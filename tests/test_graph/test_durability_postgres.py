"""Durable resume against the *production* AsyncPostgresSaver.

The SQLite durability tests verify the BaseCheckpointSaver contract on disk; this
one exercises the exact saver used in production. It is gated on a reachable
Postgres: set ``TEST_CHECKPOINTER_DSN`` (psycopg v3 DSN, e.g.
``postgresql://scienceai:scienceai@localhost:5432/scienceai``) to run it, or
``docker compose up -d postgres`` and rely on the default DSN below. When
Postgres is unavailable the test skips cleanly, so CI without a database stays
green while a deployment with one gets real coverage.
"""

import os
import uuid

import pytest

pytest.importorskip("langgraph.checkpoint.postgres.aio")
pytest.importorskip("psycopg")

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: E402
from psycopg import AsyncConnection  # noqa: E402

from science_ai.orchestrator.graph.runner import GraphRunner  # noqa: E402

_DSN = os.environ.get(
    "TEST_CHECKPOINTER_DSN",
    "postgresql://scienceai:scienceai@localhost:5432/scienceai",
)


async def _connect_or_skip():
    try:
        return await AsyncConnection.connect(_DSN, autocommit=True, prepare_threshold=0)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Postgres not reachable at {_DSN}: {exc}")


@pytest.mark.asyncio
async def test_interrupt_survives_restart_on_postgres(install_agents, fake_search):
    """A HITL interrupt written by one runner is resumable by a fresh one."""
    install_agents()
    sid = f"pg-resume-{uuid.uuid4().hex[:8]}"

    # --- "Process 1": pause at the plan gate, fully draining the stream so the
    #     async saver flushes the interrupt checkpoint. ---
    conn1 = await _connect_or_skip()
    try:
        saver1 = AsyncPostgresSaver(conn1)
        await saver1.setup()
        runner1 = GraphRunner(checkpointer=saver1, search_service=fake_search, llm_backend="cli")
        saw_interrupt = False
        async for mode, chunk in runner1.stream(
            "q", session_id=sid, phase=1, max_papers=5, hitl_gates=["plan"],
        ):
            if mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
                saw_interrupt = True
        assert saw_interrupt
        assert await runner1.get_pending_interrupt(sid) is not None
    finally:
        await conn1.close()

    # --- "Process 2": brand-new connection + runner over the same database. ---
    conn2 = await _connect_or_skip()
    try:
        saver2 = AsyncPostgresSaver(conn2)
        await saver2.setup()
        runner2 = GraphRunner(checkpointer=saver2, search_service=fake_search, llm_backend="cli")

        pending = await runner2.get_pending_interrupt(sid)
        assert pending is not None and pending["type"] == "approve_plan"

        async for _ in runner2.resume(sid, {"action": "approve"}):
            pass

        state = await runner2.get_state(sid)
        assert state is not None
        assert state["papers_found"] > 0
        assert await runner2.get_pending_interrupt(sid) is None
    finally:
        await conn2.close()
