reminder_tool = {
    "type": "function",
    "function": {
        "name": "create_reminder",
        "description": (
            "Create a one-time reminder only when the user has specified both "
            "what to remember and a relative delay, such as 'in 30 minutes'. "
            "If either detail is missing, ask a follow-up question and do not "
            "call this tool; never use that question as the reminder content. "
            "If the user gives a clock time, date, or unclear delay, ask for "
            "clarification instead of guessing."
        ),
        "parameters": {
            "type": "object",
            "required": ["content", "delay_minutes"],
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The specific thing the user wants to be reminded about; never a clarification question"
                },
                "delay_minutes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 43200,
                    "description": "A clear relative delay in minutes from now"
                }
            }
        }
    }
}
