import asyncio
import requests
import trafilatura
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

def fetch_page_text(url):
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "AriesDiscordBot/1.0"},
            timeout=10
        )
        response.raise_for_status()
    
        if "html" not in response.headers.get("Content-Type", "").lower():
            return ""
    
        text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False
        )
    
        return (text or "")[:3000]
    
    except requests.RequestException:
        return ""

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

    response = response["message"]["content"][:2000]

    await save_message(guild_id, channel_id, user_id, "assistant", response)

    await interaction.edit_original_response(
        content=response
    )
