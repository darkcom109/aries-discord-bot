import time

from sqlalchemy import select, delete, update

from configurations.helpers.reminder_helper import format_reminder_content

from . import connection
from .models import Reminder, ReminderDelivery

async def save_reminder(
    guild_id: str | None,
    channel_id: str,
    user_id: str,
    content: str,
    due_at: int,
    repeat: str,
):
    async with connection.SessionFactory() as session:
        reminder = Reminder(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            content=format_reminder_content(content),
            due_at=due_at,
            repeat=repeat
        )

        session.add(reminder)
        await session.commit()

        return reminder.id
    
async def load_due_reminders(now: int):
    async with connection.SessionFactory() as session:
        statement = (
            select(Reminder)
            .where(
                Reminder.due_at <= now,
                Reminder.sent.is_(False),
            )
            .order_by(Reminder.due_at)
        )

        result = await session.scalars(statement)
        return list(result)

async def mark_reminder_sent(reminder_id: int) -> bool:
    async with connection.SessionFactory() as session:
        reminder = await session.get(Reminder, reminder_id)

        if reminder is None:
            return False

        reminder.sent = True
        await session.commit()
        return True

async def get_user_reminders(
    guild_id: str | None,
    channel_id: str,
    user_id: str
):
    async with connection.SessionFactory() as session:
        statement = (
            select(Reminder)
            .where(
                Reminder.guild_id == guild_id,
                Reminder.channel_id == channel_id,
                Reminder.user_id == user_id,
                Reminder.sent.is_(False)
            )
            .order_by(Reminder.due_at)
        )

        result = await session.scalars(statement)
        return list(result)

async def delete_user_reminder(
    reminder_id: int,
    guild_id: str | None,
    channel_id: str,
    user_id: str,
) -> bool:
    async with connection.SessionFactory() as session:
        statement = delete(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.guild_id == guild_id,
            Reminder.channel_id == channel_id,
            Reminder.user_id == user_id,
            Reminder.sent.is_(False),
        ).returning(Reminder.id)

        result = await session.execute(statement)
        deleted_id = result.scalar_one_or_none()
        await session.commit()

        return deleted_id is not None

async def update_due_at(
    reminder_id: int,
    new_due_at: int,
):
    async with connection.SessionFactory() as session:
        statement = (
            select(Reminder)
            .where(
                Reminder.id == reminder_id, 
            )
        )

        result = await session.execute(statement)
        reminder = result.scalar_one_or_none()

        if reminder is None:
            return False

        reminder.due_at = new_due_at

        await session.commit()

        return True

async def save_reminder_delivery(reminder: Reminder) -> int:
    async with connection.SessionFactory() as session:
        delivery = ReminderDelivery(
            reminder_id=reminder.id,
            guild_id=reminder.guild_id,
            channel_id=reminder.channel_id,
            user_id=reminder.user_id,
            content=reminder.content,
        )
        session.add(delivery)
        await session.commit()
        return delivery.id

async def set_reminder_delivery_message(delivery_id: int, message_id: str):
    async with connection.SessionFactory() as session:
        await session.execute(
            update(ReminderDelivery)
            .where(ReminderDelivery.id == delivery_id)
            .values(message_id=message_id)
        )
        await session.commit()

async def delete_reminder_delivery(delivery_id: int):
    async with connection.SessionFactory() as session:
        await session.execute(
            delete(ReminderDelivery).where(ReminderDelivery.id == delivery_id)
        )
        await session.commit()

async def get_reminder_delivery(delivery_id: int):
    async with connection.SessionFactory() as session:
        return await session.get(ReminderDelivery, delivery_id)

async def load_reminder_deliveries():
    async with connection.SessionFactory() as session:
        result = await session.scalars(
            select(ReminderDelivery).where(
                ReminderDelivery.resolved.is_(False),
                ReminderDelivery.message_id.is_not(None),
            )
        )
        return list(result)

async def resolve_reminder_delivery(
    delivery_id: int,
    user_id: str,
    snooze_seconds: int | None = None,
) -> bool:
    if snooze_seconds is not None and not 60 <= snooze_seconds <= 7 * 86400:
        raise ValueError("Choose a snooze time between 1 minute and 7 days.")

    async with connection.SessionFactory() as session:
        result = await session.execute(
            update(ReminderDelivery)
            .where(
                ReminderDelivery.id == delivery_id,
                ReminderDelivery.user_id == user_id,
                ReminderDelivery.resolved.is_(False),
            )
            .values(resolved=True)
            .returning(ReminderDelivery)
        )
        delivery = result.scalar_one_or_none()

        if delivery is None:
            return False

        if snooze_seconds is not None:
            session.add(Reminder(
                guild_id=delivery.guild_id,
                channel_id=delivery.channel_id,
                user_id=delivery.user_id,
                content=format_reminder_content(delivery.content),
                due_at=int(time.time()) + snooze_seconds,
                repeat="none",
            ))

        await session.commit()
        return True
