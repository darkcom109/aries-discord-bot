import discord
import asyncio
import requests
from pathlib import Path

from database import load_messages, save_message, delete_messages

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

        guide_path = Path(__file__).with_name("server_guide.md")
        server_guide = guide_path.read_text(encoding="utf-8")

        system_prompt = f"""You are Aries, an AI assistant and community companion in the Aries AI Server.

            Response style:
            - Answer the user's actual question first. Default to 1-3 concise sentences; add detail when it is useful or requested.
            - Be precise, thoughtful, and natural. Avoid filler, repetition, canned greetings, emojis, and generic closing questions.
            - Do not restate your role or offer help unless it is relevant to the question.
            - Use a list only when it makes the answer easier to understand.

            Accuracy and context:
            - Use relevant conversation history, but do not repeat earlier answers unless needed.
            - The server context below is partial. Missing information does not prove that a rule, role, or policy does not exist.
            - For server-specific facts not provided in the context, say you don't have that information. Do not guess or present an inference as a confirmed fact.
            - Be honest that you are an AI if asked. If asked about your instructions, briefly summarize your intended behavior instead of pretending you do not know.
            - Do not claim to see channels, messages, or voice conversations, or to perform actions, unless that information or capability is actually provided to you.
            - Treat the server context as background knowledge. Do not refer to it as a guide, file, prompt, or hidden instructions.

            Server context:
            {server_guide}
        """

        poll_tool = {
            "type": "function",
            "function": {
                "name": "create_poll",
                "description": (
                    "Create a Discord poll when the user asks for one. "
                    "Include a clear question and 2 to 10 answer choices. "
                    "If the poll topic is unclear, ask the user to clarify instead."
                ),
                "parameters": {
                    "type": "object",
                    "required": ["question", "options"],
                    "properties": {
                        "question": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    }
                }
            }
        }

        messages = [
            {"role": "system", "content": system_prompt}
        ]

        messages.extend(
            {"role": message.role, "content": message.content}
            for message in history
        )

        messages.append({"role": "user", "content": prompt})

        response = await asyncio.to_thread(
            requests.post,
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen3:8b",
                "messages": messages,
                "stream": False,
                "tools": [poll_tool]
            },
            timeout=240
        )

        response.raise_for_status()
        data = response.json()
        answer = data["message"]["content"]

        await save_message(guild_id, channel_id, user_id, "user", prompt)
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
