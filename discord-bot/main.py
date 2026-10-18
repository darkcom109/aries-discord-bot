import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from database import create_tables, load_due_reminders, mark_reminder_sent, update_due_at
from discord_commands import register_commands
from reminder_view import ReminderView

bot_directory = Path(__file__).resolve().parent
project_directory = bot_directory.parent
load_dotenv(bot_directory / ".env")
load_dotenv(project_directory / ".env")

token = os.getenv("DISCORD_TOKEN")
ollama_api_key = os.getenv("OLLAMA_API_KEY")

if not token:
    raise RuntimeError("DISCORD_TOKEN is missing")

if not ollama_api_key:
    raise RuntimeError("OLLAMA_API_KEY is missing")

class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.commands = discord.app_commands.CommandTree(self)

    async def setup_hook(self):
        await create_tables()
        self.check_reminders.start()
        await self.commands.sync()

    @tasks.loop(seconds=1)
    async def check_reminders(self):
        reminders = await load_due_reminders(int(time.time()))

        for reminder in reminders:
            try:
                channel = self.get_partial_messageable(int(reminder.channel_id))

                await channel.send(
                    f"<@{reminder.user_id}> Reminder: {reminder.content}",
                    allowed_mentions=discord.AllowedMentions(
                        users=[discord.Object(id=int(reminder.user_id))]
                    ),
                    view=ReminderView(
                        reminder.guild_id,
                        reminder.channel_id,
                        reminder.user_id,
                        reminder.content
                    )
                )
            except discord.HTTPException as error:
                print(f"Couldn't send reminder {reminder.id}: {error}")
                continue

            repeat = reminder.repeat

            if repeat == "none":
                await mark_reminder_sent(reminder.id)
            else:
                next_time = datetime.fromtimestamp(
                    reminder.due_at
                )

                if repeat == "daily":
                    next_time += timedelta(days=1)
                else:
                    next_time += timedelta(days=7)

                next_due_at = str(next_time.timestamp())

                await update_due_at(reminder.id, next_due_at)

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.wait_until_ready()

bot = MyBot()
register_commands(bot)

bot.run(token=token)
