from typing import Literal

import discord
from discord import app_commands

from clients.server_client import MonitorError
from configurations.helpers.server_helper import check_monitor_owner, logs_embed
from views import LogsView


def register_logs(bot):
    @bot.commands.command(name="logs", description="Owner only: view private Aries or SearXNG logs")
    @app_commands.describe(
        service="Predefined service to read; no arbitrary commands or file paths",
        minutes="Look back 1–1440 minutes", lines="Capture up to 200 recent entries",
        errors_only="Filter the captured sample for errors and traceback context",
    )
    async def logs(
        interaction: discord.Interaction,
        service: Literal["aries", "searxng"] = "aries",
        minutes: app_commands.Range[int, 1, 1440] = 30,
        lines: app_commands.Range[int, 1, 200] = 100,
        errors_only: bool = False,
    ):
        if not await check_monitor_owner(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            snapshot = await bot.monitor.logs(service, minutes, lines)
        except MonitorError as error:
            await interaction.edit_original_response(content=str(error), allowed_mentions=discord.AllowedMentions.none())
            return
        await interaction.edit_original_response(
            embed=logs_embed(snapshot, errors_only),
            view=LogsView(str(interaction.user.id), bot.monitor, snapshot, errors_only),
            allowed_mentions=discord.AllowedMentions.none(),
        )
