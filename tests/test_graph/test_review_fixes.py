"""Regression tests for the code-review fixes.

Covers:
- the shared cost tracker (LLM client records must reach session summaries)
- HITL interrupts surviving loss of the in-memory session overlay (restart)
- graph runs surviving an SSE client disconnect (decoupled execution)
"""

from unittest.mock import AsyncMock, patch

import pytest

import science_ai.api.routes as routes
from science_ai.api.schemas import ResumeRequest
from science_ai.orchestrator.graph.runner import GraphRunner


# --- Shared cost tracker ----------------------------------------------------

def test_runner_llm_records_into_the_summary_tracker(fake_search):
    """The LLM client and the per-session summaries must share one tracker.

    A private tracker on the client would silently report $0 for every run.
    """
    runner = GraphRunner(search_service=fake_search, llm_backend="cli")
    assert runner.llm.cost_tracker is runner.cost_tracker


@pytest.mark.asyncio
async def test_llm_call_costs_show_up_in_run_summary(install_agents, fake_search):
    install_agents()
    runner = GraphRunner(search_service=fake_search, llm_backend="cli")
    sid = "cost-wiring"

    # Simulate what the LLM client does on every call: record into its tracker.
    runner.llm.cost_tracker.record_call(
        session_id=sid, agent="query_planner", model="claude-opus-4-6",
        reasoning_effort="medium", input_tokens=1000, output_tokens=200,
    )

    result = await runner.run("q", session_id=sid, phase=1, max_papers=5)
    assert result["cost_summary"]["total_usd"] > 0
    assert result["cost_summary"]["call_count"] == 1


# --- HITL interrupt survives loss of the in-memory overlay -------------------

async def _interrupt_at_plan_gate(runner: GraphRunner, sid: str) -> None:
    """Drive a session into the plan gate, draining the stream fully."""
    async for _mode, _chunk in runner.stream(
        "q", session_id=sid, phase=1, max_papers=5, hitl_gates=["plan"],
    ):
        pass
    assert await runner.get_pending_interrupt(sid) is not None


@pytest.mark.asyncio
async def test_status_surfaces_checkpointed_interrupt_after_restart(
    install_agents, fake_search,
):
    install_agents()
    runner = GraphRunner(search_service=fake_search, llm_backend="cli")
    sid = "restart-status"
    await _interrupt_at_plan_gate(runner, sid)

    # Simulate a restart: the in-memory overlay is gone, the checkpoint is not.
    routes._sessions.pop(sid, None)
    with patch.object(routes, "_graph_runner", runner):
        status = await routes._graph_session_status(sid)

    assert status.status == "awaiting_input"
    assert status.interrupt is not None
    assert status.interrupt["type"] == "approve_plan"
    # The overlay was rebuilt so a subsequent /resume finds the session.
    assert routes._sessions[sid]["status"] == "awaiting_input"
    routes._sessions.pop(sid, None)


@pytest.mark.asyncio
async def test_resume_works_without_in_memory_session(install_agents, fake_search):
    install_agents()
    runner = GraphRunner(search_service=fake_search, llm_backend="cli")
    sid = "restart-resume"
    await _interrupt_at_plan_gate(runner, sid)

    routes._sessions.pop(sid, None)
    with (
        patch.object(routes, "_graph_runner", runner),
        patch.object(routes, "_session_repo", AsyncMock()),
    ):
        response = await routes.resume_research(sid, ResumeRequest(action="approve"))
        frames = [frame async for frame in response.body_iterator]

    assert any("event: done" in f for f in frames)
    state = await runner.get_state(sid)
    assert state["papers_found"] > 0
    assert await runner.get_pending_interrupt(sid) is None
    routes._sessions.pop(sid, None)


# --- Run survives client disconnect ------------------------------------------

@pytest.mark.asyncio
async def test_stream_run_survives_client_disconnect(install_agents, fake_search):
    """Closing the SSE response mid-run must not abort the pipeline."""
    install_agents()
    runner = GraphRunner(search_service=fake_search, llm_backend="cli")
    sid = "disconnect"
    routes._sessions[sid] = {
        "status": "created", "question": "q", "phase": 1, "max_papers": 5,
        "user_background": "", "source": "web", "hitl_gates": [],
        "interrupt": None, "result": None,
    }

    with (
        patch.object(routes, "_graph_runner", runner),
        patch.object(routes, "_session_repo", AsyncMock()),
    ):
        response = await routes.stream_research(sid)
        # Read a single frame, then drop the connection.
        agen = response.body_iterator
        first = await agen.__anext__()
        assert "event: progress" in first
        await agen.aclose()

        # The detached driver task finishes the run regardless.
        await routes._sessions[sid]["task"]

    assert routes._sessions[sid]["status"] == "completed"
    state = await runner.get_state(sid)
    assert state["papers_found"] > 0
    routes._sessions.pop(sid, None)
