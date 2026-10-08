import asyncio
import requests
import base64

from configurations.prompts.system_prompt import get_system_prompt
from configurations.tools import poll_tool, reminder_tool, web_search_tool

async def ollama_response(history, prompt, image_data: bytes | None = None):
    messages = [
        {"role": "system", "content": get_system_prompt()}
    ]

    messages.extend(
        {"role": message.role, "content": message.content}
        for message in history
    )

    user_message = {
        "role": "user",
        "content": prompt
    }

    if image_data is not None:
        user_message["images"] = [
            base64.b64encode(image_data).decode("ascii")
        ]

    messages.append(user_message)

    response = await asyncio.to_thread(
        requests.post,
        "http://localhost:11434/api/chat",
        json={
            "model": "gemma4:e4b",
            "messages": messages,
            "stream": False,
            "tools": [poll_tool, reminder_tool, web_search_tool],
            "think": False,
            "options": {
                "num_predict": 256
            }
        },
        timeout=240
    )

    response.raise_for_status()
    data = response.json()

    def tokens_per_second(count, duration_ns):
        return count * 1_000_000_000 / duration_ns if duration_ns else 0

    message = data.get("message", {})
    thinking = message.get("thinking") or ""

    print(
        f"Ollama: total={data.get('total_duration', 0) / 1e9:.2f}s | "
        f"load={data.get('load_duration', 0) / 1e9:.2f}s | "
        f"prompt={data.get('prompt_eval_count', 0)} tokens, "
        f"{data.get('prompt_eval_duration', 0) / 1e9:.2f}s "
        f"({tokens_per_second(data.get('prompt_eval_count', 0), data.get('prompt_eval_duration', 0)):.1f} tok/s) | "
        f"output={data.get('eval_count', 0)} tokens, "
        f"{data.get('eval_duration', 0) / 1e9:.2f}s "
        f"({tokens_per_second(data.get('eval_count', 0), data.get('eval_duration', 0)):.1f} tok/s) | "
        f"thinking={len(thinking)} chars"
    )
