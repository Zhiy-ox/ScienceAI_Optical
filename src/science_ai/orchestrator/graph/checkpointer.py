"""Checkpointer factory — Postgres (durable) with MemorySaver fallback."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

_checkpointer: Any = None
_pg_connection: Any = None


async def get_checkpointer():
    """Return a shared checkpointer instance, creating it on first call.

    Uses AsyncPostgresSaver if ``checkpointer_dsn`` is configured and Postgres
    is reachable; otherwise falls back to MemorySaver (in-memory, non-durable).
    """
    global _checkpointer, _pg_connection
    if _checkpointer is not None:
        return _checkpointer

    from science_ai.config import settings

    dsn = settings.checkpointer_dsn
    if not dsn:
        # Derive DSN from database_url if it looks like a Postgres URL
        db_url = settings.database_url
        if db_url.startswith("postgresql+asyncpg://"):
            dsn = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    if dsn:
        try:
            from psycopg import AsyncConnection
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            _pg_connection = await AsyncConnection.connect(
                dsn, autocommit=True, prepare_threshold=0,
            )
            saver = AsyncPostgresSaver(_pg_connection)
            await saver.setup()
            _checkpointer = saver
            logger.info("Checkpointer: AsyncPostgresSaver (Postgres, durable)")
            return _checkpointer
        except Exception:
            logger.warning(
                "Postgres checkpointer unavailable, falling back to MemorySaver",
                exc_info=True,
            )

    _checkpointer = MemorySaver()
    logger.info("Checkpointer: MemorySaver (in-memory, non-durable)")
    return _checkpointer


async def close_checkpointer():
    """Shut down the checkpointer and release connections."""
    global _checkpointer, _pg_connection
    if _pg_connection is not None:
        try:
            await _pg_connection.close()
        except Exception:
            logger.warning("Error closing checkpointer connection", exc_info=True)
        _pg_connection = None
    _checkpointer = None


def reset_checkpointer():
    """Reset the singleton (for testing)."""
    global _checkpointer, _pg_connection
    _checkpointer = None
    _pg_connection = None
