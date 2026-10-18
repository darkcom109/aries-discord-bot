import time

import discord

from database import save_reminder

class ReminderView(discord.ui.View):
    def __init__(
        self,
        guild_id: str | None,
        channel_id: str,
        user_id: str,
        content: str,
    ):
        super().__init__(timeout=86400)

        self.guild_id = guild_id
        self.channel_id = channel_id
        self.user_id = user_id
        self.content = content

    async def interaction_check(
        self,
        interaction: discord.Interaction
    ) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "Only the person who set this reminder can use these buttons.",
                ephemeral=True
            )
            return False

        return True

    @discord.ui.button(
        label="Snooze 10 min",
        style=discord.ButtonStyle.primary
    )
    async def snooze(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        due_at = int(time.time()) + 600

        await save_reminder(
            self.guild_id,
            self.channel_id,
            self.user_id,
            self.content,
            due_at,
            "none"
        )

        await interaction.response.edit_message(
            content=f"Snoozed - <t:{due_at}:R>.",
            view=None
        )

    @discord.ui.button(
        label="Dismiss",
        style=discord.ButtonStyle.secondary,
    )
    async def dismiss(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content="Reminder dismissed",
            view=None
        )