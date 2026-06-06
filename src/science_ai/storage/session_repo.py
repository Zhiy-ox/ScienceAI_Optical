"""Repository for persisting research sessions to PostgreSQL."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from science_ai.storage.models import ResearchSession

logger = logging.getLogger(__name__)


class SessionRepository:
    """CRUD operations for ResearchSession rows.

    Accepts an async_sessionmaker so it can be tested against SQLite in-memory.
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def create_session(self, session_id: str, question: str, phase: int) -> None:
        """Insert a new session row with status='running'."""
        async with self._session_factory() as db:
            row = ResearchSession(
                session_id=session_id,
                question=question,
                phase=phase,
                status="running",
            )
            db.add(row)
            await db.commit()
        logger.info("Created session %s (phase=%d)", session_id, phase)

    async def update_status(self, session_id: str, status: str) -> None:
        """Update only the status field of a session."""
        async with self._session_factory() as db:
            row = await db.get(ResearchSession, session_id)
            if row:
                row.status = status
                await db.commit()

    async def update_result(
        self,
        session_id: str,
        result: dict[str, Any],
        cost_records: list[dict[str, Any]],
    ) -> None:
        """Persist the final pipeline result and cost records, mark completed."""
        async with self._session_factory() as db:
            row = await db.get(ResearchSession, session_id)
            if row:
                row.result = result
                row.cost_records = cost_records
                row.status = "completed"
                await db.commit()
        logger.info("Persisted result for session %s", session_id)

    async def get_session(self, session_id: str) -> ResearchSession | None:
        """Fetch a session row by primary key. Returns None if not found."""
        async with self._session_factory() as db:
            return await db.get(ResearchSession, session_id)

    async def list_sessions(self) -> list[ResearchSession]:
        """Return all sessions ordered by created_at descending."""
        async with self._session_factory() as db:
            stmt = select(ResearchSession).order_by(ResearchSession.created_at.desc())
            result = await db.execute(stmt)
            return list(result.scalars().all())
