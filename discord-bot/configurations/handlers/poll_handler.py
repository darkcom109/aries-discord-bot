from datetime import timedelta
import discord

from database import save_message

async def handle_create_poll(
    interaction,
    function,
    guild_id,
    channel_id,
    user_id
):
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