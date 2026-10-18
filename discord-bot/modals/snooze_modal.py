import logging

import discord

from configurations.handlers.reminder_action_handler import handle_reminder_action

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

        await handle_reminder_action(
            interaction, self.delivery_id, minutes * 60, self.parent_view
        )

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
