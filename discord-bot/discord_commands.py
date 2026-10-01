import discord
from datetime import timedelta

from database import load_messages, save_message, delete_messages
from ollama_client import ollama_response

def register_commands(bot):
    @bot.event
    async def on_ready():
        print(f"Connected as {bot.user}")

    @bot.commands.command(name="hello", description="Say hello")
    async def hello(interaction: discord.Interaction):
        await interaction.response.send_message(f"Hello from {bot.user}")

    @bot.commands.command(name="ask", description="Ask Aries a question")
    async def ask(interaction: discord.Interaction, prompt: str):
        # Acknowledge the command while Ollama is generating its reply
        await interaction.response.defer(thinking=True)

        guild_id = (
            str(interaction.guild_id)
            if interaction.guild_id is not None
            else None
        )
        channel_id = str(interaction.channel_id)
        user_id = str(interaction.user.id)

        history = await load_messages(guild_id, channel_id, user_id)

        data = await ollama_response(history, prompt)

        message = data["message"]
        tool_calls = message.get("tool_calls", [])

        await save_message(guild_id, channel_id, user_id, "user", prompt)

        if tool_calls:
            function = tool_calls[0].get("function", {})

            if function.get("name") != "create_poll":
                await interaction.edit_original_response(
                    content="I don't know how to perform that action"
                )
                return

            arguments = function.get("arguments", {})

            if not isinstance(arguments, dict):
                await interaction.edit_original_response(
                    content="I couldn't understand the poll details"
                )
                return

            question = arguments.get("question")
            options = arguments.get("options")

            if (
                not isinstance(question, str)
                or not question.strip()
                or not isinstance(options, list)
                or not 2 <= len(options) <= 10
                or not all(isinstance(option, str) and option.strip() for option in options)
            ):
                await interaction.edit_original_response(
                    content="I couldn't make a valid poll. Please provide a question and 2-10 choices."
                )
                return

            question = question.strip()
            options = [option.strip() for option in options]

            poll = discord.Poll(
                question=question,
                duration=timedelta(hours=24)
            )

            for option in options:
                poll.add_answer(text=option)

            await interaction.edit_original_response(
                content="Poll created:",
                poll=poll
            )

            await save_message(
                guild_id,
                channel_id,
                user_id,
                "assistant",
                f"Created a 24-hour poll: {question}"
            )

            return

        answer = message.get("content", "")

        await save_message(guild_id, channel_id, user_id, "assistant", answer)

        await interaction.edit_original_response(content=answer[:2000])

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
        user_id = str(interaction.user.id)

        await delete_messages(guild_id, channel_id, user_id)

        await interaction.response.send_message(
            "I've cleared your saved conversation history from this channel",
            ephemeral=True
        )
