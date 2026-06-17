"""Tests for human-in-the-loop gate nodes and the interrupt/resume flow.

Fakes and fixtures (install_agents, graph_runner) live in ``conftest.py``.
"""

import pytest


# --- Gate node passthrough behavior (no interrupt when gate disabled) --------

@pytest.mark.asyncio
async def test_plan_gate_passthrough_when_disabled():
    from science_ai.orchestrator.graph.nodes import plan_gate_node
    out = await plan_gate_node({"hitl_gates": [], "plan": {"x": 1}}, {})
    assert out == {}


@pytest.mark.asyncio
async def test_gaps_gate_passthrough_when_disabled():
    from science_ai.orchestrator.graph.nodes import gaps_gate_node
    out = await gaps_gate_node({"hitl_gates": [], "verified_gaps": []}, {})
    assert out == {}


# --- End-to-end interrupt + resume through the real graph --------------------

@pytest.mark.asyncio
async def test_plan_gate_interrupts_then_resumes(install_agents, graph_runner):
    """With the plan gate enabled, the graph pauses, then resumes to completion."""
    install_agents()
    sid = "hitl-plan"

    # Phase 1 with the plan gate — should interrupt before searching.
    saw_interrupt = False
    async for mode, chunk in graph_runner.stream(
        "q", session_id=sid, phase=1, max_papers=5, hitl_gates=["plan"],
    ):
        if mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
            saw_interrupt = True
            break

    assert saw_interrupt, "expected the plan gate to interrupt the graph"

    pending = await graph_runner.get_pending_interrupt(sid)
    assert pending is not None
    assert pending["type"] == "approve_plan"

    # Resume with approval — drain the stream to drive the graph to completion.
    async for _mode, _chunk in graph_runner.resume(sid, {"action": "approve"}):
        pass

    state = await graph_runner.get_state(sid)
    assert state is not None
    # Search ran after approval → papers were found.
    assert state["papers_found"] > 0
    # No longer awaiting input.
    assert await graph_runner.get_pending_interrupt(sid) is None


@pytest.mark.asyncio
async def test_plan_gate_reject_stops_pipeline(install_agents, graph_runner):
    """Rejecting at the plan gate ends the run without searching."""
    install_agents()
    sid = "hitl-reject"

    async for mode, chunk in graph_runner.stream(
        "q", session_id=sid, phase=1, max_papers=5, hitl_gates=["plan"],
    ):
        if mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
            break

    async for _ in graph_runner.resume(sid, {"action": "reject"}):
        pass

    state = await graph_runner.get_state(sid)
    assert state["status"] == "rejected"
    # Rejected before search ran.
    assert state.get("papers_found", 0) == 0


@pytest.mark.asyncio
async def test_no_gate_no_interrupt(install_agents, graph_runner):
    """Without gates, the graph runs straight through (no interrupt)."""
    install_agents()
    sid = "hitl-none"

    async for mode, chunk in graph_runner.stream(
        "q", session_id=sid, phase=1, max_papers=5, hitl_gates=[],
    ):
        assert not (mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk)

    assert await graph_runner.get_pending_interrupt(sid) is None
