"""Tests for checkpointer factory and state persistence."""

import pytest

from langgraph.checkpoint.memory import MemorySaver


@pytest.fixture(autouse=True)
def _reset_singleton():
    from science_ai.orchestrator.graph.checkpointer import reset_checkpointer
    reset_checkpointer()
    yield
    reset_checkpointer()


@pytest.mark.asyncio
async def test_get_checkpointer_returns_memory_saver_when_no_dsn(monkeypatch):
    """With empty DSN and non-Postgres database_url, falls back to MemorySaver."""
    monkeypatch.setattr("science_ai.config.settings.checkpointer_dsn", "")
    monkeypatch.setattr("science_ai.config.settings.database_url", "sqlite:///test.db")

    from science_ai.orchestrator.graph.checkpointer import get_checkpointer
    cp = await get_checkpointer()
    assert isinstance(cp, MemorySaver)


@pytest.mark.asyncio
async def test_get_checkpointer_returns_same_instance(monkeypatch):
    """Singleton: second call returns the same object."""
    monkeypatch.setattr("science_ai.config.settings.checkpointer_dsn", "")
    monkeypatch.setattr("science_ai.config.settings.database_url", "sqlite:///test.db")

    from science_ai.orchestrator.graph.checkpointer import get_checkpointer
    cp1 = await get_checkpointer()
    cp2 = await get_checkpointer()
    assert cp1 is cp2


@pytest.mark.asyncio
async def test_get_checkpointer_falls_back_on_bad_dsn(monkeypatch):
    """If Postgres is unreachable, falls back to MemorySaver."""
    monkeypatch.setattr(
        "science_ai.config.settings.checkpointer_dsn",
        "postgresql://bad:bad@localhost:1/nonexistent",
    )
    monkeypatch.setattr("science_ai.config.settings.database_url", "")

    from science_ai.orchestrator.graph.checkpointer import get_checkpointer
    cp = await get_checkpointer()
    assert isinstance(cp, MemorySaver)


@pytest.mark.asyncio
async def test_get_state_returns_none_for_unknown_session(monkeypatch):
    """get_state on a session that never ran returns None."""
    monkeypatch.setattr("science_ai.config.settings.checkpointer_dsn", "")
    monkeypatch.setattr("science_ai.config.settings.database_url", "sqlite:///test.db")

    from science_ai.orchestrator.graph.runner import GraphRunner
    runner = GraphRunner(llm_backend="cli")
    state = await runner.get_state("nonexistent-session")
    assert state is None
