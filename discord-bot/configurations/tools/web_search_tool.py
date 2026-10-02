web_search_tool = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web when the user asks for current or up-to-date information.",
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