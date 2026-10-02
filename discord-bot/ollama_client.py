import asyncio
import requests

from configurations.system_prompt import system_prompt
from configurations.tools import poll_tool, reminder_tool, web_search_tool

async def ollama_response(history, prompt):
    messages = [
        {"role": "system", "content": system_prompt}
    ]

    messages.extend(
        {"role": message.role, "content": message.content}
        for message in history
    )

    messages.append({"role": "user", "content": prompt})

    response = await asyncio.to_thread(
        requests.post,
        "http://localhost:11434/api/chat",
        json={
            "model": "qwen3:8b",
            "messages": messages,
            "stream": False,
            "tools": [poll_tool, reminder_tool, web_search_tool]
        },
        timeout=240
    )

    response.raise_for_status()
    return response.json()