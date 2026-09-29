import os

import discord
from dotenv import load_dotenv

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
        await self.commands.sync()

bot = MyBot()

@bot.event
async def on_ready():
    print(f"Connected as {bot.user}")

@bot.commands.command(name="hello", description="Say hello")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello from my bot")

bot.run(token=token)