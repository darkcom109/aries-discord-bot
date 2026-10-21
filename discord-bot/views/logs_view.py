from io import BytesIO

import discord

from configurations.helpers.server_helper import log_text, logs_embed
from .monitor_view import MonitorView


class LogsView(MonitorView):
    def __init__(self, user_id: str, monitor, snapshot: dict, errors_only: bool = False):
        super().__init__(user_id, monitor)
        self.snapshot = snapshot
        self.errors_only = errors_only
        self.errors.label = "Show all" if errors_only else "Errors only"

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.snapshot = await self.monitor.logs(
            self.snapshot["service_id"], self.snapshot["minutes"], self.snapshot["limit"],
        )
        await interaction.edit_original_response(
            embed=logs_embed(self.snapshot, self.errors_only), view=self, allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Errors only", style=discord.ButtonStyle.secondary)
    async def errors(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.errors_only = not self.errors_only
        button.label = "Show all" if self.errors_only else "Errors only"
        await interaction.response.edit_message(
            embed=logs_embed(self.snapshot, self.errors_only), view=self, allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Download logs", style=discord.ButtonStyle.secondary)
    async def download(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True, ephemeral=True)
        text = log_text(self.snapshot, self.errors_only)
        await interaction.followup.send(
            file=discord.File(BytesIO(text.encode("utf-8")), filename=f"aries_{self.snapshot['service_id']}_logs.txt"),
            ephemeral=True, allowed_mentions=discord.AllowedMentions.none(),
        )
