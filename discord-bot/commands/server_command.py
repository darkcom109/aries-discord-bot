import discord

from clients.server_client import MonitorError
from configurations.helpers.server_helper import check_monitor_owner, server_embed
from views import ServerView


def register_server(bot):
    @bot.commands.command(name="server", description="Owner only: view private host metrics and service status")
    async def server(interaction: discord.Interaction):
        if not await check_monitor_owner(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            snapshot = await bot.monitor.snapshot()
        except MonitorError as error:
            await interaction.edit_original_response(content=str(error), allowed_mentions=discord.AllowedMentions.none())
            return
        await interaction.edit_original_response(
            embed=server_embed(snapshot), view=ServerView(str(interaction.user.id), bot.monitor),
            allowed_mentions=discord.AllowedMentions.none(),
        )
