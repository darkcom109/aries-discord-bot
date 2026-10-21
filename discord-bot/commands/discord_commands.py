import logging

import discord

from database import load_messages, save_message
from clients.ollama_client import ollama_response
from configurations.helpers.response_helper import answer_parts
from configurations.handlers.tfl_handler import tfl_answer
from .ask_command import register_ask
from .cancel_reminder_command import register_cancel_reminder
from .forget_command import register_forget
from .hello_command import register_hello
from .reminders_command import register_reminders
from .summarise_command import register_summarise
from .notes_command import register_notes
from .save_command import register_save
from .library_command import register_library
from .context_command import register_context
from .tfl_command import register_tfl
from .server_command import register_server
from .logs_command import register_logs
from .autonomy_command import register_autonomy

def register_commands(bot):
    @bot.event
    async def on_ready():
        print(f"Connected as {bot.user}")

    @bot.commands.error
    async def on_command_error(interaction: discord.Interaction, error):
        logging.getLogger(__name__).error(
            "Discord command failed", exc_info=(type(error), error, error.__traceback__)
        )
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(
                    content="I couldn't complete that request. Please try again."
                )
            else:
                await interaction.response.send_message(
                    "I couldn't complete that request. Please try again.", ephemeral=True
                )
        except discord.HTTPException:
            pass

    @bot.event
    async def on_message(message):
        if message.author.bot or bot.user is None:
            return

        if bot.user not in message.mentions:
            return

        prompt = (
            message.content
            .replace(f"<@{bot.user.id}>", "")
            .replace(f"<@!{bot.user.id}>", "")
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
            tool_calls = reply.get("tool_calls") or []
            if tool_calls:
                function = tool_calls[0].get("function", {})
                if function.get("name") == "get_tfl":
                    answer = await tfl_answer(bot.tfl, function.get("arguments", {}))
                else:
                    answer = "Use /ask for that action."
            else:
                answer = reply.get("content") or "I couldn't generate a reply"

        await save_message(guild_id, channel_id, user_id, "user", prompt)
        await save_message(guild_id, channel_id, user_id, "assistant", answer)

        preview, files = answer_parts(answer)
        await message.reply(
            preview,
            files=files,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    register_ask(bot)
    register_forget(bot)
    register_hello(bot)
    register_reminders(bot)
    register_cancel_reminder(bot)
    register_summarise(bot)
    register_notes(bot)
    register_save(bot)
    register_library(bot)
    register_context(bot)
    register_tfl(bot)
    register_server(bot)
    register_logs(bot)
    register_autonomy(bot)
