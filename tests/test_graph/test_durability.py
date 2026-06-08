"""Durable checkpoint / resume-after-restart tests.

These exercise the same ``BaseCheckpointSaver`` contract that the production
``AsyncPostgresSaver`` implements, but with a file-backed SQLite saver so the
durability is real (written to disk) and verifiable without a live database:
a second GraphRunner over the same file — standing in for a server restart —
reads state written by the first.
"""

import pytest

pytest.importorskip("langgraph.checkpoint.sqlite.aio")

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402

from science_ai.orchestrator.graph.runner import GraphRunner  # noqa: E402


@pytest.mark.asyncio
async def test_interrupted_session_survives_restart(tmp_path, install_agents, fake_search):
    """A HITL interrupt persists to disk and is resumable by a fresh runner."""
    install_agents()
    db = str(tmp_path / "checkpoints.sqlite")
    sid = "durable-resume"

    # --- "Process 1": start a gated run; pause at the plan gate. ---
    # The stream is consumed to its natural end (not broken early): abandoning
    # an async-checkpointer generator mid-flight cancels the interrupt write.
    async with AsyncSqliteSaver.from_conn_string(db) as saver1:
        runner1 = GraphRunner(
            checkpointer=saver1, search_service=fake_search, llm_backend="cli",
        )
        saw_interrupt = False
        async for mode, chunk in runner1.stream(
            "q", session_id=sid, phase=1, max_papers=5, hitl_gates=["plan"],
        ):
            if mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
                saw_interrupt = True
        assert saw_interrupt
        assert await runner1.get_pending_interrupt(sid) is not None

    # saver1's connection is now closed — the interrupt lives only on disk.

    # --- "Process 2": brand-new saver + runner over the same file. ---
    async with AsyncSqliteSaver.from_conn_string(db) as saver2:
        runner2 = GraphRunner(
            checkpointer=saver2, search_service=fake_search, llm_backend="cli",
        )

        # The pending interrupt was persisted and is readable after "restart".
        pending = await runner2.get_pending_interrupt(sid)
        assert pending is not None
        assert pending["type"] == "approve_plan"

        # And the new instance can resume it to completion.
        async for _ in runner2.resume(sid, {"action": "approve"}):
            pass

        state = await runner2.get_state(sid)
        assert state is not None
        assert state["papers_found"] > 0          # search ran after the resume
        assert await runner2.get_pending_interrupt(sid) is None


@pytest.mark.asyncio
async def test_completed_run_state_is_durable(tmp_path, install_agents, fake_search):
    """A completed run's final state is readable by a fresh runner over the same store."""
    install_agents()
    db = str(tmp_path / "done.sqlite")
    sid = "durable-done"

    async with AsyncSqliteSaver.from_conn_string(db) as saver1:
        runner1 = GraphRunner(
            checkpointer=saver1, search_service=fake_search, llm_backend="cli",
        )
        await runner1.run("durable q", session_id=sid, phase=1, max_papers=5)

    # New saver + runner over the same file — no search needed (run is done).
    async with AsyncSqliteSaver.from_conn_string(db) as saver2:
        runner2 = GraphRunner(checkpointer=saver2, llm_backend="cli")
        state = await runner2.get_state(sid)
        assert state is not None
        assert state["question"] == "durable q"
        assert len(state["knowledge_objects"]) > 0
