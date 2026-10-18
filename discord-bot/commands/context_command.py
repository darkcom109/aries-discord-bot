import discord

from configurations.helpers.library_helper import read_library_message
from library_database import save_library_item
from source_question_modal import SourceQuestionModal

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

class MessageQuestionModal(SourceQuestionModal):
    def __init__(
        self,
        user_id: str,
        message: discord.Message,
        image: discord.Attachment | None,
    ):
        super().__init__(user_id, "", image)
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "Please open your own question form.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            self.source = await read_library_message(self.message)
        except ValueError as error:
            if self.image is None:
                await interaction.edit_original_response(content=str(error))
                return
            self.source = self.message.content

        self.source = f"Original message: {self.message.jump_url}\n\n{self.source}"
        await self.answer_question(interaction)
