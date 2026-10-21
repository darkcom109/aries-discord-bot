import asyncio
from datetime import datetime, timezone
from email.message import Message
import json
from pathlib import Path
import shutil
import socket
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "discord-bot"))

import discord
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import database
from database import connection
from clients.autonomy_client import AutonomyClient, AutonomyStopped
from clients.page_client import fetch_page_text, public_page_target
from commands import register_commands
from main import MyBot


def request(user_id=123):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id), response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        edit_original_response=AsyncMock(), guild=SimpleNamespace(id=456),
    )


def tool_response(*functions):
    return {"message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": name, "arguments": arguments}} for name, arguments in functions
    ]}}


class AutonomyStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = Path(__file__).resolve().parent / f".aries-autonomy-{uuid4().hex}"
        self.directory.mkdir()
        self.addCleanup(shutil.rmtree, self.directory)
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{(self.directory / 'test.db').as_posix()}")
        self.addAsyncCleanup(self.engine.dispose)
        for item in (patch.object(connection, "engine", self.engine),
                     patch.object(connection, "SessionFactory", async_sessionmaker(self.engine, expire_on_commit=False)),
                     patch.dict("os.environ", {"ARIES_OWNER_ID": "123"})):
            item.start()
            self.addCleanup(item.stop)
        await database.create_tables()
        self.channel = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=999)))
        self.client = AutonomyClient(SimpleNamespace(tfl=Mock()))
        self.client.approved_channel = AsyncMock(return_value=self.channel)
        self.addAsyncCleanup(self.client.cancel_cycle)

    async def enabled(self, allow_actions=False):
        return await database.configure_autonomy("123", "456", "789", "Track useful changes and cite evidence.", 15, allow_actions)

    async def test_default_off_claim_persistence_and_stop_revision(self):
        self.assertIsNone(await database.get_autonomy_state())
        self.assertIsNone(await database.claim_autonomy_run(int(time.time())))
        state = await self.enabled()
        results = await asyncio.gather(database.claim_autonomy_run(int(time.time())), database.claim_autonomy_run(int(time.time())))
        self.assertEqual(sum(item is not None for item in results), 1)
        await database.finish_autonomy_run(state, "Remember verified facts", 60)
        await self.engine.dispose()
        current = await database.get_autonomy_state()
        self.assertTrue(current.enabled)
        self.assertEqual(current.memory, "Remember verified facts")
        await database.disable_autonomy()
        self.assertFalse(await database.autonomy_is_current(state))
        await database.finish_autonomy_run(state, "stale write", 15)
        self.assertEqual((await database.get_autonomy_state()).memory, "Remember verified facts")

    async def test_action_budget_and_duplicate_reservations_survive_failed_delivery(self):
        first = await database.reserve_autonomy_action("send_message", "one", "signature1")
        await database.complete_autonomy_action(first, "error")
        self.assertIsNone(await database.reserve_autonomy_action("send_message", "duplicate", "signature1"))
        self.assertIsNotNone(await database.reserve_autonomy_action("send_message", "two", "signature2"))
        self.assertIsNotNone(await database.reserve_autonomy_action("create_poll", "three", "signature3"))
        self.assertIsNone(await database.reserve_autonomy_action("create_reminder", "four", "signature4"))
        self.assertIsNotNone(await database.reserve_autonomy_action("web_search", "read only"))

    async def test_concurrent_reservations_cannot_exceed_three(self):
        ids = await asyncio.gather(*(database.reserve_autonomy_action("send_message", str(index), f"s{index}") for index in range(8)))
        self.assertEqual(sum(item is not None for item in ids), 3)

    async def test_activity_is_owner_and_channel_scoped(self):
        await database.reserve_autonomy_action("web_search", "private", owner_id="123", channel_id="789")
        self.assertEqual(await database.get_autonomy_actions(owner_id="456"), [])
        self.assertEqual(await database.get_autonomy_actions(owner_id="123", channel_id="other"), [])
        self.assertEqual(len(await database.get_autonomy_actions(owner_id="123", channel_id="789")), 1)

    async def test_disabled_ticks_never_call_model_and_owner_change_revokes_mode(self):
        with patch("clients.autonomy_client.ollama_request", new=AsyncMock()) as model:
            await self.client.tick()
            await self.enabled()
            with patch.dict("os.environ", {"ARIES_OWNER_ID": "456"}):
                await self.client.tick()
        model.assert_not_awaited()
        self.assertFalse((await database.get_autonomy_state()).enabled)

    async def test_search_result_is_fed_back_to_model_then_one_post_and_memory_are_saved(self):
        state = await self.enabled()
        responses = [tool_response(("web_search", {"query": "TfL news"})),
                     tool_response(("send_message", {"content": "Verified update: https://example.com/news"}),
                                   ("finish_cycle", {"memory": "Posted the verified update; don't repeat it.", "wait_minutes": 60}))]
        with patch("clients.autonomy_client.ollama_request", new=AsyncMock(side_effect=responses)) as model, patch(
            "clients.autonomy_client.web_search", new=AsyncMock(return_value=[{"title": "News", "url": "https://example.com/news", "content": "Useful fact"}])
        ):
            await self.client.run_cycle(state)
        self.channel.send.assert_awaited_once()
        kwargs = self.channel.send.call_args.kwargs
        self.assertFalse(kwargs["allowed_mentions"].everyone)
        self.assertFalse(kwargs["allowed_mentions"].users)
        self.assertTrue(kwargs["suppress_embeds"])
        self.assertEqual(model.await_count, 2)
        messages = model.call_args.args[0]
        self.assertTrue(any(row["role"] == "tool" and "Useful fact" in row["content"] for row in messages))
        self.assertEqual((await database.get_autonomy_state()).memory, "Posted the verified update; don't repeat it.")
        self.assertEqual(len(await database.load_messages("456", "789")), 1)
        self.assertEqual(await database.load_messages("456", "other"), [])

    async def test_plain_completion_and_finish_cycle_are_quiet(self):
        state = await self.enabled()
        for data in ({"message": {"content": "Nothing meaningful changed."}},
                     tool_response(("finish_cycle", {"memory": "No new facts", "wait_minutes": 120}))):
            with patch("clients.autonomy_client.ollama_request", new=AsyncMock(return_value=data)):
                await self.client.run_cycle(state)
        self.channel.send.assert_not_awaited()
        self.assertEqual((await database.get_autonomy_state()).memory, "No new facts")

    async def test_stop_during_inference_cancels_cycle_and_prevents_late_post(self):
        await self.enabled()
        started = asyncio.Event()

        async def wait_for_model(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()

        with patch("clients.autonomy_client.ollama_request", side_effect=wait_for_model):
            tick = asyncio.create_task(self.client.tick())
            await started.wait()
            await self.client.stop()
            await tick
        self.assertFalse((await database.get_autonomy_state()).enabled)
        self.channel.send.assert_not_awaited()

    async def test_stale_state_cannot_run_any_tool(self):
        state = await self.enabled()
        await database.disable_autonomy()
        with self.assertRaises(AutonomyStopped):
            await self.client.run_tool(state, self.channel, "send_message", {"content": "late"})
        self.channel.send.assert_not_awaited()

    async def test_unknown_tools_and_polls_reminders_without_opt_in_are_rejected(self):
        state = await self.enabled()
        for name, arguments in (("shell", {"command": "anything"}), ("get_logs", {}),
                                ("create_poll", {"question": "x", "options": ["A", "B"]}),
                                ("create_reminder", {"content": "x", "time": "later"})):
            with self.subTest(name=name), self.assertRaises(ValueError):
                await self.client.run_tool(state, self.channel, name, arguments)
        self.channel.send.assert_not_awaited()

    async def test_goal_and_tool_arguments_cannot_select_another_recipient(self):
        state = await self.enabled()
        await self.client.run_tool(state, self.channel, "send_message", {"content": "hello", "channel_id": "other", "user_id": "other"})
        self.channel.send.assert_awaited_once()
        messages = await database.load_messages("456", "789")
        self.assertEqual(messages[0].user_id, "123")
        with self.assertRaises(ValueError):
            await self.client.run_tool(state, self.channel, "send_message", {"content": "hello", "channel_id": "yet another"})
        self.assertEqual(self.channel.send.await_count, 1)

    async def test_runtime_channel_permissions_and_owner_membership_are_rechecked(self):
        state = await self.enabled()
        channel = Mock(spec=discord.TextChannel)
        channel.guild = SimpleNamespace(id=456, me=Mock(), fetch_member=AsyncMock(return_value=Mock()))
        channel.permissions_for.return_value = SimpleNamespace(view_channel=True, send_messages=True)
        client = AutonomyClient(SimpleNamespace(get_channel=Mock(return_value=channel)))
        self.assertIs(await client.approved_channel(state), channel)
        channel.guild.fetch_member.assert_awaited_once_with(123)
        channel.permissions_for.return_value = SimpleNamespace(view_channel=False, send_messages=False)
        with self.assertRaises(ValueError):
            await client.approved_channel(state)
        channel.guild.id = 999
        with self.assertRaises(ValueError):
            await client.approved_channel(state)

    async def test_unavailable_backend_backs_off_without_exposing_exception_text(self):
        state = await self.enabled()
        with patch("clients.autonomy_client.ollama_request", new=AsyncMock(side_effect=RuntimeError("private secret URL"))):
            await self.client.run_cycle(state)
        current = await database.get_autonomy_state()
        self.assertGreaterEqual(current.next_run_at, int(time.time()) + 29 * 60)
        entries = await database.get_autonomy_actions()
        self.assertEqual(entries[0].name, "error")
        self.assertNotIn("private secret URL", entries[0].detail)
        self.channel.send.assert_not_awaited()

    async def test_finished_read_only_cycles_obey_model_and_tool_budgets(self):
        state = await self.enabled()
        data = tool_response(*[("web_search", {"query": str(index)}) for index in range(10)])
        with patch("clients.autonomy_client.ollama_request", new=AsyncMock(return_value=data)) as model, patch(
            "clients.autonomy_client.web_search", new=AsyncMock(return_value=[])
        ) as search:
            await self.client.run_cycle(state)
        self.assertEqual(search.await_count, 4)
        self.assertEqual(model.await_count, 1)
        names = {item["function"]["name"] for item in model.call_args.kwargs["tools"]}
        self.assertNotIn("create_poll", names)
        self.assertNotIn("create_reminder", names)
        self.assertIn("finish_cycle", names)
        self.channel.send.assert_not_awaited()

    async def test_shutdown_cancellation_does_not_disable_persisted_mode(self):
        await self.enabled()
        await self.client.cancel_cycle()
        self.assertTrue((await database.get_autonomy_state()).enabled)

    async def test_reminder_delivery_can_ping_only_its_owner_not_roles_or_everyone(self):
        await database.save_reminder("456", "789", "123", "@everyone <@&456> <@999> Stretch", int(time.time()) - 1, "none")
        bot = MyBot()
        bot.get_partial_messageable = Mock(return_value=SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=444))))
        try:
            await MyBot.check_reminders.coro(bot)
            mentions = bot.get_partial_messageable.return_value.send.call_args.kwargs["allowed_mentions"]
            self.assertFalse(mentions.everyone)
            self.assertFalse(mentions.roles)
            self.assertFalse(mentions.replied_user)
            self.assertEqual([item.id for item in mentions.users], [123])
        finally:
            await bot.close()

    async def test_outgoing_text_and_activity_scrub_loaded_secrets(self):
        state = await self.enabled()
        with patch.dict("os.environ", {"OLLAMA_API_KEY": "secret-credential-for-test"}):
            await self.client.run_tool(state, self.channel, "send_message", {"content": "secret-credential-for-test"})
        self.assertNotIn("secret-credential-for-test", self.channel.send.call_args.kwargs["content"])
        self.assertNotIn("secret-credential-for-test", (await database.get_autonomy_actions())[0].detail)

    async def test_searches_and_urls_cannot_send_loaded_credentials(self):
        state = await self.enabled()
        with patch.dict("os.environ", {"OLLAMA_API_KEY": "secret-credential-for-test"}), patch(
            "clients.autonomy_client.web_search", new=AsyncMock()
        ) as search, patch("clients.autonomy_client.fetch_page_text") as fetch:
            for name, arguments in (("web_search", {"query": "secret-credential-for-test"}),
                                    ("read_web_page", {"url": "https://example.com/?key=secret-credential-for-test"})):
                with self.assertRaises(ValueError):
                    await self.client.run_tool(state, self.channel, name, arguments)
        search.assert_not_awaited()
        fetch.assert_not_called()

    async def test_poll_validation_and_one_time_reminder_target_owner(self):
        state = await self.enabled(True)
        with self.assertRaises(ValueError):
            await self.client.run_tool(state, self.channel, "create_poll", {"question": "Q", "options": ["One"]})
        await self.client.run_tool(state, self.channel, "create_poll", {"question": "Pick", "options": ["A", "B"]})
        self.assertEqual(len(self.channel.send.call_args.kwargs["poll"].answers), 2)
        target = datetime.fromtimestamp(time.time() + 3600, timezone.utc).isoformat()
        result = await self.client.run_tool(state, self.channel, "create_reminder", {"content": "stretch", "time": target})
        self.assertIn("reminder #", result)
        reminders = await database.get_user_reminders("456", "789", "123")
        self.assertEqual(reminders[0].content, "Stretch")
        self.assertEqual(reminders[0].repeat, "none")
        for target in ("2026-01-01T12:00:00", "invalid", datetime.fromtimestamp(time.time() + 10 * 86400, timezone.utc).isoformat()):
            with self.assertRaises(ValueError):
                await self.client.run_tool(state, self.channel, "create_reminder", {"content": "x", "time": target})

    async def test_only_one_outward_action_per_cycle_and_model_turns_are_bounded(self):
        state = await self.enabled()
        data = tool_response(("send_message", {"content": "First"}), ("send_message", {"content": "Second"}))
        with patch("clients.autonomy_client.ollama_request", new=AsyncMock(return_value=data)) as model:
            await self.client.run_cycle(state)
        self.channel.send.assert_awaited_once()
        self.assertLessEqual(model.await_count, 3)

    async def test_a_failed_send_is_recorded_and_never_retried_as_a_duplicate(self):
        state = await self.enabled()
        self.channel.send.side_effect = RuntimeError("secret error text")
        with self.assertRaises(RuntimeError):
            await self.client.run_tool(state, self.channel, "send_message", {"content": "First"})
        self.channel.send.side_effect = None
        with self.assertRaises(ValueError):
            await self.client.run_tool(state, self.channel, "send_message", {"content": "First"})
        self.assertEqual(self.channel.send.await_count, 1)
        self.assertEqual((await database.get_autonomy_actions())[0].status, "error")


class AutonomyCommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        environment = patch.dict("os.environ", {"ARIES_OWNER_ID": "123"})
        environment.start()
        self.addCleanup(environment.stop)
        self.bot = MyBot()
        register_commands(self.bot)
        self.addAsyncCleanup(self.bot.close)
        self.group = self.bot.commands.get_command("autonomy")

    async def test_commands_register_and_nonowners_are_denied_before_any_work(self):
        self.assertEqual({item.name for item in self.group.commands}, {"start", "stop", "status", "activity"})
        for name in ("stop", "status", "activity"):
            interaction = request(999)
            await self.group.get_command(name).callback(interaction)
            self.assertTrue(interaction.response.send_message.call_args.kwargs["ephemeral"])
            interaction.response.defer.assert_not_awaited()
        interaction = request(999)
        await self.group.get_command("start").callback(interaction, "goal", None)
        self.assertTrue(interaction.response.send_message.call_args.kwargs["ephemeral"])

    async def test_missing_owner_disables_controls(self):
        with patch.dict("os.environ", {"ARIES_OWNER_ID": ""}):
            interaction = request()
            await self.group.get_command("stop").callback(interaction)
        self.assertIn("ARIES_OWNER_ID", interaction.response.send_message.call_args.args[0])

    async def test_start_validates_channel_and_passes_explicit_action_permission(self):
        channel = SimpleNamespace(id=789, guild=SimpleNamespace(id=456, me=Mock()), mention="<#789>",
                                  permissions_for=Mock(return_value=SimpleNamespace(view_channel=True, send_messages=True)))
        interaction = request()
        with patch.object(self.bot.autonomy, "start", new=AsyncMock()) as start:
            await self.group.get_command("start").callback(interaction, "Check public news", channel, 15, True)
        self.assertTrue(interaction.response.defer.call_args.kwargs["ephemeral"])
        self.assertEqual(start.call_args.args, ("123", "456", "789", "Check public news", 15, True))
        channel.guild.id = 999
        with patch.object(self.bot.autonomy, "start", new=AsyncMock()) as start:
            await self.group.get_command("start").callback(request(), "goal", channel)
        start.assert_not_awaited()

    async def test_status_and_activity_are_private_and_owner_scoped(self):
        with patch("commands.autonomy_command.get_autonomy_state", new=AsyncMock(return_value=None)):
            interaction = request()
            await self.group.get_command("status").callback(interaction)
            self.assertTrue(interaction.response.defer.call_args.kwargs["ephemeral"])
        with patch("commands.autonomy_command.get_autonomy_actions", new=AsyncMock(return_value=[])) as actions:
            interaction = request()
            await self.group.get_command("activity").callback(interaction)
        actions.assert_awaited_once_with(10, "123")


class PublicPageTests(unittest.TestCase):
    def dns(self, ip):
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    def test_private_metadata_loopback_reserved_and_multicast_addresses_are_blocked(self):
        for ip in ("127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254", "::1", "fc00::1", "224.0.0.1", "0.0.0.0"):
            with self.subTest(ip=ip), patch("clients.page_client.socket.getaddrinfo", return_value=self.dns(ip)):
                with self.assertRaises(ValueError):
                    public_page_target("https://example.com/")

    def test_unsupported_urls_ports_credentials_and_mixed_dns_are_blocked(self):
        for url in ("file:///etc/passwd", "https://user:pass@example.com/", "https://example.com:8080/", "https://example.com/\nHeader", "ftp://example.com"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                public_page_target(url)
        with patch("clients.page_client.socket.getaddrinfo", return_value=self.dns("8.8.8.8") + self.dns("127.0.0.1")):
            with self.assertRaises(ValueError):
                public_page_target("https://example.com/")

    def test_public_page_pins_dns_and_bounds_text_without_forwarding_credentials(self):
        headers = Message()
        headers["Content-Type"] = "text/plain; charset=utf-8"
        response = Mock(status=200, headers=headers)
        response.getheader.side_effect = lambda key, default="": {"Content-Type": "text/plain", "Content-Encoding": "identity"}.get(key, default)
        response.read.return_value = b"a" * 5000
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("clients.page_client.socket.getaddrinfo", return_value=self.dns("8.8.8.8")), patch(
            "clients.page_client.socket.create_connection"
        ) as connect, patch("clients.page_client.http.client.HTTPConnection", return_value=connection):
            text = fetch_page_text("http://example.com/news")
        self.assertEqual(len(text), 3000)
        self.assertEqual(connect.call_args.args[0], ("8.8.8.8", 80))
        self.assertNotIn("Authorization", connection.request.call_args.kwargs["headers"])
        self.assertNotIn("Cookie", connection.request.call_args.kwargs["headers"])
        connection.close.assert_called_once()

    def test_redirect_to_private_network_is_blocked_before_connection(self):
        response = Mock(status=302)
        response.getheader.return_value = "http://127.0.0.1/private"
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("clients.page_client.socket.getaddrinfo", side_effect=[self.dns("8.8.8.8"), self.dns("127.0.0.1")]), patch(
            "clients.page_client.socket.create_connection"
        ) as connect, patch("clients.page_client.http.client.HTTPConnection", return_value=connection):
            self.assertEqual(fetch_page_text("http://example.com/redirect"), "")
        self.assertEqual(connect.call_count, 1)

    def test_oversized_downloads_are_discarded_and_tls_uses_original_hostname(self):
        response = Mock(status=200)
        response.getheader.side_effect = lambda key, default="": {"Content-Type": "text/html", "Content-Encoding": "identity"}.get(key, default)
        response.read.return_value = b"a" * (512 * 1024 + 1)
        connection = Mock()
        connection.getresponse.return_value = response
        context = Mock()
        with patch("clients.page_client.socket.getaddrinfo", return_value=self.dns("8.8.8.8")), patch(
            "clients.page_client.socket.create_connection"
        ), patch("clients.page_client.http.client.HTTPConnection", return_value=connection), patch(
            "clients.page_client.ssl.create_default_context", return_value=context
        ):
            self.assertEqual(fetch_page_text("https://example.com/large"), "")
        self.assertEqual(context.wrap_socket.call_args.kwargs["server_hostname"], "example.com")
        response.read.assert_called_once_with(512 * 1024 + 1)


if __name__ == "__main__":
    unittest.main()
