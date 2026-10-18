import time

from sqlalchemy import delete, func, select

from . import connection
from .models import SavedItem

async def save_library_item(
    guild_id: str | None,
    channel_id: str,
    user_id: str,
    title: str,
    content: str,
    source_url: str | None = None,
) -> int:
    async with connection.SessionFactory() as session:
        item = None

        if source_url is not None:
            item = await session.scalar(
                select(SavedItem).where(
                    SavedItem.guild_id == guild_id,
                    SavedItem.user_id == user_id,
                    SavedItem.source_url == source_url,
                )
            )

        if item is None:
            item = SavedItem(
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                source_url=source_url,
                created_at=int(time.time()),
            )
            session.add(item)

        item.title = title.strip()[:100] or "Saved item"
        item.content = content.strip()[:100_000]
        await session.commit()
        return item.id

async def get_user_library(
    guild_id: str | None,
    user_id: str,
    query: str = "",
):
    async with connection.SessionFactory() as session:
        statement = select(SavedItem).where(
            SavedItem.guild_id == guild_id,
            SavedItem.user_id == user_id,
        )

        searchable = func.lower(SavedItem.title + " " + SavedItem.content)

        for word in query.lower().split()[:10]:
            statement = statement.where(searchable.contains(word, autoescape=True))

        result = await session.scalars(
            statement.order_by(SavedItem.created_at.desc(), SavedItem.id.desc()).limit(50)
        )
        return list(result)

async def get_user_library_item(
    item_id: int,
    guild_id: str | None,
    user_id: str,
):
    async with connection.SessionFactory() as session:
        return await session.scalar(
            select(SavedItem).where(
                SavedItem.id == item_id,
                SavedItem.guild_id == guild_id,
                SavedItem.user_id == user_id,
            )
        )

async def delete_user_library_item(
    item_id: int,
    guild_id: str | None,
    user_id: str,
) -> bool:
    async with connection.SessionFactory() as session:
        result = await session.execute(
            delete(SavedItem)
            .where(
                SavedItem.id == item_id,
                SavedItem.guild_id == guild_id,
                SavedItem.user_id == user_id,
            )
            .returning(SavedItem.id)
        )
        deleted_id = result.scalar_one_or_none()
        await session.commit()
        return deleted_id is not None
