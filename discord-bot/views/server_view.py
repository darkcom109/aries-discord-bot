import discord

from configurations.helpers.server_helper import server_embed
from .monitor_view import MonitorView


class ServerView(MonitorView):
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        snapshot = await self.monitor.snapshot()
        await interaction.edit_original_response(
            embed=server_embed(snapshot), view=self, allowed_mentions=discord.AllowedMentions.none(),
        )
