import discord

from database import delete_messages

def register_forget(bot):
    @bot.commands.command(
            name="forget",
            description="Delete your saved Aries history from this channel",
        )
    async def forget(interaction: discord.Interaction):
        guild_id = (
            str(interaction.guild_id)
            if interaction.guild_id is not None
            else None
        )
        channel_id = str(interaction.channel_id)

        await delete_messages(guild_id, channel_id)

        await interaction.response.send_message(
            "I've cleared your saved conversation history from this channel",
            ephemeral=True
        )