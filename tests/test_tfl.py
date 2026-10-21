import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "discord-bot"))

import discord
import requests
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import database
from database import connection
from clients.tfl_client import TflClient, TflError
from clients.ollama_client import ollama_response
from configurations.handlers.tfl_handler import handle_get_tfl, tfl_answer
from configurations.handlers.tfl_watch_handler import handle_tfl_watches
from configurations.helpers.tfl_helper import (
    format_tfl_journeys,
    matching_tfl_lines,
    tfl_status_fingerprint,
    tfl_timestamp,
)
from commands import register_commands
from main import MyBot


def line_status(description="Good Service", reason=""):
    return {
        "id": "victoria", "name": "Victoria", "modeName": "tube",
        "lineStatuses": [{
            "id": 1, "statusSeverity": 10 if description == "Good Service" else 6,
            "statusSeverityDescription": description, "reason": reason,
        }],
    }


def response(data, status=200, headers=None):
    return SimpleNamespace(status_code=status, headers=headers or {}, json=Mock(return_value=data))


def interaction(user_id="123", channel=None):
    channel = channel or SimpleNamespace(id=456, send=AsyncMock())
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, create_dm=AsyncMock(return_value=channel)),
        response=SimpleNamespace(defer=AsyncMock()),
        edit_original_response=AsyncMock(),
    )


class TflClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = TflClient()
        self.env = patch.dict("os.environ", {"TFL_APP_KEY": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    async def test_requests_are_cached_and_share_inflight_work(self):
        with patch("clients.tfl_client.requests.get", return_value=response([line_status()])) as get:
            answers = await asyncio.gather(self.client.status("Victoria line"), self.client.status("victoria"))
        self.assertEqual(answers[0], answers[1])
        get.assert_called_once()
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        self.assertNotIn("app_key", get.call_args.kwargs["params"])
        self.assertIn("Good Service", answers[0])

    async def test_expired_cache_refetches_instead_of_reusing_stale_data(self):
        with patch("clients.tfl_client.requests.get", return_value=response([])) as get:
            await self.client.request("/example")
            self.client.cache[("/example", ())] = (0, [], 100)
            await self.client.request("/example")
        self.assertEqual(get.call_count, 2)

    async def test_optional_key_is_used_but_never_leaked_in_errors(self):
        with patch.dict("os.environ", {"TFL_APP_KEY": "private-test-key"}):
            with patch("clients.tfl_client.requests.get", return_value=response({}, 403)) as get:
                with self.assertRaises(TflError) as raised:
                    await self.client.request("/example")
        self.assertEqual(get.call_args.kwargs["params"]["app_key"], "private-test-key")
        self.assertNotIn("private-test-key", str(raised.exception))
        with patch("clients.tfl_client.requests.get", side_effect=requests.Timeout("URL contains private-test-key")):
            with self.assertRaises(TflError) as raised:
                await self.client.request("/example")
        self.assertNotIn("private-test-key", str(raised.exception))

    async def test_network_errors_and_bad_responses_are_user_friendly(self):
        cases = [response({}, 404), response({}, 500), response(None), response({}, 302)]
        invalid_json = response(None)
        invalid_json.json.side_effect = ValueError("bad JSON")
        cases.append(invalid_json)
        for item in cases:
            with self.subTest(status=item.status_code):
                with patch("clients.tfl_client.requests.get", return_value=item):
                    with self.assertRaises(TflError):
                        await self.client.request("/example", ttl=0)

    async def test_429_obeys_backoff_without_repeating_requests(self):
        with patch("clients.tfl_client.requests.get", return_value=response({}, 429, {"Retry-After": "120"})) as get:
            for _ in range(2):
                with self.assertRaises(TflError):
                    await self.client.request("/example")
        get.assert_called_once()

    async def test_local_rate_limit_stops_at_40_requests_per_minute(self):
        with patch("clients.tfl_client.requests.get", return_value=response([])) as get:
            for number in range(40):
                await self.client.request(f"/example/{number}")
            with self.assertRaises(TflError):
                await self.client.request("/example/41")
        self.assertEqual(get.call_count, 40)

    async def test_cache_size_is_bounded(self):
        with patch("clients.tfl_client.requests.get", return_value=response([])):
            for number in range(130):
                self.client.request_times.clear()
                await self.client.request(f"/example/{number}")
        self.assertEqual(len(self.client.cache), 128)

    async def test_unknown_line_and_missing_status_do_not_claim_good_service(self):
        unknown = line_status()
        unknown["lineStatuses"] = []
        with patch.object(self.client, "line_statuses", new=AsyncMock(return_value=([unknown], 100))):
            self.assertIn("Status unavailable", await self.client.status("Victoria"))
            with self.assertRaises(TflError):
                await self.client.status("made-up line")
            with self.assertRaises(TflError):
                await self.client.status(123)

    async def test_ambiguous_stop_shows_directions_instead_of_picking_first(self):
        matches = [
            {"id": "490000001A", "name": "Oxford Circus Station", "modes": ["bus"], "towards": "North"},
            {"id": "490000001B", "name": "Oxford Circus Station", "modes": ["bus"], "towards": "South"},
        ]
        with patch.object(self.client, "search_stops", new=AsyncMock(return_value=(matches, 100))):
            with patch.object(self.client, "request", new=AsyncMock()) as request:
                answer = await self.client.arrivals("Oxford Circus Station")
        request.assert_not_awaited()
        self.assertIn("North", answer)
        self.assertIn("South", answer)
        self.assertIn("490000001B", answer)

    async def test_specific_stop_name_resolves_and_arrivals_are_sorted_and_filtered(self):
        checked = 1_800_000_000
        predictions = [
            {"lineId": "victoria", "lineName": "Victoria", "timeToStation": 180, "destinationName": "Brixton", "platformName": "Southbound"},
            {"lineId": "central", "lineName": "Central", "timeToStation": 10},
            {"lineId": "victoria", "lineName": "Victoria", "timeToStation": 60, "destinationName": "Walthamstow"},
        ]
        matches = [{"id": "940GZZLUOXC", "name": "Oxford Circus Underground Station", "modes": ["tube"]}]
        with patch.object(self.client, "search_stops", new=AsyncMock(return_value=(matches, checked))):
            with patch.object(self.client, "request", new=AsyncMock(return_value=(predictions, checked))) as request:
                answer = await self.client.arrivals("Oxford Circus Underground Station", "Victoria line")
        self.assertEqual(request.call_args.args[0], "/StopPoint/940GZZLUOXC/Arrivals")
        self.assertLess(answer.index("Walthamstow"), answer.index("Brixton"))
        self.assertNotIn("Central", answer)
        self.assertIn(f"<t:{checked + 60}:R>", answer)

    async def test_empty_arrivals_do_not_report_cancellation(self):
        with patch.object(self.client, "request", new=AsyncMock(return_value=([], 100))):
            answer = await self.client.arrivals("490000001A")
        self.assertIn("does not necessarily mean", answer)

    async def test_journey_parameters_are_encoded_and_300_is_clarified(self):
        data = {"toLocationDisambiguation": {"disambiguationOptions": [
            {"parameterValue": "1000013", "place": {"commonName": "City of London, Bank"}},
        ]}}
        with patch("clients.tfl_client.requests.get", return_value=response(data, 300)) as get:
            answer = await self.client.journey("Waterloo/Station", "Bank")
        self.assertIn("Waterloo%2FStation/to/Bank", get.call_args.args[0])
        self.assertIn("1000013", answer)
        self.assertIn("Destination", answer)

    async def test_invalid_tool_arguments_and_missing_fields_do_not_make_http_requests(self):
        with patch("clients.tfl_client.requests.get") as get:
            for arguments in (None, [], {"action": "arrivals"}, {"action": "journey", "origin": "Bank"}, {"action": "watch"}):
                self.assertTrue(await tfl_answer(self.client, arguments))
        get.assert_not_called()

    async def test_tfl_tool_is_available_to_the_model(self):
        with patch("clients.ollama_client.ollama_request", new=AsyncMock(return_value={"message": {"content": "Hi"}})) as request:
            await ollama_response([], "Is the Victoria line running?")
        tools = request.call_args.kwargs["tools"]
        self.assertIn("get_tfl", [tool["function"]["name"] for tool in tools])


class TflHelperTests(unittest.TestCase):
    def test_status_fingerprint_ignores_ids_and_validity_but_tracks_real_changes(self):
        original = line_status()
        copy = deepcopy(original)
        copy["lineStatuses"][0].update(id=999, validityPeriods=[{"fromDate": "changed"}])
        self.assertEqual(tfl_status_fingerprint(original), tfl_status_fingerprint(copy))
        self.assertNotEqual(tfl_status_fingerprint(original), tfl_status_fingerprint(line_status("Minor Delays", "Signal failure")))
        self.assertIsNone(tfl_status_fingerprint({"lineStatuses": []}))

    def test_named_lines_and_modern_overground_groups(self):
        lines = [line_status(), {"id": "lioness", "name": "Lioness", "modeName": "overground"}, {"id": "mildmay", "name": "Mildmay", "modeName": "overground"}]
        self.assertEqual(matching_tfl_lines("Victoria line", lines)[0]["id"], "victoria")
        self.assertEqual(len(matching_tfl_lines("Overground", lines)), 2)

    def test_london_journey_times_respect_bst_and_winter_time(self):
        summer = tfl_timestamp("2026-10-19T10:00:00")
        winter = tfl_timestamp("2026-11-19T10:00:00")
        self.assertEqual(datetime.fromtimestamp(summer, timezone.utc).hour, 9)
        self.assertEqual(datetime.fromtimestamp(winter, timezone.utc).hour, 10)

    def test_journey_output_has_directions_and_disruption_warning(self):
        data = {"journeys": [{"startDateTime": "2026-10-19T10:00:00", "arrivalDateTime": "2026-10-19T10:30:00", "duration": 30, "legs": [
            {"instruction": {"summary": "<b>Take</b> the Victoria line"}, "isDisrupted": True},
        ]}]}
        answer = format_tfl_journeys(data, "Brixton", "Victoria", 100)
        self.assertIn("30 min", answer)
        self.assertIn("Take the Victoria line", answer)
        self.assertNotIn("<b>", answer)
        self.assertIn("Disruption/planned work", answer)


class TflStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = Path(__file__).resolve().parent / f".aries-tfl-test-{uuid4().hex}"
        self.directory.mkdir()
        self.addCleanup(shutil.rmtree, self.directory)
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{(self.directory / 'test.db').as_posix()}")
        self.addAsyncCleanup(self.engine.dispose)
        for item in (
            patch.object(connection, "engine", self.engine),
            patch.object(connection, "SessionFactory", async_sessionmaker(self.engine, expire_on_commit=False)),
        ):
            item.start()
            self.addCleanup(item.stop)
        await database.create_tables()
        self.bot = MyBot()
        register_commands(self.bot)
        self.addAsyncCleanup(self.bot.close)

    async def test_watches_are_private_unique_and_survive_reopening(self):
        first = await database.save_tfl_watch("owner", "456", "victoria", "Victoria", "initial")
        self.assertIsNotNone(first)
        self.assertIsNone(await database.save_tfl_watch("owner", "999", "victoria", "Victoria", "changed"))
        self.assertEqual(await database.get_user_tfl_watches("stranger"), [])
        self.assertFalse(await database.delete_user_tfl_watch("stranger", "victoria"))
        await self.engine.dispose()
        await database.create_tables()
        saved = (await database.get_user_tfl_watches("owner"))[0]
        self.assertEqual(saved.last_status, "initial")
        self.assertEqual(saved.channel_id, "456")
        self.assertTrue(await database.delete_user_tfl_watch("owner", "victoria"))

    async def test_alerts_send_only_on_change_and_not_after_restart(self):
        await database.save_tfl_watch("owner", "456", "victoria", "Victoria", tfl_status_fingerprint(line_status()))
        changed = line_status("Minor Delays", "Signal failure")
        channel = SimpleNamespace(send=AsyncMock())
        with patch.object(self.bot.tfl, "line_statuses", new=AsyncMock(return_value=([changed], 100))):
            with patch.object(self.bot, "get_partial_messageable", return_value=channel):
                await handle_tfl_watches(self.bot)
                await self.engine.dispose()
                await handle_tfl_watches(self.bot)
        channel.send.assert_awaited_once()
        self.assertIn("Signal failure", channel.send.call_args.args[0])
        self.assertEqual((await database.load_tfl_watches())[0].last_status, tfl_status_fingerprint(changed))

    async def test_no_watches_means_no_background_api_requests(self):
        with patch.object(self.bot.tfl, "line_statuses", new=AsyncMock()) as get:
            await handle_tfl_watches(self.bot)
        get.assert_not_awaited()

    async def test_missing_status_and_api_outage_do_not_generate_false_recovery(self):
        await database.save_tfl_watch("owner", "456", "victoria", "Victoria", "initial")
        with patch.object(self.bot.tfl, "line_statuses", new=AsyncMock(return_value=([], 100))):
            with patch.object(self.bot, "get_partial_messageable") as channel:
                await handle_tfl_watches(self.bot)
        channel.assert_not_called()
        with patch.object(self.bot.tfl, "line_statuses", new=AsyncMock(side_effect=TflError("offline"))):
            with self.assertLogs("configurations.handlers.tfl_watch_handler", level="WARNING"):
                await handle_tfl_watches(self.bot)
        self.assertEqual((await database.load_tfl_watches())[0].last_status, "initial")

    async def test_failed_dm_keeps_previous_snapshot_for_retry(self):
        await database.save_tfl_watch("owner", "456", "victoria", "Victoria", "initial")
        error = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "DMs disabled")
        channel = SimpleNamespace(send=AsyncMock(side_effect=error))
        with patch.object(self.bot.tfl, "line_statuses", new=AsyncMock(return_value=([line_status()], 100))):
            with patch.object(self.bot, "get_partial_messageable", return_value=channel):
                with self.assertLogs("configurations.handlers.tfl_watch_handler", level="WARNING"):
                    await handle_tfl_watches(self.bot)
        self.assertEqual((await database.load_tfl_watches())[0].last_status, "initial")

    async def test_slash_commands_register_and_defer_before_fetching(self):
        group = self.bot.commands.get_command("tfl")
        self.assertEqual({item.name for item in group.commands}, {"status", "stops", "arrivals", "journey", "watch", "watches", "unwatch"})
        request = interaction()

        async def status(line):
            request.response.defer.assert_awaited_once()
            return "Victoria: Good Service"

        with patch.object(self.bot.tfl, "status", new=status):
            await group.get_command("status").callback(request, "Victoria")
        self.assertTrue(request.response.defer.call_args.kwargs["ephemeral"])
        self.assertIn("Good Service", request.edit_original_response.call_args.kwargs["content"])

    async def test_watch_sends_optin_dm_and_saves_baseline(self):
        request = interaction()
        with patch.object(self.bot.tfl, "line_statuses", new=AsyncMock(return_value=([line_status()], 100))):
            await self.bot.commands.get_command("tfl").get_command("watch").callback(request, "Victoria")
        saved = await database.get_user_tfl_watches("123")
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].last_status, tfl_status_fingerprint(line_status()))
        request.user.create_dm.return_value.send.assert_awaited_once()

    async def test_blocked_initial_dm_does_not_leave_an_active_watch(self):
        error = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "DMs disabled")
        request = interaction(channel=SimpleNamespace(id=456, send=AsyncMock(side_effect=error)))
        with patch.object(self.bot.tfl, "line_statuses", new=AsyncMock(return_value=([line_status()], 100))):
            await self.bot.commands.get_command("tfl").get_command("watch").callback(request, "Victoria")
        self.assertEqual(await database.get_user_tfl_watches("123"), [])
        self.assertIn("Enable DMs", request.edit_original_response.call_args.kwargs["content"])

    async def test_unwatch_is_owner_scoped_and_works_without_tfl(self):
        await database.save_tfl_watch("123", "456", "victoria", "Victoria", "initial")
        group = self.bot.commands.get_command("tfl")
        with patch.object(self.bot.tfl, "request", new=AsyncMock()) as get:
            await group.get_command("unwatch").callback(interaction("stranger"), "Victoria")
            self.assertEqual(len(await database.get_user_tfl_watches("123")), 1)
            await group.get_command("unwatch").callback(interaction(), "Victoria line")
        self.assertEqual(await database.get_user_tfl_watches("123"), [])
        get.assert_not_awaited()

    async def test_ask_tool_handler_uses_same_client_and_records_answer(self):
        request = interaction()
        request.client = self.bot
        with patch.object(self.bot.tfl, "status", new=AsyncMock(return_value="Victoria: Good Service")):
            await handle_get_tfl(request, {"arguments": {"action": "status", "line": "Victoria"}}, "guild", "channel", "123")
        self.assertIn("Good Service", request.edit_original_response.call_args.kwargs["content"])
        history = await database.load_messages("guild", "channel")
        self.assertEqual(history[0].content, "Victoria: Good Service")

    async def test_ask_command_dispatches_the_tfl_tool_and_preserves_history(self):
        request = interaction()
        request.client = self.bot
        request.guild_id, request.channel_id = 1, 2
        result = {"message": {"tool_calls": [{"function": {"name": "get_tfl", "arguments": {"action": "status", "line": "Victoria"}}}]}}
        with patch("commands.ask_command.ollama_response", new=AsyncMock(return_value=result)):
            with patch.object(self.bot.tfl, "status", new=AsyncMock(return_value="Victoria: Good Service")):
                await self.bot.commands.get_command("ask").callback(request, "Is Victoria running?")
        history = await database.load_messages("1", "2")
        self.assertEqual([item.role for item in history], ["user", "assistant"])
        self.assertIn("Good Service", request.edit_original_response.call_args.kwargs["content"])

    async def test_mentions_run_tfl_tool_while_typing_and_reply_normally(self):
        bot_user = SimpleNamespace(id=999)
        typing = MagicMock()
        typing.__aenter__ = AsyncMock()
        typing.__aexit__ = AsyncMock(return_value=False)
        message = SimpleNamespace(
            author=SimpleNamespace(id=123, bot=False), guild=SimpleNamespace(id=1),
            channel=SimpleNamespace(id=2, typing=Mock(return_value=typing)),
            mentions=[bot_user], content="<@999> Is Victoria running?", attachments=[], reply=AsyncMock(),
        )
        result = {"message": {"tool_calls": [{"function": {"name": "get_tfl", "arguments": {"action": "status", "line": "Victoria"}}}]}}

        async def status(line):
            typing.__aenter__.assert_awaited_once()
            typing.__aexit__.assert_not_awaited()
            return "Victoria: Good Service"

        with patch.object(self.bot._connection, "user", bot_user):
            with patch("commands.discord_commands.ollama_response", new=AsyncMock(return_value=result)):
                with patch.object(self.bot.tfl, "status", new=status):
                    await self.bot.on_message(message)
        self.assertIn("Good Service", message.reply.call_args.args[0])
        self.assertEqual(len(await database.load_messages("1", "2")), 2)
        typing.__aexit__.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
