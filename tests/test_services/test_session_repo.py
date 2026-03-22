"""Tests for SessionRepository using in-memory SQLite."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from science_ai.storage.models import ResearchSession
from science_ai.storage.session_repo import SessionRepository


@pytest.fixture
async def repo():
    """In-memory SQLite engine scoped to a single test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            ResearchSession.metadata.create_all,
            tables=[ResearchSession.__table__],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return SessionRepository(factory)


@pytest.mark.asyncio
async def test_create_and_get_session(repo):
    await repo.create_session("s1", "What are optical phased arrays?", phase=3)
    session = await repo.get_session("s1")

    assert session is not None
    assert session.session_id == "s1"
    assert session.question == "What are optical phased arrays?"
    assert session.phase == 3
    assert session.status == "running"


@pytest.mark.asyncio
async def test_get_session_returns_none_for_missing_id(repo):
    result = await repo.get_session("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_update_status(repo):
    await repo.create_session("s2", "Test question", phase=1)
    await repo.update_status("s2", "completed")

    session = await repo.get_session("s2")
    assert session.status == "completed"


@pytest.mark.asyncio
async def test_update_result_stores_full_payload(repo):
    await repo.create_session("s3", "Beam steering efficiency", phase=2)

    result = {"status": "completed", "plan": {"queries": ["q1"]}, "papers_found": 5}
    cost_records = [
        {
            "call_id": "c1",
            "agent": "query_planner",
            "model": "gpt-4o",
            "reasoning_effort": "medium",
            "input_tokens": 100,
            "output_tokens": 50,
            "cached_tokens": 0,
            "cost_usd": 0.001,
            "timestamp": 1700000000.0,
        }
    ]
    await repo.update_result("s3", result, cost_records)

    session = await repo.get_session("s3")
    assert session.status == "completed"
    assert session.result["plan"]["queries"] == ["q1"]
    assert len(session.cost_records) == 1
    assert session.cost_records[0]["agent"] == "query_planner"


@pytest.mark.asyncio
async def test_list_sessions_returns_all(repo):
    await repo.create_session("s4", "Q1", phase=1)
    await repo.create_session("s5", "Q2", phase=2)
    await repo.create_session("s6", "Q3", phase=3)

    sessions = await repo.list_sessions()
    assert len(sessions) == 3
    ids = {s.session_id for s in sessions}
    assert ids == {"s4", "s5", "s6"}


@pytest.mark.asyncio
async def test_list_sessions_empty(repo):
    sessions = await repo.list_sessions()
    assert sessions == []


@pytest.mark.asyncio
async def test_update_status_noop_for_missing_id(repo):
    # Should not raise even if the session doesn't exist
    await repo.update_status("ghost", "failed")


@pytest.mark.asyncio
async def test_failed_status_persisted(repo):
    await repo.create_session("s7", "Experiment design", phase=3)
    await repo.update_status("s7", "failed")

    session = await repo.get_session("s7")
    assert session.status == "failed"
    assert session.result is None
