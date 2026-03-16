"""Tests for cross-session knowledge persistence (in-memory SQLite)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from science_ai.storage.knowledge_repo import KnowledgeEntry, KnowledgeRepository


@pytest.fixture
async def repo():
    """Create an in-memory SQLite async engine for testing.

    Only creates the knowledge_entries table (avoids JSONB issues with
    other models that use PostgreSQL-specific types).
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(KnowledgeEntry.metadata.create_all, tables=[KnowledgeEntry.__table__])

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return KnowledgeRepository(factory)


@pytest.mark.asyncio
async def test_save_and_load_knowledge_objects(repo):
    kos = [
        {"paper_id": "p1", "title": "Paper 1", "method": {"core_idea": "CNN"}},
        {"paper_id": "p2", "title": "Paper 2", "method": {"core_idea": "RNN"}},
    ]
    count = await repo.save_knowledge_objects("session-1", kos)
    assert count == 2

    loaded = await repo.load_knowledge_objects()
    assert len(loaded) == 2
    titles = {ko["title"] for ko in loaded}
    assert "Paper 1" in titles
    assert "Paper 2" in titles


@pytest.mark.asyncio
async def test_save_and_load_gaps(repo):
    gaps = [
        {"gap_id": "g1", "title": "Missing OPA beam steering", "gap_type": "method_gap"},
    ]
    count = await repo.save_gaps("session-1", gaps)
    assert count == 1

    loaded = await repo.load_gaps(session_id="session-1")
    assert len(loaded) == 1
    assert loaded[0]["gap_id"] == "g1"


@pytest.mark.asyncio
async def test_save_and_load_ideas(repo):
    ideas = [
        {"title": "Hybrid OPA design", "strategy": "combination"},
    ]
    count = await repo.save_ideas("session-1", ideas)
    assert count == 1

    loaded = await repo.load_ideas()
    assert len(loaded) == 1
    assert loaded[0]["title"] == "Hybrid OPA design"


@pytest.mark.asyncio
async def test_load_by_paper_ids(repo):
    kos = [
        {"paper_id": "p1", "title": "Paper 1"},
        {"paper_id": "p2", "title": "Paper 2"},
        {"paper_id": "p3", "title": "Paper 3"},
    ]
    await repo.save_knowledge_objects("s1", kos)

    loaded = await repo.load_knowledge_objects(paper_ids=["p1", "p3"])
    assert len(loaded) == 2
    ids = {ko["paper_id"] for ko in loaded}
    assert ids == {"p1", "p3"}


@pytest.mark.asyncio
async def test_session_knowledge_summary(repo):
    await repo.save_knowledge_objects("s1", [
        {"paper_id": "p1", "title": "P1"},
    ])
    await repo.save_gaps("s1", [
        {"gap_id": "g1", "title": "Gap"},
    ])
    await repo.save_ideas("s1", [
        {"title": "Idea 1"},
        {"title": "Idea 2"},
    ])

    summary = await repo.get_session_knowledge_summary("s1")
    assert summary["total_entries"] == 4
    assert summary["by_type"]["knowledge_object"] == 1
    assert summary["by_type"]["gap"] == 1
    assert summary["by_type"]["idea"] == 2


@pytest.mark.asyncio
async def test_find_related_knowledge(repo):
    await repo.save_knowledge_objects("s1", [
        {"paper_id": "p1", "title": "Optical phased array beam steering"},
        {"paper_id": "p2", "title": "Deep learning for image classification"},
    ])

    related = await repo.find_related_knowledge("optical phased arrays")
    assert len(related) == 1
    assert related[0]["paper_id"] == "p1"
