"""End-to-end Phase 1 graph execution with faked agents.

Validates that the compiled graph runs through ``ainvoke``/``astream`` and that
Feedback Loop 1 (search refinement) actually cycles and terminates at the
max-iteration bound. Fakes and fixtures live in ``conftest.py``.
"""

import pytest

from science_ai.orchestrator.feedback import MAX_LOOP_ITERATIONS


@pytest.mark.asyncio
async def test_phase1_refinement_loop_bounded(install_agents, graph_runner):
    class NovelReader:
        """Every paper yields a brand-new keyword, so refinement keeps firing."""

        def __init__(self, llm, session_id=""):
            pass

        async def run(self, *, paper_text, paper_id="", title="", priority="high", **kwargs):
            return {
                "paper_id": paper_id,
                "method": {"key_components": [f"novel-{paper_id}"]},
                "research_problem": {},
            }

    install_agents(DeepReader=NovelReader)

    result = await graph_runner.run(
        "What are advances in optical phased arrays?",
        session_id="e2e-phase1",
        phase=1,
        max_papers=10,
    )

    # Loop 1 fires every pass (always-novel keywords) up to the bound, then stops.
    assert result["search_refine_count"] == MAX_LOOP_ITERATIONS
    # Phase 1 stops after deep reading — no critiques/gaps produced.
    assert result.get("critiques", []) == []
    assert result.get("gaps", []) == []
    assert len(result["knowledge_objects"]) > 0


@pytest.mark.asyncio
async def test_phase1_no_refinement_when_no_new_keywords(install_agents, graph_runner):
    # Default DeepReader (StaticReader) emits the plan keyword → 0% novelty.
    install_agents()

    result = await graph_runner.run(
        "test", session_id="e2e-norefine", phase=1, max_papers=10,
    )

    assert result["search_refine_count"] == 0
    assert len(result["knowledge_objects"]) == 2


@pytest.mark.asyncio
async def test_get_state_returns_completed_run(install_agents, graph_runner):
    """After a run, get_state returns the checkpointed final state."""
    install_agents()

    sid = "e2e-getstate"
    await graph_runner.run("test question", session_id=sid, phase=1, max_papers=10)

    state = await graph_runner.get_state(sid)
    assert state is not None
    assert state["session_id"] == sid
    assert state["question"] == "test question"
    assert len(state["knowledge_objects"]) > 0


@pytest.mark.asyncio
async def test_stream_yields_progress_and_updates(install_agents, graph_runner):
    """stream() yields both custom progress events and node updates."""
    install_agents()

    modes_seen = set()
    progress_stages = []
    node_names = []

    async for mode, chunk in graph_runner.stream(
        "stream test", session_id="e2e-stream", phase=1, max_papers=10,
    ):
        modes_seen.add(mode)
        if mode == "custom":
            progress_stages.append(chunk.get("stage"))
        elif mode == "updates":
            node_names.extend(chunk.keys())

    # Both stream modes are exercised.
    assert "custom" in modes_seen
    assert "updates" in modes_seen
    # Human-readable progress for the early stages was emitted.
    assert "plan" in progress_stages
    assert "search" in progress_stages
    # Node updates flowed through.
    assert "plan" in node_names
