import logging

import discord

from database import get_reminder_delivery, resolve_reminder_delivery
from configurations.helpers.response_helper import shorten_text

async def finish_reminder(
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

class SnoozeModal(discord.ui.Modal, title="Snooze reminder"):
    minutes = discord.ui.TextInput(
        label="Snooze for how many minutes? (1-10080)",
        default="10",
        max_length=5,
    )

    def __init__(self, delivery_id: int, parent_view: discord.ui.View | None = None):
        super().__init__()
        self.delivery_id = delivery_id
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            minutes = int(self.minutes.value.strip())
        except ValueError:
            minutes = 0

        if not 1 <= minutes <= 10080:
            await interaction.response.send_message(
                "Enter a whole number between 1 and 10080 minutes (7 days).",
                ephemeral=True,
            )
            return

        await finish_reminder(interaction, self.delivery_id, minutes * 60, self.parent_view)

    async def on_error(self, interaction, error):
        logging.getLogger(__name__).error(
            "Custom snooze failed", exc_info=(type(error), error, error.__traceback__)
        )
        if interaction.response.is_done():
            await interaction.followup.send(
                "I couldn't snooze that reminder. Please try again.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "I couldn't snooze that reminder. Please try again.", ephemeral=True
            )

class ReminderView(discord.ui.View):
    def __init__(self, delivery_id: int):
        super().__init__(timeout=None)
        self.delivery_id = delivery_id
        self.snooze.custom_id = f"aries:reminder:{delivery_id}:snooze"
        self.custom_snooze.custom_id = f"aries:reminder:{delivery_id}:custom"
        self.dismiss.custom_id = f"aries:reminder:{delivery_id}:dismiss"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        delivery = await get_reminder_delivery(self.delivery_id)

        if delivery is None or delivery.user_id != str(interaction.user.id):
            await interaction.response.send_message(
                "Only the person who set this reminder can use these controls.",
                ephemeral=True,
            )
            return False

        if delivery.resolved:
            await interaction.response.send_message(
                "This reminder has already been snoozed or dismissed.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.select(
        placeholder="Snooze reminder...",
        options=[
            discord.SelectOption(label="5 minutes", value="300"),
            discord.SelectOption(label="10 minutes", value="600"),
            discord.SelectOption(label="30 minutes", value="1800"),
            discord.SelectOption(label="1 hour", value="3600"),
            discord.SelectOption(label="Tomorrow (24 hours)", value="86400"),
        ],
        row=0,
    )
    async def snooze(self, interaction: discord.Interaction, select: discord.ui.Select):
        await finish_reminder(interaction, self.delivery_id, int(select.values[0]), self)

    @discord.ui.button(label="Custom snooze", style=discord.ButtonStyle.primary, row=1)
    async def custom_snooze(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SnoozeModal(self.delivery_id, self))

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary, row=1)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button):
        await finish_reminder(interaction, self.delivery_id, view=self)

    async def on_error(self, interaction, error, item):
        logging.getLogger(__name__).error(
            "Reminder control failed", exc_info=(type(error), error, error.__traceback__)
        )
        if interaction.response.is_done():
            await interaction.followup.send(
                "I couldn't update that reminder. Please try again.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "I couldn't update that reminder. Please try again.", ephemeral=True
            )
