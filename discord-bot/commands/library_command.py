import discord

from library_database import get_user_library
from library_view import LibraryView

def register_library(bot):
    @bot.commands.command(
        name="library",
        description="Search and browse your private saved notes and documents",
    )
    async def library(interaction: discord.Interaction, query: str = ""):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild_id = str(interaction.guild_id) if interaction.guild_id is not None else None
        user_id = str(interaction.user.id)
        items = await get_user_library(guild_id, user_id, query)
        view = LibraryView(guild_id, user_id, items, query)

        await interaction.edit_original_response(
            embed=view.build_embed(),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
