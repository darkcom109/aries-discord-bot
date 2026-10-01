poll_tool = {
    "type": "function",
    "function": {
        "name": "create_poll",
        "description": (
            "Create a Discord poll when the user asks for one. "
            "Include a clear question and 2 to 10 answer choices. "
            "If the poll topic is unclear, ask the user to clarify instead."
        ),
        "parameters": {
            "type": "object",
            "required": ["question", "options"],
            "properties": {
                "question": {"type": "string"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        }
    }
}