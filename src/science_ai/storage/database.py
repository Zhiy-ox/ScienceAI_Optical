"""Async PostgreSQL database setup with SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from science_ai.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_size=10)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """Get a new async database session."""
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables."""
    from science_ai.storage.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the engine."""
    await engine.dispose()
