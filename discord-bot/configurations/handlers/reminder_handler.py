from datetime import datetime

from database import save_reminder, save_message

async def handle_create_reminder(
    interaction,
    function,
    guild_id,
    channel_id,
    user_id
):
    arguments = function.get("arguments", {})

    if not isinstance(arguments, dict):
        await interaction.edit_original_response(
            content="I couldn't understand the reminder details"
        )
        return

    reminders = arguments.get("reminders", [])

    if reminders == []:
        await interaction.edit_original_response(
            content="Please provide a valid reminder"
        )
        return

    for reminder in reminders:

        content = reminder.get("content")
        reminder_time = reminder.get("time")
        repeat = reminder.get("repeat", "none")

        if (
            not isinstance(content, str)
            or not content.strip()
            or not isinstance(reminder_time, str)
            or isinstance(reminder_time, bool)
            or datetime.now().strftime("%Y-%m-%dT%H:%M:%S") >= reminder_time
            or repeat not in ["none", "daily", "weekly"]
        ):
            await interaction.edit_original_response(
                content="Please provide a valid reminder"
            )
            return

        content = content.strip()

        target = datetime.strptime(reminder_time, "%Y-%m-%dT%H:%M:%S")

        due_at = int(target.timestamp())

        await save_reminder(
            guild_id,
            channel_id,
            user_id,
            content,
            due_at,
            repeat,
        )

    confirmation = "\n".join(
        f"I have scheduled: {reminder['content']}"
        for reminder in reminders
    )

    await interaction.edit_original_response(
        content=confirmation
    )

    await save_message(
        guild_id,
        channel_id,
        user_id,
        "assistant",
        confirmation
    )
