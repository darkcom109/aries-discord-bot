import os
import time
from pathlib import Path

import discord
from discord.ext import tasks
from dotenv import load_dotenv

from database import (
    create_tables,
    delete_reminder_delivery,
    load_due_reminders,
    load_reminder_deliveries,
    mark_reminder_sent,
    save_reminder_delivery,
    set_reminder_delivery_message,
    update_due_at,
)
from configurations.helpers.reminder_helper import next_reminder_due_at
from configurations.helpers.response_helper import shorten_text
from discord_commands import register_commands
from reminder_view import ReminderView

bot_directory = Path(__file__).resolve().parent
project_directory = bot_directory.parent
load_dotenv(bot_directory / ".env")
load_dotenv(project_directory / ".env")

token = os.getenv("DISCORD_TOKEN")
ollama_api_key = os.getenv("OLLAMA_API_KEY")

class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.commands = discord.app_commands.CommandTree(self)

    async def setup_hook(self):
        await create_tables()
        for delivery in await load_reminder_deliveries():
            if delivery.message_id is not None:
                self.add_view(ReminderView(delivery.id), message_id=int(delivery.message_id))
        self.check_reminders.start()
        await self.commands.sync()

    async def close(self):
        self.check_reminders.cancel()
        await super().close()

    @tasks.loop(seconds=1)
    async def check_reminders(self):
        reminders = await load_due_reminders(int(time.time()))

        for reminder in reminders:
            delivery_id = await save_reminder_delivery(reminder)
            try:
                channel = self.get_partial_messageable(int(reminder.channel_id))

                message = await channel.send(
                    shorten_text(f"<@{reminder.user_id}> Reminder: {reminder.content}"),
                    allowed_mentions=discord.AllowedMentions(
                        users=[discord.Object(id=int(reminder.user_id))]
                    ),
                    view=ReminderView(delivery_id),
                )
            except discord.HTTPException as error:
                await delete_reminder_delivery(delivery_id)
                print(f"Couldn't send reminder {reminder.id}: {error}")
                continue

            await set_reminder_delivery_message(delivery_id, str(message.id))
            next_due_at = next_reminder_due_at(int(reminder.due_at), reminder.repeat)

            if next_due_at is None:
                await mark_reminder_sent(reminder.id)
            else:
                await update_due_at(reminder.id, next_due_at)

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.wait_until_ready()

if __name__ == "__main__":
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing")

    if not ollama_api_key:
        raise RuntimeError("OLLAMA_API_KEY is missing")

    bot = MyBot()
    register_commands(bot)
    bot.run(token=token)
