import os

import discord
from dotenv import load_dotenv

from database import create_tables
from discord_commands import register_commands

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
register_commands(bot)

bot.run(token=token)