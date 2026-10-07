import discord

from database import get_user_reminders

def register_reminders(bot):
    @bot.commands.command(
        name="reminders",
        description="View all your saved reminders due"
    )
    async def reminders(interaction: discord.Interaction):
        guild_id = (
            str(interaction.guild_id)
            if interaction.guild_id is not None
            else None
        )
        channel_id = str(interaction.channel_id)
        user_id = str(interaction.user.id)

        reminders = await get_user_reminders(guild_id, channel_id, user_id)

        if not reminders:
            await interaction.response.send_message(
                "You don't have any upcoming reminders in this channel.",
                ephemeral=True,
            )
            return

        lines = []
        for reminder in reminders[:10]:
            content = " ".join(reminder.content.split())
            lines.append(
                f"**#{reminder.id}** · <t:{reminder.due_at}:R> · {content[:120]}"
            )

        if len(reminders) > 10:
            lines.append(f"... and {len(reminders) - 10} more.")

        await interaction.response.send_message(
            "Your upcoming reminders:\n" + "\n".join(lines),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none()
        )
