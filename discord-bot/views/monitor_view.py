import logging

import discord

from clients.server_client import MonitorError
from configurations.helpers.server_helper import check_monitor_owner


class MonitorView(discord.ui.View):
    def __init__(self, user_id: str, monitor):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.monitor = monitor

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_monitor_owner(interaction, self.user_id)

    async def on_error(self, interaction, error, item):
        # Exception text can itself contain logs or credentials; don't echo it.
        logging.getLogger(__name__).error("Monitoring control failed: %s", type(error).__name__)
        message = str(error) if isinstance(error, MonitorError) else "I couldn't refresh monitoring. Please try the command again."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        else:
            await interaction.response.send_message(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
