import time

from sqlalchemy import String, Text, Integer, Boolean, select, delete, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

class Base(DeclarativeBase):
    pass

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_id: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)

class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_id: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    due_at: Mapped[int] = mapped_column(Integer)
    repeat: Mapped[str] = mapped_column(String)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)

class ReminderDelivery(Base):
    __tablename__ = "reminder_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_id: Mapped[int] = mapped_column(Integer)
    guild_id: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_id: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

class SavedItem(Base):
    __tablename__ = "saved_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_id: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer)

engine = create_async_engine("sqlite+aiosqlite:///aries.db")

SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

async def create_tables():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

async def save_message(
    guild_id: str | None,
    channel_id: str,
    user_id: str,
    role: str,
    content: str,
):
    async with SessionFactory() as session:
        message = Message(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            role=role,
            content=content
        )

        session.add(message)
        await session.commit()

async def load_messages(
    guild_id: str | None,
    channel_id: str,
    limit: int = 10,
):
    async with SessionFactory() as session:
        statement = (
            select(Message)
            .where(
                Message.guild_id == guild_id,
                Message.channel_id == channel_id,
            )
            .order_by(Message.id.desc())
            .limit(limit)
        )

        result = await session.scalars(statement)
        messages = list(result)
        messages.reverse()
        return messages

async def delete_messages(
    guild_id: str | None,
    channel_id: str,
):
    async with SessionFactory() as session:
        statement = delete(Message).where(
            Message.guild_id == guild_id,
            Message.channel_id == channel_id,
        )

        await session.execute(statement)
        await session.commit()

async def save_reminder(
    guild_id: str | None,
    channel_id: str,
    user_id: str,
    content: str,
    due_at: int,
    repeat: str,
):
    async with SessionFactory() as session:
        reminder = Reminder(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            content=content,
            due_at=due_at,
            repeat=repeat
        )

        session.add(reminder)
        await session.commit()

        return reminder.id
    
async def load_due_reminders(now: int):
    async with SessionFactory() as session:
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
    async with SessionFactory() as session:
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
    async with SessionFactory() as session:
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
    async with SessionFactory() as session:
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
    async with SessionFactory() as session:
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
    async with SessionFactory() as session:
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
    async with SessionFactory() as session:
        await session.execute(
            update(ReminderDelivery)
            .where(ReminderDelivery.id == delivery_id)
            .values(message_id=message_id)
        )
        await session.commit()

async def delete_reminder_delivery(delivery_id: int):
    async with SessionFactory() as session:
        await session.execute(
            delete(ReminderDelivery).where(ReminderDelivery.id == delivery_id)
        )
        await session.commit()

async def get_reminder_delivery(delivery_id: int):
    async with SessionFactory() as session:
        return await session.get(ReminderDelivery, delivery_id)

async def load_reminder_deliveries():
    async with SessionFactory() as session:
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

    async with SessionFactory() as session:
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
                content=delivery.content,
                due_at=int(time.time()) + snooze_seconds,
                repeat="none",
            ))

        await session.commit()
        return True
