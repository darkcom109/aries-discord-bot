web_search_tool = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the live web. Always use this for questions about the latest, current, today, recent events, or live news; do not answer those from memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The words or question to search for."
                }
            },
            "required": ["query"]
        }
    }
}
