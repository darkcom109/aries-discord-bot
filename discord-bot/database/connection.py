from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .models import Base

engine = create_async_engine("sqlite+aiosqlite:///aries.db")

SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

async def create_tables():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
