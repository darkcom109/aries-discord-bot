from sqlalchemy import select, delete

from . import connection
from .models import Message

async def save_message(
    guild_id: str | None,
    channel_id: str,
    user_id: str,
    role: str,
    content: str,
):
    async with connection.SessionFactory() as session:
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
    async with connection.SessionFactory() as session:
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
    async with connection.SessionFactory() as session:
        statement = delete(Message).where(
            Message.guild_id == guild_id,
            Message.channel_id == channel_id,
        )

        await session.execute(statement)
        await session.commit()
