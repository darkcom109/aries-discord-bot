import discord

from configurations.helpers.library_helper import read_library_message
from database import save_library_item
from modals import MessageQuestionModal

def register_context(bot):
    async def save_message(interaction: discord.Interaction, message: discord.Message):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            content = await read_library_message(message)
        except ValueError as error:
            await interaction.edit_original_response(content=str(error))
            return

        item_id = await save_library_item(
            str(interaction.guild_id) if interaction.guild_id is not None else None,
            str(message.channel.id),
            str(interaction.user.id),
            " ".join(content.split())[:100],
            content,
            message.jump_url,
        )
        await interaction.edit_original_response(content=f"Saved **#{item_id}**. Find it with /library.")

    async def ask_message(interaction: discord.Interaction, message: discord.Message):
        image = next(
            (
                file for file in message.attachments
                if file.content_type and file.content_type.startswith("image/")
            ),
            None,
        )
        modal = MessageQuestionModal(str(interaction.user.id), message, image)
        await interaction.response.send_modal(modal)

    bot.commands.add_command(discord.app_commands.ContextMenu(
        name="Save to Aries",
        callback=save_message,
    ))
    bot.commands.add_command(discord.app_commands.ContextMenu(
        name="Ask Aries about this",
        callback=ask_message,
    ))
