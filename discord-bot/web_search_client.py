import asyncio
import requests

async def web_search_response(prompt):
    messages = [
        {"role": "system", "content": "Summarise the web search results and provide it in a readable format for users"}
    ]

    messages.append({"role": "user", "content": prompt})

    response = await asyncio.to_thread(
        requests.post,
        "http://localhost:11434/api/chat",
        json={
            "model": "qwen3:8b",
            "messages": messages,
            "stream": False,
        },
        timeout=240
    )

    response.raise_for_status()
    return response.json()