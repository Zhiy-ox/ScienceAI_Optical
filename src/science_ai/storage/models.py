"""SQLAlchemy ORM models matching the architecture spec."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, Integer, JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Paper(Base):
    """Stores paper metadata and agent outputs."""

    __tablename__ = "papers"

    paper_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_obj: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    critique: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    triage_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String, default="new"
    )  # new | triaged | extracted | deep_read | critiqued
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())


class ResearchSession(Base):
    """Tracks a single research session end-to-end."""

    __tablename__ = "research_sessions"

    session_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    phase: Mapped[int] = mapped_column(Integer, default=3)
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gaps: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ideas: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_tracking: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_records: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String, default="running"
    )  # running | completed | failed
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
