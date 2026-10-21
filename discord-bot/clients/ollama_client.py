import asyncio
import requests
import base64
import time
import weakref

from configurations.prompts.system_prompt import get_system_prompt
from configurations.tools import poll_tool, reminder_tool, web_search_tool, tfl_tool
from configurations.ollama_config import (
    OLLAMA_API_URL, OLLAMA_MODEL, get_ollama_headers,
    local_ollama_settings, ollama_fallback_enabled,
)


class OllamaUnavailable(RuntimeError):
    pass


# A shared circuit breaker avoids hitting an exhausted cloud allowance on every request.
cloud_retry_at = 0.0
local_locks = weakref.WeakKeyDictionary()


def retry_delay(response) -> int:
    try:
        return max(60, min(86400, int(response.headers.get("Retry-After", "900"))))
    except (TypeError, ValueError):
        return 900


def can_fall_back(response) -> bool:
    if response.status_code in {402, 429, 500, 502, 503, 504}:
        return True
    if response.status_code == 403:
        # Do not hide invalid keys, missing models or malformed requests behind a fallback.
        return any(word in response.text[:2000].lower() for word in ("quota", "usage limit", "credits", "usage exceeded"))
    return False


def ollama_backend_status() -> str:
    if ollama_fallback_enabled() and time.monotonic() < cloud_retry_at:
        return f"Local backup selected: {local_ollama_settings()[1]} (cloud cooldown)"
    return f"Cloud selected: {OLLAMA_MODEL}"

async def ollama_response(history, prompt, image_data: bytes | None = None):
    messages = [
        {"role": "system", "content": get_system_prompt()}
    ]

    messages.extend(
        {"role": message.role, "content": message.content}
        for message in history
    )

    user_message: dict[str, str | list[str]] = {
        "role": "user",
        "content": prompt
    }

    if image_data is not None:
        user_message["images"] = [
            base64.b64encode(image_data).decode("ascii")
        ]

    messages.append(user_message)

    return await ollama_request(
        messages,
        tools=[poll_tool, reminder_tool, web_search_tool, tfl_tool],
    )

async def ollama_request(messages, tools=None, max_tokens: int = 256):
    global cloud_retry_at
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"num_predict": max_tokens},
    }

    if tools:
        payload["tools"] = tools

    data = None
    use_local = ollama_fallback_enabled() and time.monotonic() < cloud_retry_at
    if not use_local:
        try:
            response = await asyncio.to_thread(
                requests.post, OLLAMA_API_URL, headers=get_ollama_headers(),
                json=payload, timeout=(10, 180),
            )
        except (requests.ConnectionError, requests.Timeout):
            if not ollama_fallback_enabled():
                raise OllamaUnavailable("Ollama Cloud is unreachable and local fallback is disabled.") from None
            cloud_retry_at = time.monotonic() + 60
            use_local = True
        else:
            if can_fall_back(response) and ollama_fallback_enabled():
                cloud_retry_at = time.monotonic() + retry_delay(response)
                print(f"Ollama: cloud unavailable (HTTP {response.status_code}); switching to local fallback.")
                use_local = True
            else:
                response.raise_for_status()
                data = response.json()

    if use_local:
        url, model = local_ollama_settings()
        local_payload = {**payload, "model": model}
        loop = asyncio.get_running_loop()
        lock = local_locks.setdefault(loop, asyncio.Lock())
        await lock.acquire()
        # Cancelling an await cannot stop a requests thread. Keep the local slot held
        # until that thread really exits, even if autonomous mode is stopped meanwhile.
        worker = asyncio.create_task(asyncio.to_thread(
            requests.post, url, json=local_payload, timeout=(5, 180),
        ))

        def release_local_slot(task):
            lock.release()
            if not task.cancelled():
                task.exception()  # Retrieve failures even when the original caller was cancelled.

        worker.add_done_callback(release_local_slot)
        try:
            # Never forward the cloud API key to the local Ollama endpoint.
            response = await asyncio.shield(worker)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            raise OllamaUnavailable(
                "Ollama Cloud is unavailable and the local backup failed. "
                f"Check that local Ollama is running and run `ollama pull {model}` on the bot host."
            ) from None

    if not isinstance(data, dict) or data.get("error") or not isinstance(data.get("message"), dict):
        raise OllamaUnavailable("Ollama returned an invalid chat response.")
    data["aries_backend"] = "local" if use_local else "cloud"

    def tokens_per_second(count, duration_ns):
        return count * 1_000_000_000 / duration_ns if duration_ns else 0

    message = data.get("message", {})
    thinking = message.get("thinking") or ""

    print(
        f"Ollama [{data['aries_backend']}]: total={data.get('total_duration', 0) / 1e9:.2f}s | "
        f"load={data.get('load_duration', 0) / 1e9:.2f}s | "
        f"prompt={data.get('prompt_eval_count', 0)} tokens, "
        f"{data.get('prompt_eval_duration', 0) / 1e9:.2f}s "
        f"({tokens_per_second(data.get('prompt_eval_count', 0), data.get('prompt_eval_duration', 0)):.1f} tok/s) | "
        f"output={data.get('eval_count', 0)} tokens, "
        f"{data.get('eval_duration', 0) / 1e9:.2f}s "
        f"({tokens_per_second(data.get('eval_count', 0), data.get('eval_duration', 0)):.1f} tok/s) | "
        f"thinking={len(thinking)} chars"
    )

    return data
