import asyncio
import requests
from clients.web_search_client import web_search_response
from database import save_message

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
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "content": result.get("content", "")[:500]
        }
        for result in data.get("results", [])[:5]
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

    results_text = "\n\n".join(
        f"Title: {result['title']}\n"
        f"URL: {result['url']}\n"
        f"Snippet: {result['content']}"
        for result in results
    )

    print(results_text)

    response = await web_search_response(
                    f"Question: {query}\n\nSearch results:\n{results_text}\n\n"
                    "Answer the question and cite the URLs."
                )

    response = response["message"]["content"][:2000]

    await save_message(guild_id, channel_id, user_id, "assistant", response)

    await interaction.edit_original_response(
        content=response
    )
