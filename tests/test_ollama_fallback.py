import asyncio
import base64
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "discord-bot"))

from clients import ollama_client
from clients.generate_notes_client import generate_notes
from clients.source_client import source_response
from clients.summarise_client import summarise_response
from clients.web_search_client import web_search_response


def response(status=200, data=None, headers=None, text=""):
    result = Mock(status_code=status, headers=headers or {}, text=text)
    result.json.return_value = data if data is not None else {"message": {"role": "assistant", "content": "Done"}}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}", response=result)
    return result


class OllamaFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ollama_client.cloud_retry_at = 0
        ollama_client.local_locks.clear()
        environment = patch.dict("os.environ", {
            "OLLAMA_API_KEY": "fake-cloud-key", "OLLAMA_FALLBACK_ENABLED": "true",
            "OLLAMA_LOCAL_API_URL": "http://127.0.0.1:11434/api/chat", "OLLAMA_LOCAL_MODEL": "qwen3.5:2b",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(setattr, ollama_client, "cloud_retry_at", 0)

    async def test_normal_requests_stay_cloud_with_cap_and_thinking_disabled(self):
        with patch.object(ollama_client.requests, "post", return_value=response()) as post:
            data = await ollama_client.ollama_request([{"role": "user", "content": "Hello"}])
        self.assertEqual(data["aries_backend"], "cloud")
        self.assertEqual(post.call_args.args[0], "https://ollama.com/api/chat")
        self.assertEqual(post.call_args.kwargs["headers"], {"Authorization": "Bearer fake-cloud-key"})
        self.assertFalse(post.call_args.kwargs["json"]["think"])
        self.assertEqual(post.call_args.kwargs["json"]["options"]["num_predict"], 256)

    async def test_quota_fallback_preserves_images_tools_and_conversation_without_cloud_key(self):
        messages = [{"role": "user", "content": "Look", "images": [base64.b64encode(b"image").decode()]}]
        tools = [{"type": "function", "function": {"name": "web_search"}}]
        with patch.object(ollama_client.requests, "post", side_effect=[response(429), response()]) as post:
            data = await ollama_client.ollama_request(messages, tools=tools, max_tokens=512)
        local = post.call_args
        self.assertEqual(local.args[0], "http://127.0.0.1:11434/api/chat")
        self.assertNotIn("headers", local.kwargs)
        self.assertNotIn("fake-cloud-key", repr(local))
        self.assertEqual(local.kwargs["json"]["model"], "qwen3.5:2b")
        self.assertEqual(local.kwargs["json"]["messages"], messages)
        self.assertEqual(local.kwargs["json"]["tools"], tools)
        self.assertEqual(data["aries_backend"], "local")

    async def test_circuit_skips_exhausted_cloud_then_retries_after_cooldown(self):
        clock = SimpleNamespace(monotonic=Mock(return_value=100.0))
        with patch.object(ollama_client, "time", clock), patch.object(ollama_client.requests, "post", side_effect=[
            response(429, headers={"Retry-After": "120"}), response(), response(), response(),
        ]) as post:
            await ollama_client.ollama_request([])
            await ollama_client.ollama_request([])
            self.assertEqual(post.call_count, 3)
            self.assertEqual(ollama_client.cloud_retry_at, 220)
            clock.monotonic.return_value = 221
            result = await ollama_client.ollama_request([])
        self.assertEqual(result["aries_backend"], "cloud")
        self.assertEqual(post.call_args.args[0], "https://ollama.com/api/chat")

    async def test_auth_missing_model_and_malformed_payload_errors_are_not_masked(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status), patch.object(ollama_client.requests, "post", return_value=response(status)) as post:
                with self.assertRaises(requests.HTTPError):
                    await ollama_client.ollama_request([])
                self.assertEqual(post.call_count, 1)

    async def test_usage_forbidden_server_errors_and_network_failures_fall_back(self):
        failures = [response(402), response(403, text="weekly usage limit exceeded"), response(503), requests.Timeout()]
        for failure in failures:
            ollama_client.cloud_retry_at = 0
            with self.subTest(failure=type(failure).__name__), patch.object(ollama_client.requests, "post", side_effect=[failure, response()]):
                self.assertEqual((await ollama_client.ollama_request([]))["aries_backend"], "local")

    async def test_fallback_can_be_disabled(self):
        with patch.dict("os.environ", {"OLLAMA_FALLBACK_ENABLED": "false"}), patch.object(ollama_client.requests, "post", return_value=response(429)) as post:
            with self.assertRaises(requests.HTTPError):
                await ollama_client.ollama_request([])
        self.assertEqual(post.call_count, 1)

    async def test_backup_missing_has_safe_actionable_error(self):
        with patch.object(ollama_client.requests, "post", side_effect=[response(429), response(404)]):
            with self.assertRaisesRegex(ollama_client.OllamaUnavailable, "ollama pull qwen3.5:2b") as caught:
                await ollama_client.ollama_request([])
        self.assertNotIn("fake-cloud-key", str(caught.exception))

    async def test_invalid_response_is_not_returned_as_a_success(self):
        for data in ({"error": "failed"}, {"message": "wrong"}, []):
            with self.subTest(data=data), patch.object(ollama_client.requests, "post", return_value=response(data=data)):
                with self.assertRaises(ollama_client.OllamaUnavailable):
                    await ollama_client.ollama_request([])

    async def test_every_ai_client_uses_the_same_backup(self):
        calls = [lambda: web_search_response("question"), lambda: generate_notes("source", "lecture.pdf"),
                 lambda: summarise_response([], "summarise"), lambda: source_response("source", "question")]
        with patch.object(ollama_client.requests, "post", side_effect=[response(429)] + [response()] * 4) as post:
            for call in calls:
                await call()
        self.assertEqual(post.call_count, 5)
        self.assertTrue(all("headers" not in call.kwargs for call in post.call_args_list[1:]))

    async def test_cancelled_caller_keeps_local_slot_until_request_thread_exits(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def fake_thread(*args, **kwargs):
            started.set()
            await release.wait()
            return response()

        ollama_client.cloud_retry_at = float("inf")
        with patch.object(ollama_client.asyncio, "to_thread", side_effect=fake_thread):
            task = asyncio.create_task(ollama_client.ollama_request([]))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            lock = ollama_client.local_locks[asyncio.get_running_loop()]
            self.assertTrue(lock.locked())
            release.set()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertFalse(lock.locked())


if __name__ == "__main__":
    unittest.main()
