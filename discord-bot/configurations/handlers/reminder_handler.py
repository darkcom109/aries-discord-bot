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

    content = arguments.get("content")
    reminder_time = arguments.get("time")

    if (
        not isinstance(content, str)
        or not content.strip()
        or not isinstance(reminder_time, str)
        or isinstance(reminder_time, bool)
        or datetime.now().strftime("%Y-%m-%dT%H:%M") >= reminder_time
    ):
        await interaction.edit_original_response(
            content="Please provide a valid reminder"
        )
        return

    content = content.strip()

    target = datetime.strptime(reminder_time, "%Y-%m-%dT%H:%M")

    due_at = int(target.timestamp())

    reminder_id = await save_reminder(
        guild_id,
        channel_id,
        user_id,
        content,
        due_at
    )

    confirmation = (
        f"I'll remind you at {reminder_time}: "
        f"{content} (reminder #{reminder_id})"
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
