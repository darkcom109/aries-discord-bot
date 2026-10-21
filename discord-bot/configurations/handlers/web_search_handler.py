import asyncio
import requests
from clients.page_client import fetch_page_text
from clients.web_search_client import web_search_response
from database import save_message
from configurations.helpers.response_helper import send_answer

async def web_search(query: str) -> list[dict[str, str]]:
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
            "title": str(result.get("title") or "")[:200],
            "url": str(result.get("url") or "")[:2000],
            "content": str(result.get("content") or "")[:500]
        }
        for result in data.get("results", [])[:5]
        if isinstance(result, dict)
    ]

async def handle_web_search(
    interaction,
    function,
    guild_id,
    channel_id,
    user_id
):
    arguments = function.get("arguments", {})

    query = arguments.get("query")

    results = await web_search(query)

    page_texts = await asyncio.gather(
        *(
            asyncio.to_thread(fetch_page_text, result["url"])
            for result in results[:3]
        )
    )

    for result, page_text in zip(results[:3], page_texts):
        result["page_text"] = page_text or result["content"]

    results_text = "\n\n".join(
        f"Title: {result['title']}\n"
        f"URL: {result['url']}\n"
        f"Content: {result.get('page_text') or result['content']}"
        for result in results
    )

    response = await web_search_response(
                    f"Question: {query}\n\nSearch results:\n{results_text}\n\n"
                    "Answer the question and cite the URLs."
                )

    response = response["message"].get("content") or "I couldn't produce an answer from those results."

    await save_message(guild_id, channel_id, user_id, "assistant", response)

    await send_answer(interaction, response)
