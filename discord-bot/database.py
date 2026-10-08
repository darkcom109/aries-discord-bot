from sqlalchemy import String, Text, Integer, Boolean, select, delete
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
    sent: Mapped[bool] = mapped_column(Boolean, default=False)

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
):
    async with SessionFactory() as session:
        reminder = Reminder(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            content=content,
            due_at=due_at
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
        )

        result = await session.execute(statement)
        await session.commit()

        return True