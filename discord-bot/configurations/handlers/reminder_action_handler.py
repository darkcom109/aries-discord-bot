import discord

from database import get_reminder_delivery, resolve_reminder_delivery
from configurations.helpers.response_helper import shorten_text

async def handle_reminder_action(
    interaction: discord.Interaction,
    delivery_id: int,
    snooze_seconds: int | None = None,
    view: discord.ui.View | None = None,
):
    await interaction.response.defer()
    resolved = await resolve_reminder_delivery(
        delivery_id,
        str(interaction.user.id),
        snooze_seconds,
    )

    if not resolved:
        await interaction.followup.send(
            "That reminder has already been handled, or it isn't yours.",
            ephemeral=True,
        )
        return False

    if view is not None:
        view.stop()

    delivery = await get_reminder_delivery(delivery_id)
    status = (
        f"Snoozed for {snooze_seconds // 60} minutes."
        if snooze_seconds is not None
        else "Reminder dismissed."
    )
    content = f"{status}\n{delivery.content}" if delivery is not None else status

    await interaction.edit_original_response(
        content=shorten_text(content),
        view=None,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    return True
