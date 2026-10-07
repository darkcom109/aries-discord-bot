import discord

from database import load_messages
from clients.ollama_client import ollama_response

def register_summarise(bot):
    @bot.commands.command(
        name="summarise",
        description="Summarise the server's saved Aries conversation in this channel"
    )
    async def summarise(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        guild_id = (
            str(interaction.guild_id)
            if interaction.guild_id is not None
            else None
        )
        channel_id = str(interaction.channel_id)

        history = await load_messages(
            guild_id,
            channel_id,
            limit=20,
        )

        if not history:
            await interaction.edit_original_response(
                content="There's no saved Aries conversation to summarise here"
            )
            return

        data = await ollama_response(
            history,
            "Summarise the conversation so far. Include important facts, "
            "decisions, and unresolved questions. Be concise and don't invent "
            "details. Do not use tools."
        )

        model_message = data["message"]

        if model_message.get("tool_calls"):
            summary = "I couldn't summarise the conversation"
        else:
            summary = model_message.get("content", "").strip()
            if not summary:
                summary = "I couldn't produce a summary"

        await interaction.edit_original_response(content=summary[:2000])
