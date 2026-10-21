from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from . import connection
from .models import TflWatch


async def get_user_tfl_watches(user_id: str):
    async with connection.SessionFactory() as session:
        result = await session.scalars(
            select(TflWatch).where(TflWatch.user_id == user_id).order_by(TflWatch.line_name)
        )
        return list(result)


async def save_tfl_watch(user_id: str, channel_id: str, line_id: str, line_name: str, last_status: str):
    async with connection.SessionFactory() as session:
        watch = TflWatch(
            user_id=user_id,
            channel_id=channel_id,
            line_id=line_id,
            line_name=line_name,
            last_status=last_status,
        )
        session.add(watch)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return None
        return watch.id


async def load_tfl_watches():
    async with connection.SessionFactory() as session:
        return list(await session.scalars(select(TflWatch)))


async def update_tfl_watch_status(watch_id: int, status: str):
    async with connection.SessionFactory() as session:
        await session.execute(update(TflWatch).where(TflWatch.id == watch_id).values(last_status=status))
        await session.commit()


async def delete_user_tfl_watch(user_id: str, line_id: str) -> bool:
    async with connection.SessionFactory() as session:
        result = await session.execute(
            delete(TflWatch).where(TflWatch.user_id == user_id, TflWatch.line_id == line_id).returning(TflWatch.id)
        )
        deleted_id = result.scalar_one_or_none()
        await session.commit()
        return deleted_id is not None
