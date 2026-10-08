import asyncio
import requests
import base64

from configurations.prompts.summarise_prompt import get_summarise_prompt

async def summarise_response(history, prompt, image_data: bytes | None = None):
    messages = [
        {"role": "system", "content": get_summarise_prompt()}
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
            "options": {
                "num_predict": 256
            }
        },
        timeout=240
    )

    response.raise_for_status()
    return response.json()
