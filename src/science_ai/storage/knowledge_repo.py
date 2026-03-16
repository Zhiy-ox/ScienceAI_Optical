"""Cross-session knowledge persistence repository.

Saves and loads knowledge objects, gaps, and ideas across research sessions,
enabling knowledge accumulation over time. Uses PostgreSQL JSONB for flexible
schema evolution.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from science_ai.storage.models import Base

logger = logging.getLogger(__name__)


class KnowledgeEntry(Base):
    """Persisted knowledge object from a research session."""

    __tablename__ = "knowledge_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(String, index=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    entry_type: Mapped[str] = mapped_column(
        String, index=True
    )  # knowledge_object | gap | idea | experiment_plan
    title: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())


class KnowledgeRepository:
    """Repository for cross-session knowledge persistence.

    Enables knowledge accumulation: subsequent research sessions can
    reuse previously extracted knowledge objects and discovered gaps.
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def save_knowledge_objects(
        self, session_id: str, knowledge_objects: list[dict[str, Any]]
    ) -> int:
        """Persist knowledge objects from a research session. Returns count saved."""
        saved = 0
        async with self._session_factory() as db:
            for ko in knowledge_objects:
                paper_id = ko.get("paper_id", "")
                entry = KnowledgeEntry(
                    id=f"ko:{paper_id}",
                    paper_id=paper_id,
                    session_id=session_id,
                    entry_type="knowledge_object",
                    title=ko.get("title", ""),
                    data=ko,
                )
                await db.merge(entry)
                saved += 1
            await db.commit()
        logger.info("Saved %d knowledge objects for session %s", saved, session_id)
        return saved

    async def save_gaps(
        self, session_id: str, gaps: list[dict[str, Any]]
    ) -> int:
        """Persist detected gaps."""
        saved = 0
        async with self._session_factory() as db:
            for gap in gaps:
                gap_id = gap.get("gap_id", gap.get("title", f"gap-{saved}"))
                entry = KnowledgeEntry(
                    id=f"gap:{session_id}:{gap_id}",
                    paper_id="",
                    session_id=session_id,
                    entry_type="gap",
                    title=gap.get("title", gap.get("gap_type", "")),
                    data=gap,
                )
                await db.merge(entry)
                saved += 1
            await db.commit()
        logger.info("Saved %d gaps for session %s", saved, session_id)
        return saved

    async def save_ideas(
        self, session_id: str, ideas: list[dict[str, Any]]
    ) -> int:
        """Persist generated ideas."""
        saved = 0
        async with self._session_factory() as db:
            for idea in ideas:
                idea_id = idea.get("title", f"idea-{saved}")
                entry = KnowledgeEntry(
                    id=f"idea:{session_id}:{idea_id}",
                    paper_id="",
                    session_id=session_id,
                    entry_type="idea",
                    title=idea.get("title", ""),
                    data=idea,
                )
                await db.merge(entry)
                saved += 1
            await db.commit()
        logger.info("Saved %d ideas for session %s", saved, session_id)
        return saved

    async def load_knowledge_objects(
        self, paper_ids: list[str] | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Load previously extracted knowledge objects.

        Args:
            paper_ids: Filter by specific paper IDs. None = load all.
            limit: Max entries to return.
        """
        async with self._session_factory() as db:
            stmt = (
                select(KnowledgeEntry)
                .where(KnowledgeEntry.entry_type == "knowledge_object")
                .order_by(KnowledgeEntry.created_at.desc())
                .limit(limit)
            )
            if paper_ids:
                stmt = stmt.where(KnowledgeEntry.paper_id.in_(paper_ids))
            result = await db.execute(stmt)
            entries = result.scalars().all()
            return [e.data for e in entries]

    async def load_gaps(
        self, session_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Load previously detected gaps."""
        async with self._session_factory() as db:
            stmt = (
                select(KnowledgeEntry)
                .where(KnowledgeEntry.entry_type == "gap")
                .order_by(KnowledgeEntry.created_at.desc())
                .limit(limit)
            )
            if session_id:
                stmt = stmt.where(KnowledgeEntry.session_id == session_id)
            result = await db.execute(stmt)
            entries = result.scalars().all()
            return [e.data for e in entries]

    async def load_ideas(
        self, session_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Load previously generated ideas."""
        async with self._session_factory() as db:
            stmt = (
                select(KnowledgeEntry)
                .where(KnowledgeEntry.entry_type == "idea")
                .order_by(KnowledgeEntry.created_at.desc())
                .limit(limit)
            )
            if session_id:
                stmt = stmt.where(KnowledgeEntry.session_id == session_id)
            result = await db.execute(stmt)
            entries = result.scalars().all()
            return [e.data for e in entries]

    async def find_related_knowledge(
        self, question: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Find knowledge entries with titles matching keywords in the question.

        Simple keyword-based lookup. For semantic search, use the vector store.
        """
        keywords = [w.lower() for w in question.split() if len(w) > 3]
        if not keywords:
            return []

        async with self._session_factory() as db:
            # Use ILIKE for case-insensitive partial matching on title
            stmt = (
                select(KnowledgeEntry)
                .order_by(KnowledgeEntry.created_at.desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            entries = result.scalars().all()

            # Filter in Python for flexible keyword matching
            matched = []
            for entry in entries:
                title_lower = (entry.title or "").lower()
                if any(kw in title_lower for kw in keywords):
                    matched.append(entry.data)

            return matched[:limit]

    async def get_session_knowledge_summary(self, session_id: str) -> dict[str, Any]:
        """Get a summary of all knowledge stored for a session."""
        async with self._session_factory() as db:
            stmt = (
                select(KnowledgeEntry)
                .where(KnowledgeEntry.session_id == session_id)
            )
            result = await db.execute(stmt)
            entries = result.scalars().all()

            by_type: dict[str, int] = {}
            for e in entries:
                by_type[e.entry_type] = by_type.get(e.entry_type, 0) + 1

            return {
                "session_id": session_id,
                "total_entries": len(entries),
                "by_type": by_type,
            }
