import discord

from configurations.helpers.library_helper import read_library_message
from .source_question_modal import SourceQuestionModal

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
