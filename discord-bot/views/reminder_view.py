import logging

import discord

from database import get_reminder_delivery
from configurations.handlers.reminder_action_handler import handle_reminder_action
from modals import SnoozeModal

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
        await handle_reminder_action(interaction, self.delivery_id, int(select.values[0]), self)

    @discord.ui.button(label="Custom snooze", style=discord.ButtonStyle.primary, row=1)
    async def custom_snooze(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SnoozeModal(self.delivery_id, self))

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary, row=1)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_reminder_action(interaction, self.delivery_id, view=self)

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
