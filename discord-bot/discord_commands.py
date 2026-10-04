import discord

from database import load_messages, save_message, delete_messages, get_user_reminders, delete_user_reminder
from ollama_client import ollama_response
from configurations.handlers import handlers

def register_commands(bot):
    @bot.event
    async def on_ready():
        print(f"Connected as {bot.user}")

    @bot.commands.command(name="hello", description="Say hello")
    async def hello(interaction: discord.Interaction):
        await interaction.response.send_message(f"Hello from {bot.user}")

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

        if not prompt:
            return

        guild_id = str(message.guild.id) if message.guild else None
        channel_id = str(message.channel.id)
        user_id = str(message.author.id)

        async with message.channel.typing():
            history = await load_messages(guild_id, channel_id)
            result = await ollama_response(history, prompt)

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

        history = await load_messages(guild_id, channel_id)

        data = await ollama_response(history, prompt)

        message = data["message"]
        tool_calls = message.get("tool_calls", [])

        await save_message(guild_id, channel_id, user_id, "user", prompt)

        # Manage different tool calls
        if tool_calls:
            function = tool_calls[0].get("function", {})
            function_name = function.get("name")

            if function_name:
                await handlers[function_name](interaction, function, guild_id, channel_id, user_id)
            else:
                await interaction.edit_original_response(
                    content="I don't know how to perform that action."
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

    @bot.commands.command(
        name="reminders",
        description="View all your saved reminders due"
    )
    async def reminders(interaction: discord.Interaction):
        guild_id = (
            str(interaction.guild_id)
            if interaction.guild_id is not None
            else None
        )
        channel_id = str(interaction.channel_id)
        user_id = str(interaction.user.id)

        reminders = await get_user_reminders(guild_id, channel_id, user_id)

        if not reminders:
            await interaction.response.send_message(
                "You don't have any upcoming reminders in this channel.",
                ephemeral=True,
            )
            return

        lines = []
        for reminder in reminders[:10]:
            content = " ".join(reminder.content.split())
            lines.append(
                f"**#{reminder.id}** · <t:{reminder.due_at}:R> · {content[:120]}"
            )

        if len(reminders) > 10:
            lines.append(f"... and {len(reminders) - 10} more.")

        await interaction.response.send_message(
            "Your upcoming reminders:\n" + "\n".join(lines),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none()
        )

    @bot.commands.command(
        name="cancelreminder",
        description="Cancel one of your upcoming reminders"
    )
    async def cancelreminder(
        interaction: discord.Interaction,
        reminder_id: int
    ):
        guild_id = (
            str(interaction.guild_id)
            if interaction.guild_id is not None
            else None
        )
        channel_id = str(interaction.channel_id)
        user_id = str(interaction.user.id)

        deleted = await delete_user_reminder(
            reminder_id,
            guild_id,
            channel_id,
            user_id
        )

        if deleted:
            response = f"Cancelled reminder #{reminder_id}"
        else:
            response = "I couldn't find that pending reminder in this channel"

        await interaction.response.send_message(
            response,
            ephemeral=True
        )

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




