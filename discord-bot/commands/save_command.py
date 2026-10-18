import discord

from configurations.helpers.library_helper import read_library_file
from database import save_library_item

def register_save(bot):
    @bot.commands.command(
        name="save",
        description="Save a private note or document in your Aries library",
    )
    async def save(
        interaction: discord.Interaction,
        text: str | None = None,
        file: discord.Attachment | None = None,
        title: str | None = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        sections = [text.strip()] if text and text.strip() else []

        if file is not None:
            try:
                document = await read_library_file(file)
            except ValueError as error:
                await interaction.edit_original_response(content=str(error))
                return
            sections.append(f"FILE: {file.filename}\n{document}")

        if not sections:
            await interaction.edit_original_response(
                content="Add some text or attach a readable document to save."
            )
            return

        content = "\n\n".join(sections)
        item_title = title or (file.filename if file else " ".join(content.split())[:100])
        item_id = await save_library_item(
            str(interaction.guild_id) if interaction.guild_id is not None else None,
            str(interaction.channel_id),
            str(interaction.user.id),
            item_title,
            content,
        )

        await interaction.edit_original_response(
            content=f"Saved **#{item_id}** to your private library. Use /library to find it.\n"
            "Documents keep up to 100,000 characters of extracted text.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
