reminder_tool = {
    "type": "function",
    "function": {
        "name": "create_reminder",
        "description": (
            "Create a one-time reminder only when the user has specified both "
            "what to remember and a time or minute, such as 'in 30 minutes'. "
            "If either detail is missing, ask a follow-up question and do not "
            "call this tool; never use that question as the reminder content. "
            "If you are unsure of the time or minute ask a clarifying question."
            "You can make a list of reminders if there are multiple, you are"
            "returning a list of reminders."
        ),
        "parameters": {
            "type": "object",
            "required": ["content", "time"],
            "properties": {
                "reminders": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["content", "time"],
                        "properties": {
                            "content": {"type": "string"},
                            "time": {
                                "type": "string",
                                "description": "YYYY-MM-DDTHH:MM:SS, using Europe/London"
                            },
                            "repeat": {
                                "type": "string",
                                "enum": ["none", "daily", "weekly"]
                            }
                        }
                    }
                }
            }
        }
    }
}
