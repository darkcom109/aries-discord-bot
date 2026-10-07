import time

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
    delay_minutes = arguments.get("delay_minutes")

    if (
        not isinstance(content, str)
        or not content.strip()
        or not isinstance(delay_minutes, int)
        or isinstance(delay_minutes, bool)
        or not 1 <= delay_minutes <= 43200
    ):
        await interaction.edit_original_response(
            content="Please provide a reminder and a delay between 1 minute and 30 days."
        )
        return

    content = content.strip()
    due_at = int(time.time() + delay_minutes * 60)

    reminder_id = await save_reminder(
        guild_id,
        channel_id,
        user_id,
        content,
        due_at
    )

    unit = "minute" if delay_minutes == 1 else "minutes"
    confirmation = (
        f"I'll remind you in {delay_minutes} {unit}: "
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
