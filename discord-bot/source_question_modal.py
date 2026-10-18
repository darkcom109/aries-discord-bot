import logging

import discord

from clients.source_client import source_response
from configurations.helpers.response_helper import send_answer

class SourceQuestionModal(discord.ui.Modal, title="Ask Aries about this"):
    question = discord.ui.TextInput(
        label="What would you like to know?",
        style=discord.TextStyle.paragraph,
        default="Explain this and highlight the important points.",
        max_length=1000,
    )

    def __init__(
        self,
        user_id: str,
        source: str,
        image: discord.Attachment | None = None,
    ):
        super().__init__()
        self.user_id = user_id
        self.source = source
        self.image = image

    async def on_submit(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "Please open your own question form.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.answer_question(interaction)

    async def answer_question(self, interaction: discord.Interaction):
        image_data = None

        if self.image is not None:
            if self.image.size > 8 * 1024 * 1024:
                await interaction.edit_original_response(
                    content="Please use an image smaller than 8 MB."
                )
                return
            image_data = await self.image.read()

        answer = await source_response(self.source, self.question.value, image_data)
        await send_answer(interaction, answer)

    async def on_error(self, interaction, error):
        logging.getLogger(__name__).error(
            "Source question failed", exc_info=(type(error), error, error.__traceback__)
        )
        if interaction.response.is_done():
            await interaction.edit_original_response(
                content="I couldn't answer that question. Please try again."
            )
        else:
            await interaction.response.send_message(
                "I couldn't answer that question. Please try again.", ephemeral=True
            )
