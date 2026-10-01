from sqlalchemy import String, Text, select, delete
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
    user_id: str,
    limit: int = 10,
):
    async with SessionFactory() as session:
        statement = (
            select(Message)
            .where(
                Message.guild_id == guild_id,
                Message.channel_id == channel_id,
                Message.user_id == user_id,
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
    user_id: str,
):
    async with SessionFactory() as session:
        statement = delete(Message).where(
            Message.guild_id == guild_id,
            Message.channel_id == channel_id,
            Message.user_id == user_id
        )

        await session.execute(statement)
        await session.commit()