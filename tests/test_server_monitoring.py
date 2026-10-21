import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "discord-bot"))

from clients.server_client import (
    MonitorError, ServerMonitor, bound_log_entries, collect_server_metrics,
    parse_container_logs, parse_journal_logs, run_monitor_command,
)
from configurations.server_config import MAX_COMMAND_BYTES, MAX_LOG_BYTES, get_aries_unit, get_monitor_owner_id
from configurations.helpers.server_helper import (
    check_monitor_owner, error_log_entries, log_text, logs_embed, redact_log_entries, redact_logs, server_embed,
)
from commands import register_commands
from main import MyBot
from views import LogsView, ServerView


def metrics():
    return {
        "host": "test-mini-pc", "platform": "Linux", "checked_at": 1_800_000_000,
        "cpu_percent": 12.5, "cpu_count": 12, "ram_used": 8 * 1024 ** 3,
        "ram_total": 64 * 1024 ** 3, "ram_percent": 12.5,
        "disk_free": 200 * 1024 ** 3, "disk_total": 500 * 1024 ** 3, "disk_percent": 60.0,
        "uptime": 90000, "process_uptime": 5000, "process_memory": 100 * 1024 ** 2,
        "temperatures": [("k10temp Tctl", 48.5)],
        "aries_status": "aries.service: active / running", "searxng_status": "running (no healthcheck reported)",
    }


def log_snapshot():
    return {
        "service": "Aries", "service_id": "aries", "source": "aries.service",
        "minutes": 30, "limit": 100, "checked_at": 1_800_000_000, "truncated": False,
        "entries": [
            {"timestamp": "2026-10-21T10:00:00+00:00", "message": "INFO started", "priority": 6},
            {"timestamp": "2026-10-21T10:01:00+00:00", "message": "ERROR request failed [REDACTED]", "priority": 6},
        ],
    }


def interaction(user_id=123):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, guild_permissions=SimpleNamespace(administrator=True)),
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock(), edit_message=AsyncMock(), is_done=Mock(return_value=True)),
        followup=SimpleNamespace(send=AsyncMock()), edit_original_response=AsyncMock(),
    )


def journal(message, priority=6, stamp=1_800_000_000_000_000):
    return json.dumps({"MESSAGE": message, "PRIORITY": str(priority), "__REALTIME_TIMESTAMP": str(stamp)})


class MonitoringHelperTests(unittest.TestCase):
    def test_owner_configuration_fails_closed_on_missing_or_invalid_id(self):
        for value in ("", "owner", "-1", "0", "１２３", "9" * 5000, str(2 ** 64)):
            with self.subTest(value=value[:20]), patch.dict("os.environ", {"ARIES_OWNER_ID": value}):
                self.assertIsNone(get_monitor_owner_id())
        with patch.dict("os.environ", {"ARIES_OWNER_ID": " 123 "}):
            self.assertEqual(get_monitor_owner_id(), "123")

    def test_unit_configuration_cannot_inject_paths_or_arguments(self):
        for unit in ("../aries.service", "--user aries.service", "aries.service;reboot", "*.service", "aries.service\nother.service"):
            with patch.dict("os.environ", {"ARIES_SYSTEMD_UNIT": unit}):
                with self.assertRaises(ValueError):
                    get_aries_unit()

    def test_redaction_covers_loaded_secrets_and_url_encoded_versions(self):
        secret = "private-test-token+with/slash"
        with patch.dict("os.environ", {"OLLAMA_API_KEY": secret}):
            text = redact_logs(f"HTTP failed {secret}\nhttps://example.com/?q={quote(secret, safe='')}")
        self.assertNotIn(secret, text)
        self.assertNotIn(quote(secret, safe=""), text)
        self.assertEqual(text.count("[REDACTED]"), 2)

    def test_unknown_credentials_and_terminal_controls_are_scrubbed(self):
        text = redact_logs(
            '\x1b[31mERROR\x1b[0m Authorization: Bearer unknown-credential\n'
            '{"access_token": "another-credential", "password": "secret-pass"}\n'
            'https://username:secret-word@example.com/\x00'
        )
        for value in ("unknown-credential", "another-credential", "secret-pass", "secret-word", "\x1b", "\x00"):
            self.assertNotIn(value, text)
        self.assertIn("ERROR", text)

    def test_private_keys_spanning_multiple_records_are_not_returned(self):
        entries = [{"message": text} for text in (
            "before", "-----BEGIN RSA PRIVATE KEY-----", "secret-base64-body",
            "more-secret-body", "-----END RSA PRIVATE KEY-----", "after",
        )]
        text = "\n".join(entry["message"] for entry in redact_log_entries(entries))
        self.assertIn("before", text)
        self.assertIn("after", text)
        self.assertNotIn("secret-base64", text)
        self.assertNotIn("more-secret", text)

    def test_error_filter_detects_python_errors_even_with_journal_info_priority(self):
        messages = ["INFO started", "ERROR command failed", "Traceback (most recent call last):", '  File "main.py", line 1', "ValueError: invalid", "INFO recovered"]
        entries = [{"message": message, "priority": 6} for message in messages]
        filtered = error_log_entries(entries)
        self.assertEqual([row["message"] for row in filtered], messages[1:5])
        self.assertEqual(len(error_log_entries([{"message": "disk problem", "priority": 3}])), 1)

    def test_bounded_logs_retain_recent_entries_and_limit_large_messages(self):
        entries = [{"message": str(number) + "x" * 10000} for number in range(20)]
        result, truncated = bound_log_entries(entries)
        self.assertTrue(truncated)
        self.assertTrue(result[-1]["message"].startswith("19"))
        self.assertLessEqual(sum(len(row["message"].encode()) + 1 for row in result), MAX_LOG_BYTES)
        result, truncated = bound_log_entries([{"message": "🚀" * MAX_LOG_BYTES}])
        self.assertTrue(truncated)
        self.assertLessEqual(len(result[0]["message"].encode()), MAX_LOG_BYTES)

    def test_journal_parser_only_extracts_required_fields_and_redacts_messages(self):
        raw = journal("ERROR password=private-password") + "\ninvalid JSON\n" + journal("INFO done")
        entries = parse_journal_logs(raw)
        self.assertEqual(len(entries), 2)
        self.assertNotIn("private-password", str(entries))
        self.assertEqual(set(entries[0]), {"timestamp", "message", "priority"})
        self.assertEqual(entries[0]["timestamp"], datetime.fromtimestamp(1_800_000_000, timezone.utc).isoformat(timespec="seconds"))

    def test_container_parser_orders_stdout_and_stderr_timestamps(self):
        entries = parse_container_logs("2026-10-21T10:01:00.123456789Z INFO done\n2026-10-21T10:00:00Z ERROR password=private-password")
        self.assertIn("ERROR", entries[0]["message"])
        self.assertNotIn("private-password", str(entries))

    def test_embeds_are_bounded_and_escape_log_code_blocks(self):
        snapshot = log_snapshot()
        snapshot["entries"] = [{"message": "```@everyone" + "🚀" * 10000, "priority": 6}]
        embed = logs_embed(snapshot)
        self.assertLess(len(embed.description.encode("utf-16-le")) // 2, 4096)
        self.assertEqual(embed.description.count("```"), 2)
        self.assertLess(len(server_embed(metrics())), 6000)


class MonitoringClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_runner_rejects_nonmonitoring_programs(self):
        with patch("clients.server_client.asyncio.create_subprocess_exec", new=AsyncMock()) as spawn:
            with self.assertRaises(MonitorError):
                await run_monitor_command("bash", ["-c", "not-a-monitoring-command"])
        spawn.assert_not_awaited()

    async def test_metrics_include_usage_and_optional_temperature(self):
        memory = SimpleNamespace(used=8, total=64, percent=12.5)
        disk = SimpleNamespace(free=100, total=200, percent=50)
        process = SimpleNamespace(create_time=Mock(return_value=100), memory_info=Mock(return_value=SimpleNamespace(rss=10)))
        with patch("clients.server_client.psutil.cpu_percent", return_value=5.0), patch("clients.server_client.psutil.virtual_memory", return_value=memory), patch("clients.server_client.psutil.disk_usage", return_value=disk), patch("clients.server_client.psutil.Process", return_value=process), patch("clients.server_client.psutil.boot_time", return_value=50), patch("clients.server_client.psutil.sensors_temperatures", create=True, return_value={"k10temp": [SimpleNamespace(label="Tctl", current=48.5)]}):
            snapshot = collect_server_metrics()
        self.assertEqual(snapshot["ram_total"], 64)
        self.assertEqual(snapshot["disk_free"], 100)
        self.assertEqual(snapshot["temperatures"], [("k10temp Tctl", 48.5)])

    async def test_snapshots_are_cached_and_metrics_run_off_the_event_loop(self):
        monitor = ServerMonitor()
        thread_ids = []
        main_thread = threading.get_ident()

        def collect():
            thread_ids.append(threading.get_ident())
            return metrics()

        with patch("clients.server_client.collect_server_metrics", new=collect):
            with patch.object(monitor, "service_status", new=AsyncMock(return_value="running")) as status:
                first, second = await asyncio.gather(monitor.snapshot(), monitor.snapshot())
        self.assertEqual(first, second)
        self.assertEqual(status.await_count, 2)
        self.assertNotEqual(thread_ids, [main_thread])
        self.assertEqual(len(thread_ids), 1)

    async def test_systemd_status_uses_only_fixed_read_only_arguments(self):
        monitor = ServerMonitor()
        with patch("clients.server_client.sys.platform", "linux"), patch.dict("os.environ", {"ARIES_SYSTEMD_UNIT": "aries.service"}):
            with patch("clients.server_client.run_monitor_command", new=AsyncMock(return_value=(0, "LoadState=loaded\nActiveState=active\nSubState=running", "", False))) as run:
                status = await monitor.service_status("aries")
        self.assertIn("active / running", status)
        self.assertEqual(run.call_args.args[0], "systemctl")
        self.assertIn("show", run.call_args.args[1])
        self.assertNotIn("sudo", run.call_args.args[1])

    async def test_compose_status_accepts_json_lines_and_arrays(self):
        for output in ('{"Service":"searxng","State":"running","Health":""}', '[{"Service":"searxng","State":"exited","Health":""}]'):
            with patch("clients.server_client.run_monitor_command", new=AsyncMock(return_value=(0, output, "", False))) as run:
                status = await ServerMonitor().service_status("searxng")
            self.assertIn("no healthcheck", status)
            self.assertEqual(run.call_args.args[1][-1], "searxng")

    async def test_missing_tools_or_permissions_do_not_claim_service_is_down(self):
        with patch("clients.server_client.run_monitor_command", new=AsyncMock(side_effect=MonitorError("docker unavailable"))):
            self.assertIn("unavailable", await ServerMonitor().service_status("searxng"))
        with patch("clients.server_client.sys.platform", "win32"):
            self.assertIn("requires Linux", await ServerMonitor().service_status("aries"))

    async def test_log_arguments_reject_arbitrary_commands_and_out_of_range_values(self):
        cases = [("../../etc/shadow", 30, 100), ("aries;reboot", 30, 100), ("aries", -1, 100), ("aries", 1441, 100), ("aries", "1;reboot", 100), ("aries", 30, 201)]
        with patch("clients.server_client.run_monitor_command", new=AsyncMock()) as run:
            for service, minutes, lines in cases:
                with self.assertRaises(MonitorError):
                    await ServerMonitor().logs(service, minutes, lines)
        run.assert_not_awaited()

    async def test_aries_logs_are_bounded_unit_filtered_and_never_use_sudo_or_priority_filter(self):
        with patch("clients.server_client.sys.platform", "linux"), patch.dict("os.environ", {"ARIES_SYSTEMD_UNIT": "aries.service"}):
            with patch("clients.server_client.run_monitor_command", new=AsyncMock(return_value=(0, journal("ERROR token=unknown-secret"), "", False))) as run:
                snapshot = await ServerMonitor().logs("aries", 15, 50)
        arguments = run.call_args.args[1]
        self.assertIn("--unit=aries.service", arguments)
        self.assertIn("--since=-15min", arguments)
        self.assertIn("--lines=50", arguments)
        self.assertNotIn("-p", arguments)
        self.assertNotIn("sudo", arguments)
        self.assertNotIn("unknown-secret", log_text(snapshot))

    async def test_journal_permission_errors_are_not_misreported_as_empty_logs(self):
        with patch("clients.server_client.sys.platform", "linux"):
            with patch("clients.server_client.run_monitor_command", new=AsyncMock(return_value=(0, "", "You are currently not seeing messages from other users", False))):
                with self.assertRaisesRegex(MonitorError, "Journal access"):
                    await ServerMonitor().logs("aries")

    async def test_container_logs_include_stderr_and_do_not_follow(self):
        with patch("clients.server_client.run_monitor_command", new=AsyncMock(return_value=(0, "2026-10-21T10:01:00Z INFO ready", "2026-10-21T10:00:00Z ERROR failed", False))) as run:
            snapshot = await ServerMonitor().logs("searxng", 30, 50)
        self.assertEqual(len(snapshot["entries"]), 2)
        arguments = run.call_args.args[1]
        self.assertIn("--tail=50", arguments)
        self.assertIn("--since=30m", arguments)
        self.assertNotIn("--follow", arguments)
        self.assertEqual(arguments[-1], "searxng")

    async def test_failed_command_does_not_echo_stderr_or_secrets(self):
        with patch("clients.server_client.run_monitor_command", new=AsyncMock(return_value=(1, "", "private-password secret command", False))):
            with self.assertRaises(MonitorError) as raised:
                await ServerMonitor().logs("searxng")
        self.assertNotIn("private-password", str(raised.exception))

    async def test_log_refresh_is_rate_limited(self):
        monitor = ServerMonitor()
        with patch("clients.server_client.run_monitor_command", new=AsyncMock(return_value=(0, "", "", False))) as run:
            await monitor.logs("searxng")
            with self.assertRaisesRegex(MonitorError, "wait"):
                await monitor.logs("searxng")
        run.assert_awaited_once()

    async def test_command_runner_never_uses_a_shell_and_bounds_its_output(self):
        stdout, stderr = asyncio.StreamReader(), asyncio.StreamReader()
        stdout.feed_data(b"old-record\n" + b"x" * (MAX_COMMAND_BYTES + 100) + b"\nrecent-record\n")
        stdout.feed_eof()
        stderr.feed_eof()
        process = SimpleNamespace(stdout=stdout, stderr=stderr, returncode=0, wait=AsyncMock(return_value=0))
        with patch("clients.server_client.shutil.which", return_value="/usr/bin/journalctl"):
            with patch("clients.server_client.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as spawn:
                code, text, _, truncated = await run_monitor_command("journalctl", ["--unit=aries.service"])
        self.assertEqual(code, 0)
        self.assertTrue(truncated)
        self.assertIn("recent-record", text)
        self.assertNotIn("old-record", text)
        self.assertLessEqual(len(text.encode()), MAX_COMMAND_BYTES)
        self.assertNotIn("shell", spawn.call_args.kwargs)

    async def test_command_timeout_kills_only_spawned_process_and_reports_safe_error(self):
        stdout, stderr = asyncio.StreamReader(), asyncio.StreamReader()
        process = SimpleNamespace(stdout=stdout, stderr=stderr, returncode=None, wait=AsyncMock(return_value=-9))

        def kill():
            process.returncode = -9
            stdout.feed_eof()
            stderr.feed_eof()

        process.kill = Mock(side_effect=kill)
        with patch("clients.server_client.shutil.which", return_value="/usr/bin/journalctl"), patch("clients.server_client.COMMAND_TIMEOUT", 0.01):
            with patch("clients.server_client.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
                with self.assertRaisesRegex(MonitorError, "timed out"):
                    await run_monitor_command("journalctl", [])
        process.kill.assert_called_once()


class MonitoringInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.environment = patch.dict("os.environ", {"ARIES_OWNER_ID": "123"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.bot = MyBot()
        register_commands(self.bot)
        self.addAsyncCleanup(self.bot.close)

    async def test_commands_and_all_controls_register(self):
        self.assertIsNotNone(self.bot.commands.get_command("server"))
        self.assertIsNotNone(self.bot.commands.get_command("logs"))
        self.assertTrue(ServerView("123", self.bot.monitor).to_components())
        self.assertEqual(len(LogsView("123", self.bot.monitor, log_snapshot()).children), 3)

    async def test_nonowner_even_if_admin_cannot_trigger_any_monitoring(self):
        with patch.object(self.bot.monitor, "snapshot", new=AsyncMock()) as status, patch.object(self.bot.monitor, "logs", new=AsyncMock()) as logs:
            for name in ("server", "logs"):
                request = interaction(999)
                await self.bot.commands.get_command(name).callback(request)
                self.assertTrue(request.response.send_message.call_args.kwargs["ephemeral"])
        status.assert_not_awaited()
        logs.assert_not_awaited()

    async def test_missing_owner_disables_commands(self):
        with patch.dict("os.environ", {"ARIES_OWNER_ID": ""}):
            request = interaction()
            self.assertFalse(await check_monitor_owner(request))
        self.assertIn("disabled", request.response.send_message.call_args.args[0])

    async def test_server_defers_privately_before_collecting_metrics(self):
        request = interaction()

        async def snapshot():
            request.response.defer.assert_awaited_once()
            self.assertTrue(request.response.defer.call_args.kwargs["ephemeral"])
            return metrics()

        with patch.object(self.bot.monitor, "snapshot", new=snapshot):
            await self.bot.commands.get_command("server").callback(request)
        self.assertIsInstance(request.edit_original_response.call_args.kwargs["view"], ServerView)
        self.assertTrue(any(field.name == "RAM" for field in request.edit_original_response.call_args.kwargs["embed"].fields))

    async def test_logs_command_is_private_and_shows_filtered_snapshot(self):
        request = interaction()
        with patch.object(self.bot.monitor, "logs", new=AsyncMock(return_value=log_snapshot())) as logs:
            await self.bot.commands.get_command("logs").callback(request, "aries", 30, 100, True)
        self.assertTrue(request.response.defer.call_args.kwargs["ephemeral"])
        self.assertIsInstance(request.edit_original_response.call_args.kwargs["view"], LogsView)
        self.assertNotIn("INFO started", request.edit_original_response.call_args.kwargs["embed"].description)
        logs.assert_awaited_once_with("aries", 30, 100)

    async def test_buttons_check_current_owner_and_revoke_old_sessions(self):
        view = LogsView("123", self.bot.monitor, log_snapshot())
        self.assertFalse(await view.interaction_check(interaction(999)))
        self.assertTrue(await view.interaction_check(interaction(123)))
        with patch.dict("os.environ", {"ARIES_OWNER_ID": "999"}):
            self.assertFalse(await view.interaction_check(interaction(123)))
            self.assertFalse(await view.interaction_check(interaction(999)))

    async def test_error_toggle_is_local_and_download_is_ephemeral(self):
        view = LogsView("123", self.bot.monitor, log_snapshot())
        request = interaction()
        with patch.object(self.bot.monitor, "logs", new=AsyncMock()) as logs:
            await view.errors.callback(request)
            self.assertTrue(view.errors_only)
            await view.download.callback(request)
        logs.assert_not_awaited()
        kwargs = request.followup.send.call_args.kwargs
        self.assertTrue(kwargs["ephemeral"])
        text = kwargs["file"].fp.read().decode()
        kwargs["file"].close()
        self.assertNotIn("INFO started", text)
        self.assertIn("ERROR request failed", text)

    async def test_refresh_preserves_log_parameters_and_error_mode(self):
        view = LogsView("123", self.bot.monitor, log_snapshot(), errors_only=True)
        request = interaction()
        with patch.object(self.bot.monitor, "logs", new=AsyncMock(return_value=log_snapshot())) as logs:
            await view.refresh.callback(request)
        logs.assert_awaited_once_with("aries", 30, 100)
        self.assertTrue(view.errors_only)
        request.response.defer.assert_awaited_once()

    async def test_backend_errors_are_private_and_do_not_return_a_broken_view(self):
        request = interaction()
        with patch.object(self.bot.monitor, "snapshot", new=AsyncMock(side_effect=MonitorError("Metrics unavailable"))):
            await self.bot.commands.get_command("server").callback(request)
        self.assertEqual(request.edit_original_response.call_args.kwargs["content"], "Metrics unavailable")
        self.assertNotIn("view", request.edit_original_response.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
