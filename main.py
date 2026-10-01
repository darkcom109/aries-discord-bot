import os

import discord
import asyncio
import requests
from dotenv import load_dotenv
from pathlib import Path

from database import create_tables, load_messages, save_message, delete_messages

load_dotenv()

token = os.getenv("DISCORD_TOKEN")

if not token:
    raise RuntimeError("DISCORD_TOKEN is missing")

class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.commands = discord.app_commands.CommandTree(self)

    async def setup_hook(self):
        await create_tables()
        await self.commands.sync()

bot = MyBot()

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

    system_prompt = f"""
        You are Aries, a friendly assistant in a Discord server.
        Give clear, concise answers. Use the conversation history for context. 
        If you don't know something, say so instead of making it up.
        You can only see the messages included in this request.

        Server Guide:
        {server_guide}
    """

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
            "stream": False
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

bot.run(token=token)