import os
import time

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from database import create_tables, load_due_reminders, mark_reminder_sent
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
        self.check_reminders.start()
        await self.commands.sync()

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        reminders = await load_due_reminders(int(time.time()))

        for reminder in reminders:
            try:
                channel = self.get_partial_messageable(int(reminder.channel_id))

                await channel.send(
                    f"<@{reminder.user_id}> Reminder: {reminder.content}",
                    allowed_mentions=discord.AllowedMentions(
                        users=[discord.Object(id=int(reminder.user_id))]
                    )
                )
            except discord.HTTPException as error:
                print(f"Couldn't send reminder {reminder.id}: {error}")
                continue

            await mark_reminder_sent(reminder.id)

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.wait_until_ready()

bot = MyBot()
register_commands(bot)

bot.run(token=token)