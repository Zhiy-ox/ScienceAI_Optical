"""End-to-end Phase 2 and Phase 3 graph execution.

Covers the deeper pipeline that the Phase 1 e2e suite does not reach:
  - Phase 2: critique → index → gap detection → verification, and Feedback
    Loop 2 (gap-detection retry on weak verification).
  - Phase 3: ideation → experiment planning → report, Feedback Loop 3 (idea
    regeneration on infeasible experiments), and the gaps approval gate.

Fakes and fixtures (install_agents, graph_runner) live in conftest.py.
"""

import pytest

from science_ai.orchestrator.feedback import MAX_LOOP_ITERATIONS


# --- Phase 2 ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase2_full_flow(install_agents, graph_runner):
    """Phase 2 runs through critique → gap detection → verification, then stops."""
    install_agents()
    result = await graph_runner.run("q", session_id="e2e-p2", phase=2, max_papers=10)

    assert len(result["knowledge_objects"]) == 2
    assert len(result["critiques"]) == 2            # one per KO (operator.add)
    assert len(result["gaps"]) >= 1
    assert len(result["verified_gaps"]) >= 1        # default verifier passes all
    # Phase 2 stops before ideation.
    assert result.get("ideas", []) == []
    assert result.get("report") is None
    # Healthy verification → Loop 2 never fired.
    assert result["gap_retry_count"] == 0


class _FailingVerifier:
    """Marks every gap as not novel → verification ratio 0 → Loop 2 fires."""

    def __init__(self, llm, session_id="", search_service=None):
        pass

    async def run(self, *, gaps, **kwargs):
        return [{**g, "status": "not_novel"} for g in gaps]


@pytest.mark.asyncio
async def test_phase2_gap_retry_loop_bounded(install_agents, graph_runner):
    """Weak verification re-runs gap detection, bounded by MAX_LOOP_ITERATIONS."""
    install_agents(VerificationAgent=_FailingVerifier)
    result = await graph_runner.run(
        "q", session_id="e2e-p2-retry", phase=2, max_papers=10,
    )

    # Loop 2 fires every pass (verification always fails) up to the bound.
    assert result["gap_retry_count"] == MAX_LOOP_ITERATIONS
    assert result.get("verified_gaps", []) == []


# --- Phase 3 ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase3_full_flow(install_agents, graph_runner):
    """Phase 3 runs the whole pipeline through to a written report."""
    install_agents()
    result = await graph_runner.run("q", session_id="e2e-p3", phase=3, max_papers=10)

    assert len(result["knowledge_objects"]) == 2
    assert len(result["critiques"]) == 2
    assert len(result["verified_gaps"]) >= 1
    assert len(result["ideas"]) >= 1
    assert len(result["experiment_plans"]) >= 1
    assert result["report"] is not None
    assert result["status"] == "completed"
    # No feedback loop fired on the happy path.
    assert result["search_refine_count"] == 0
    assert result["gap_retry_count"] == 0
    assert result["idea_regen_count"] == 0


class _InfeasiblePlanner:
    """Plans an infeasible experiment (feasibility < 0.4) → Loop 3 fires."""

    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, idea, knowledge_objects, **kwargs):
        return {
            "idea": idea.get("title"),
            "feasibility_score": 0.1,
            "experiment_plan": {"risks": ["needs unavailable equipment"]},
        }


@pytest.mark.asyncio
async def test_phase3_idea_regen_loop_bounded(install_agents, graph_runner):
    """Infeasible experiments regenerate ideas, bounded, then write the report."""
    install_agents(ExperimentPlanner=_InfeasiblePlanner)
    result = await graph_runner.run(
        "q", session_id="e2e-p3-regen", phase=3, max_papers=10,
    )

    assert result["idea_regen_count"] == MAX_LOOP_ITERATIONS
    # Despite the loop, the pipeline still finishes and writes a report.
    assert result["report"] is not None
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_phase3_gaps_gate_interrupts_then_resumes(install_agents, graph_runner):
    """The gaps approval gate pauses Phase 3 before ideation, then resumes."""
    install_agents()
    sid = "e2e-p3-gapsgate"

    saw_interrupt = False
    async for mode, chunk in graph_runner.stream(
        "q", session_id=sid, phase=3, max_papers=10, hitl_gates=["gaps"],
    ):
        if mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
            saw_interrupt = True
            break

    assert saw_interrupt, "expected the gaps gate to interrupt the graph"
    pending = await graph_runner.get_pending_interrupt(sid)
    assert pending is not None
    assert pending["type"] == "approve_gaps"

    # Approve → runs to completion with ideas and a report.
    async for _mode, _chunk in graph_runner.resume(sid, {"action": "approve"}):
        pass

    state = await graph_runner.get_state(sid)
    assert state["status"] == "completed"
    assert state["report"] is not None
    assert len(state["ideas"]) >= 1
