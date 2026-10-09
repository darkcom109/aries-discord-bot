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
        ),
        "parameters": {
            "type": "object",
            "required": ["content", "time"],
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The specific thing the user wants to be reminded about; never a clarification question"
                },
                "time": {
                    "type": "string",
                    "description": "Scheduled date and time in YYYY-MM-DDTHH:MM format, "
                                   "using Europe/London. Example: 2026-10-10T16:00"
                }
            }
        }
    }
}
