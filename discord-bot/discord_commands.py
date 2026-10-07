from database import load_messages, save_message
from ollama_client import ollama_response
from commands import (
    register_ask,
    register_cancel_reminder,
    register_forget,
    register_hello,
    register_reminders,
    register_summarise,
    register_notes
)

def register_commands(bot):
    @bot.event
    async def on_ready():
        print(f"Connected as {bot.user}")

    @bot.event
    async def on_message(message):
        if message.author.bot or bot.user is None:
            return

        if bot.user not in message.mentions:
            return

        prompt = (
            message.content
            .replace(f"<@{bot.user.id}", "")
            .replace(f"<@!{bot.user.id}", "")
            .strip()
        )

        image = next(
            (
                attachment
                for attachment in message.attachments
                if attachment.content_type
                and attachment.content_type.startswith("image/")
            ),
            None,
        )

        if image is not None and image.size > 8 * 1024 * 1024:
            await message.reply(
                "Please use an image smaller than 8 MB.",
                mention_author=False
            )
            return

        if not prompt and image is not None:
            prompt = "Describe this image."

        if not prompt:
            return

        guild_id = str(message.guild.id) if message.guild else None
        channel_id = str(message.channel.id)
        user_id = str(message.author.id)

        async with message.channel.typing():
            image_data = await image.read() if image is not None else None
            history = await load_messages(guild_id, channel_id)
            result = await ollama_response(history, prompt, image_data)

        reply = result["message"]

        if reply.get("tool_calls"):
            answer = "Use /ask for polls and reminders"
        else:
            answer = reply.get("content") or "I couldn't generate a reply"

        await save_message(guild_id, channel_id, user_id, "user", prompt)
        await save_message(guild_id, channel_id, user_id, "assistant", answer)

        if len(answer) > 2000:
            answer = answer[:1997] + "..."

        await message.reply(answer, mention_author=False)

    register_ask(bot)
    register_forget(bot)
    register_hello(bot)
    register_reminders(bot)
    register_cancel_reminder(bot)
    register_summarise(bot)
    register_notes(bot)
