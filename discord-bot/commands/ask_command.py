import discord

from database import load_messages, save_message
from ollama_client import ollama_response
from configurations.handlers import handlers

def register_ask(bot):
    @bot.commands.command(name="ask", description="Ask Aries a question")
    async def ask(interaction: discord.Interaction, prompt: str, image: discord.Attachment | None = None):

        image_data = None

        if image is not None:
            if not image.content_type or not image.content_type.startswith("image/"):
                await interaction.edit_original_response(
                    content="Please attach an image file"
                )
                return

            if image.size > 8 * 1024 * 1024:
                await interaction.edit_original_response(
                    content="Please use an image smaller than 8MB."
                )

            image_data = await image.read()
            
        # Acknowledge the command while Ollama is generating its reply
        await interaction.response.defer(thinking=True)

        guild_id = (
            str(interaction.guild_id)
            if interaction.guild_id is not None
            else None
        )
        channel_id = str(interaction.channel_id)
        user_id = str(interaction.user.id)

        history = await load_messages(guild_id, channel_id)

        data = await ollama_response(history, prompt, image_data)

        message = data["message"]
        tool_calls = message.get("tool_calls", [])

        await save_message(guild_id, channel_id, user_id, "user", prompt)

        # Manage different tool calls
        if tool_calls:
            function = tool_calls[0].get("function", {})
            function_name = function.get("name")

            if function_name in handlers:
                await handlers[function_name](interaction, function, guild_id, channel_id, user_id)
            else:
                await interaction.edit_original_response(
                    content="I don't know how to perform that action."
                )

            return

        answer = message.get("content", "")

        await save_message(guild_id, channel_id, user_id, "assistant", answer)

        await interaction.edit_original_response(content=answer[:2000])