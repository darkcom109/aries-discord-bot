web_search_tool = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the live web for latest/current information or news; do not answer those from memory. Use get_tfl instead for live London transport.",
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
