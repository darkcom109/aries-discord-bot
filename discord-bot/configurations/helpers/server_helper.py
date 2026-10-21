from datetime import datetime, timezone
import json
import os
import re
from urllib.parse import quote, quote_plus

import discord

from configurations.server_config import get_monitor_owner_id
from .response_helper import shorten_text


async def check_monitor_owner(interaction, user_id: str | None = None) -> bool:
    owner_id = get_monitor_owner_id()
    if owner_id is None:
        message = "Server monitoring is disabled. Set ARIES_OWNER_ID to your Discord user ID in .env, then restart Aries."
    elif str(interaction.user.id) != owner_id or (user_id is not None and user_id != owner_id):
        message = "Only the configured Aries owner can access server monitoring."
    else:
        return True
    await interaction.response.send_message(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    return False


def redact_logs(text: str) -> str:
    # Strip terminal escape sequences and non-printing control characters first.
    text = re.sub(r"\x1b\][^\x07]*?(?:\x07|\x1b\\)", "", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    values = set()
    for name, value in os.environ.items():
        if value and len(value) >= 6 and re.search(r"token|secret|password|passwd|api.?key|app.?key|credential|cookie", name, re.I):
            values.update((value, quote(value, safe=""), quote_plus(value), json.dumps(value)[1:-1]))
    for value in sorted(values, key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    text = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", "[REDACTED PRIVATE KEY]", text, flags=re.S)
    text = re.sub(r"(?i)\b(Bearer|Basic|Bot)\s+[A-Za-z0-9._~+/=-]+", r"\1 [REDACTED]", text)
    text = re.sub(
        r'''(?ix)(\b[\w-]*(?:token|secret|password|passwd|api[_-]?key|app[_-]?key|authorization|cookie)\b["']?\s*[:=]\s*)
        (?:"[^"\n]*"|'[^'\n]*'|[^\s,;&}\]]+)''',
        r"\1[REDACTED]", text,
    )
    text = re.sub(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b", "[REDACTED TOKEN]", text)
    return text


def redact_log_entries(entries: list[dict]) -> list[dict]:
    result = []
    inside_key = False
    begin_pattern = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
    end_pattern = re.compile(r"-----END [A-Z ]*PRIVATE KEY-----")
    for entry in entries:
        message = entry["message"]
        if inside_key:
            end = end_pattern.search(message)
            if end is None:
                continue
            message = message[end.end():]
            inside_key = False
        while begin := begin_pattern.search(message):
            end = end_pattern.search(message, begin.end())
            if end is None:
                message = message[:begin.start()] + "[REDACTED PRIVATE KEY]"
                inside_key = True
                break
            message = message[:begin.start()] + "[REDACTED PRIVATE KEY]" + message[end.end():]
        if message.strip():
            result.append({**entry, "message": redact_logs(message)})
    return result


def error_log_entries(entries: list[dict]) -> list[dict]:
    result = []
    in_traceback = False
    marker = re.compile(r"\b(error|critical|fatal|traceback|panic|exception|failed|failure)\b|\b\w*(?:Error|Exception):", re.I)
    for entry in entries:
        message = entry["message"]
        priority = entry.get("priority")
        error = (isinstance(priority, int) and priority <= 3) or marker.search(message) is not None
        continuation = message.startswith((" ", "\t", "During handling of the above exception", "The above exception"))
        if error or (in_traceback and continuation):
            result.append(entry)
            in_traceback = True
        else:
            in_traceback = False
    return result


def render_log_entry(entry: dict) -> str:
    timestamp = entry.get("timestamp") or ""
    return f"{timestamp} {entry['message']}".strip() if timestamp else entry["message"]


def log_text(snapshot: dict, errors_only: bool = False) -> str:
    entries = error_log_entries(snapshot["entries"]) if errors_only else snapshot["entries"]
    mode = "Errors and traceback context" if errors_only else "All captured entries"
    header = f"{snapshot['service']} | {snapshot['source']} | last {snapshot['minutes']} minutes\n{mode}\n"
    if snapshot["truncated"]:
        header += "Output was capped; older/oversized entries may be omitted.\n"
    body = "\n".join(render_log_entry(entry) for entry in entries)
    return header + "\n" + (body or "No matching entries in the captured log sample.")


def display_metric_text(value: str) -> str:
    return discord.utils.escape_markdown(discord.utils.escape_mentions(redact_logs(str(value))))


def format_bytes(value: int | float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return "Unavailable"


def format_uptime(seconds: float) -> str:
    minutes = max(0, int(seconds)) // 60
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    return f"{days}d {hours}h {minutes}m"


def server_embed(snapshot: dict) -> discord.Embed:
    embed = discord.Embed(
        title="Aries host status",
        description=f"{display_metric_text(snapshot['host'])} · {display_metric_text(snapshot['platform'])}",
        colour=discord.Colour.blurple(),
        timestamp=datetime.fromtimestamp(snapshot["checked_at"], timezone.utc),
    )
    embed.add_field(name="CPU", value=f"{snapshot['cpu_percent']:.1f}% · {snapshot['cpu_count']} logical cores")
    embed.add_field(name="RAM", value=f"{format_bytes(snapshot['ram_used'])} / {format_bytes(snapshot['ram_total'])}\n{snapshot['ram_percent']:.1f}% used")
    embed.add_field(name="Disk · Aries filesystem", value=f"{format_bytes(snapshot['disk_free'])} free / {format_bytes(snapshot['disk_total'])}\n{snapshot['disk_percent']:.1f}% used")
    embed.add_field(name="Host uptime", value=format_uptime(snapshot["uptime"]))
    embed.add_field(name="Aries process", value=f"Running · {format_uptime(snapshot['process_uptime'])}\nRAM: {format_bytes(snapshot['process_memory'])}")
    temperatures = snapshot["temperatures"]
    embed.add_field(name="Temperatures", value="\n".join(f"{display_metric_text(label)[:80]}: {value:.1f} °C" for label, value in temperatures) or "Not reported by this OS/hardware")
    embed.add_field(name="Aries systemd service", value=shorten_text(display_metric_text(snapshot["aries_status"]), 500), inline=False)
    embed.add_field(name="SearXNG Compose service", value=shorten_text(display_metric_text(snapshot["searxng_status"]), 500), inline=False)
    embed.set_footer(text="Owner only · Read-only snapshot · Cache: up to 5 seconds · No AI request")
    return embed


def logs_embed(snapshot: dict, errors_only: bool = False) -> discord.Embed:
    entries = error_log_entries(snapshot["entries"]) if errors_only else snapshot["entries"]
    preview = "\n".join(render_log_entry(entry) for entry in entries[-12:])
    preview = preview or "No matching entries in the captured log sample."
    preview = shorten_text(preview.replace("```", "`\u200b``"), 2800)
    note = "Output capped; narrow the time window for more detail.\n" if snapshot["truncated"] else ""
    embed = discord.Embed(
        title=f"{snapshot['service']} logs",
        description=f"{snapshot['minutes']} minute window · {len(entries)} matching entries in the captured sample\n"
                    + note + "```text\n" + preview + "\n```",
        colour=discord.Colour.blurple(),
        timestamp=datetime.fromtimestamp(snapshot["checked_at"], timezone.utc),
    )
    embed.set_footer(text="Owner only · Last 12 matches previewed · Download gets the captured sample · Redaction is best-effort")
    return embed
