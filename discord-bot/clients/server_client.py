import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import json
import math
import platform
import shutil
import sys
import time

import psutil

from configurations.server_config import (
    COMMAND_TIMEOUT, LOG_SERVICES, MAX_COMMAND_BYTES, MAX_LOG_BYTES, MAX_LOG_LINES, PROJECT_DIRECTORY, get_aries_unit,
)
from configurations.helpers.server_helper import redact_log_entries, render_log_entry


class MonitorError(Exception):
    pass


async def run_monitor_command(program: str, arguments: list[str]):
    if program not in {"systemctl", "journalctl", "docker"}:
        raise MonitorError("Only predefined monitoring programs are supported.")
    executable = shutil.which(program)
    if executable is None:
        raise MonitorError(f"{program} is not installed or is not on the Aries service's PATH.")
    try:
        process = await asyncio.create_subprocess_exec(
            executable, *arguments, cwd=PROJECT_DIRECTORY,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        raise MonitorError(f"I couldn't run the read-only {program} check.") from None

    async def read_bounded(stream):
        data = bytearray()
        truncated = False
        while chunk := await stream.read(8192):
            data.extend(chunk)
            if len(data) > MAX_COMMAND_BYTES:
                del data[:-MAX_COMMAND_BYTES]
                truncated = True
        if truncated:
            # Never expose the first partial record after a bounded tail read.
            data = data.partition(b"\n")[2]
        return data.decode("utf-8", errors="replace"), truncated

    async def collect():
        stdout, stderr = await asyncio.gather(read_bounded(process.stdout), read_bounded(process.stderr))
        await process.wait()
        return process.returncode, stdout[0], stderr[0], stdout[1] or stderr[1]

    collection = asyncio.create_task(collect())
    try:
        return await asyncio.wait_for(asyncio.shield(collection), timeout=COMMAND_TIMEOUT)
    except (TimeoutError, asyncio.CancelledError) as error:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
        try:
            await asyncio.wait_for(asyncio.shield(collection), timeout=2)
        except (TimeoutError, asyncio.CancelledError):
            collection.cancel()
            with suppress(asyncio.CancelledError):
                await collection
        if isinstance(error, asyncio.CancelledError):
            raise
        raise MonitorError("The service check timed out. Please try again later.") from None


def collect_server_metrics():
    now = time.time()
    try:
        cpu_percent = psutil.cpu_percent(interval=0.2)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(PROJECT_DIRECTORY))
        process = psutil.Process()
        snapshot = {
            "host": platform.node(), "platform": platform.system(), "checked_at": int(now),
            "cpu_percent": cpu_percent, "cpu_count": psutil.cpu_count() or 0,
            "ram_used": memory.used, "ram_total": memory.total, "ram_percent": memory.percent,
            "disk_free": disk.free, "disk_total": disk.total, "disk_percent": disk.percent,
            "uptime": now - psutil.boot_time(), "process_uptime": now - process.create_time(),
            "process_memory": process.memory_info().rss, "temperatures": [],
        }
    except (psutil.Error, OSError):
        raise MonitorError("I couldn't read host metrics with the current service permissions.") from None

    sensor_function = getattr(psutil, "sensors_temperatures", None)
    if sensor_function is not None:
        try:
            for sensor, readings in sensor_function().items():
                for reading in readings:
                    if reading.current is not None and math.isfinite(reading.current):
                        label = f"{sensor} {reading.label or ''}".strip()
                        snapshot["temperatures"].append((label, reading.current))
            snapshot["temperatures"] = snapshot["temperatures"][:5]
        except (psutil.Error, OSError, NotImplementedError):
            pass
    return snapshot


def compose_arguments() -> list[str]:
    return ["compose", "--project-directory", str(PROJECT_DIRECTORY), "-f", str(PROJECT_DIRECTORY / "compose.yaml")]


class ServerMonitor:
    def __init__(self):
        self.status_lock = asyncio.Lock()
        self.logs_lock = asyncio.Lock()
        self.status_cache = None
        self.status_cached_at = 0.0
        self.last_logs_at = float("-inf")

    async def snapshot(self):
        async with self.status_lock:
            if self.status_cache is not None and time.monotonic() - self.status_cached_at < 5:
                return self.status_cache
            metrics, aries, searxng = await asyncio.gather(
                asyncio.to_thread(collect_server_metrics), self.service_status("aries"), self.service_status("searxng"),
            )
            self.status_cache = {**metrics, "aries_status": aries, "searxng_status": searxng}
            self.status_cached_at = time.monotonic()
            return self.status_cache

    async def service_status(self, service: str) -> str:
        try:
            if service == "aries":
                if not sys.platform.startswith("linux"):
                    return "Unavailable: systemd status requires Linux. The Aries process is running."
                try:
                    unit = get_aries_unit()
                except ValueError as error:
                    raise MonitorError(str(error)) from None
                code, stdout, _, _ = await run_monitor_command(
                    "systemctl", ["show", "--no-pager", "--property=LoadState,ActiveState,SubState", unit],
                )
                if code != 0:
                    return "Unavailable: systemd is not running or access was denied."
                values = dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)
                if values.get("LoadState") == "not-found":
                    return "Unit not found. Check ARIES_SYSTEMD_UNIT if Aries runs under a different service name."
                return f"{unit}: {values.get('ActiveState', 'unknown')} / {values.get('SubState', 'unknown')}"
            if service != "searxng":
                raise MonitorError("Choose aries or searxng.")
            code, stdout, _, _ = await run_monitor_command(
                "docker", compose_arguments() + ["ps", "--all", "--format", "json", "searxng"],
            )
            if code != 0:
                return "Unavailable: check Docker/Compose access, the daemon, and the repo-root .env."
            try:
                rows = json.loads(stdout) if stdout.strip().startswith("[") else [json.loads(line) for line in stdout.splitlines() if line.strip()]
                rows = [row for row in rows if row.get("Service") == "searxng"]
            except (ValueError, AttributeError, TypeError):
                return "Unavailable: Docker returned an unexpected status response."
            if not rows:
                return "No SearXNG container found for this Compose project."
            return "; ".join(
                str(row.get("State") or "unknown") + (f" (health: {row['Health']})" if row.get("Health") else " (no healthcheck reported)")
                for row in rows[:3]
            )
        except MonitorError as error:
            return str(error)

    async def logs(self, service: str, minutes: int = 30, lines: int = 100):
        if service not in LOG_SERVICES:
            raise MonitorError("Choose aries or searxng; arbitrary services and file paths aren't supported.")
        if type(minutes) is not int or not 1 <= minutes <= 1440:
            raise MonitorError("Choose a log window between 1 and 1440 minutes.")
        if type(lines) is not int or not 1 <= lines <= MAX_LOG_LINES:
            raise MonitorError(f"Choose between 1 and {MAX_LOG_LINES} log entries.")
        async with self.logs_lock:
            if time.monotonic() - self.last_logs_at < 2:
                raise MonitorError("Please wait a couple of seconds before refreshing logs.")
            self.last_logs_at = time.monotonic()
            if service == "aries":
                if not sys.platform.startswith("linux"):
                    raise MonitorError("Aries service logs require Linux and journalctl. Run this command on your mini PC's Aries instance.")
                try:
                    unit = get_aries_unit()
                except ValueError as error:
                    raise MonitorError(str(error)) from None
                arguments = [
                    "--unit=" + unit, f"--since=-{minutes}min", f"--lines={lines}",
                    "--no-pager", "--output=json", "--output-fields=__REALTIME_TIMESTAMP,MESSAGE,PRIORITY",
                ]
                code, stdout, stderr, truncated = await run_monitor_command("journalctl", arguments)
                source = unit
                if journal_access_denied(stderr):
                    raise MonitorError("Journal access was denied or is incomplete. Check the Aries service user's journal-reading permissions; Aries never uses sudo.")
            else:
                code, stdout, stderr, truncated = await run_monitor_command(
                    "docker", compose_arguments() + ["logs", "--no-color", "--no-log-prefix", "--timestamps", f"--since={minutes}m", f"--tail={lines}", "searxng"],
                )
                source = "Compose service: searxng"
            if code != 0:
                raise MonitorError("I couldn't read those logs. Check the service name, journal/Docker permissions and service configuration. No elevated commands were attempted.")
            entries = parse_journal_logs(stdout) if service == "aries" else parse_container_logs(stdout + "\n" + stderr)
            entries, capped = bound_log_entries(entries[-lines:])
            return {
                "service": LOG_SERVICES[service], "service_id": service, "source": source,
                "minutes": minutes, "limit": lines, "entries": entries,
                "checked_at": int(time.time()), "truncated": truncated or capped,
            }


def journal_access_denied(text: str) -> bool:
    return any(word in text.lower() for word in ("permission", "access denied", "not seeing messages", "no journal files were opened"))


def parse_journal_logs(text: str) -> list[dict]:
    entries = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
            message = row.get("MESSAGE")
            if not isinstance(message, str):
                continue
            timestamp = datetime.fromtimestamp(int(row["__REALTIME_TIMESTAMP"]) / 1_000_000, timezone.utc).isoformat(timespec="seconds")
            priority = int(row.get("PRIORITY", 6))
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, OSError):
            continue
        entries.append({"timestamp": timestamp, "message": message, "priority": priority})
    return redact_log_entries(entries)


def parse_container_logs(text: str) -> list[dict]:
    entries = []
    for line in text.splitlines():
        stamp, _, message = line.partition(" ")
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            timestamp = parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
        except ValueError:
            timestamp, message = "", line
        entries.append({"timestamp": timestamp, "message": message, "priority": None})
    entries.sort(key=lambda entry: entry["timestamp"])
    return redact_log_entries(entries)


def bound_log_entries(entries: list[dict]):
    kept = []
    size = 0
    truncated = False
    for entry in reversed(entries):
        entry_size = len(render_log_entry(entry).encode("utf-8")) + 1
        if size + entry_size > MAX_LOG_BYTES:
            if not kept:
                entry = {**entry, "message": entry["message"].encode("utf-8")[:MAX_LOG_BYTES - 200].decode("utf-8", errors="ignore") + "\n[Entry truncated]"}
                kept.append(entry)
            truncated = True
            break
        kept.append(entry)
        size += entry_size
    return list(reversed(kept)), truncated
