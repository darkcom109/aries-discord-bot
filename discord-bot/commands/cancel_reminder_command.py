import discord

from database import delete_user_reminder

def register_cancel_reminder(bot):
    @bot.commands.command(
        name="cancelreminder",
        description="Cancel one of your upcoming reminders"
    )
    async def cancelreminder(
        interaction: discord.Interaction,
        reminder_id: int
    ):
        guild_id = (
            str(interaction.guild_id)
            if interaction.guild_id is not None
            else None
        )
        channel_id = str(interaction.channel_id)
        user_id = str(interaction.user.id)

        deleted = await delete_user_reminder(
            reminder_id,
            guild_id,
            channel_id,
            user_id
        )

        if deleted:
            response = f"Cancelled reminder #{reminder_id}"
        else:
            response = "I couldn't find that pending reminder in this channel"

        await interaction.response.send_message(
            response,
            ephemeral=True
        )
