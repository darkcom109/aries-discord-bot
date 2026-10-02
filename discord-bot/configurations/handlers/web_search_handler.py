import asyncio
import requests

async def handle_search_web(query: str) -> list[dict[str, str]] | None:
    response = await asyncio.to_thread(
        requests.get,
        "http://localhost:8088/search",
        params={"q": query, "format": "json"},
        timeout=15
    )
    response.raise_for_status()

    data = response.json()

    return [
        {
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "content": result.get("content", "")[:500]
        }
        for result in data.get("results", [])[:5]
    ]