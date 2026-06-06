"""Tests for the feedback-loop decision nodes (trigger + max-iteration bounds).

The decision nodes only read state (no Deps needed), so they can be called with
an empty config.
"""

import pytest

from science_ai.orchestrator.feedback import MAX_LOOP_ITERATIONS
from science_ai.orchestrator.graph.nodes import (
    gap_retry_decision_node,
    idea_regen_decision_node,
    refine_decision_node,
)

CFG: dict = {}


def _ko(components):
    return {"method": {"key_components": components}, "research_problem": {}}


# --- Loop 1: search refinement ----------------------------------------------

@pytest.mark.asyncio
async def test_refine_triggers_on_new_keywords():
    state = {
        "plan": {"search_queries": [{"keywords": ["lidar"]}]},
        "knowledge_objects": [_ko(["metasurface", "phased array", "soliton"])],
        "search_refine_count": 0,
    }
    out = await refine_decision_node(state, CFG)
    assert out["refine_keywords"]  # non-empty
    assert out["search_refine_count"] == 1


@pytest.mark.asyncio
async def test_refine_does_not_trigger_when_keywords_known():
    state = {
        "plan": {"search_queries": [{"keywords": ["metasurface", "phased array"]}]},
        "knowledge_objects": [_ko(["metasurface", "phased array"])],
        "search_refine_count": 0,
    }
    out = await refine_decision_node(state, CFG)
    assert out["refine_keywords"] == []


@pytest.mark.asyncio
async def test_refine_respects_max_iterations():
    state = {
        "plan": {"search_queries": [{"keywords": ["lidar"]}]},
        "knowledge_objects": [_ko(["metasurface", "soliton", "phased array"])],
        "search_refine_count": MAX_LOOP_ITERATIONS,
    }
    out = await refine_decision_node(state, CFG)
    assert out["refine_keywords"] == []


@pytest.mark.asyncio
async def test_refine_no_knowledge_objects():
    state = {
        "plan": {"search_queries": [{"keywords": ["lidar"]}]},
        "knowledge_objects": [],
        "search_refine_count": 0,
    }
    out = await refine_decision_node(state, CFG)
    assert out["refine_keywords"] == []


# --- Loop 2: gap re-detection -----------------------------------------------

@pytest.mark.asyncio
async def test_gap_retry_triggers_on_low_verification():
    # 1 verified out of 5 = 20% < 30% threshold
    vr = [{"status": "verified_gap"}] + [{"status": "known"} for _ in range(4)]
    state = {"verification_results": vr, "gap_retry_count": 0}
    out = await gap_retry_decision_node(state, CFG)
    assert out["gap_retry_pending"] is True
    assert out["gap_retry_count"] == 1
    assert len(out["previous_failures"]) == 4


@pytest.mark.asyncio
async def test_gap_retry_does_not_trigger_when_enough_verified():
    vr = [{"status": "verified_gap"} for _ in range(4)] + [{"status": "known"}]
    state = {"verification_results": vr, "gap_retry_count": 0}
    out = await gap_retry_decision_node(state, CFG)
    assert out["gap_retry_pending"] is False


@pytest.mark.asyncio
async def test_gap_retry_respects_max_iterations():
    vr = [{"status": "known"} for _ in range(5)]
    state = {"verification_results": vr, "gap_retry_count": MAX_LOOP_ITERATIONS}
    out = await gap_retry_decision_node(state, CFG)
    assert out["gap_retry_pending"] is False


@pytest.mark.asyncio
async def test_gap_retry_empty_results():
    state = {"verification_results": [], "gap_retry_count": 0}
    out = await gap_retry_decision_node(state, CFG)
    assert out["gap_retry_pending"] is False


# --- Loop 3: idea regeneration ----------------------------------------------

@pytest.mark.asyncio
async def test_idea_regen_triggers_on_low_feasibility():
    state = {
        "experiment_plans": [
            {"feasibility_score": 0.2, "experiment_plan": {"risks": ["needs fab"]}},
            {"feasibility_score": 0.8},
        ],
        "idea_regen_count": 0,
    }
    out = await idea_regen_decision_node(state, CFG)
    assert out["idea_regen_pending"] is True
    assert out["idea_regen_count"] == 1
    assert "needs fab" in out["regen_constraint"]


@pytest.mark.asyncio
async def test_idea_regen_does_not_trigger_when_feasible():
    state = {
        "experiment_plans": [{"feasibility_score": 0.7}],
        "idea_regen_count": 0,
    }
    out = await idea_regen_decision_node(state, CFG)
    assert out["idea_regen_pending"] is False


@pytest.mark.asyncio
async def test_idea_regen_respects_max_iterations():
    state = {
        "experiment_plans": [{"feasibility_score": 0.1}],
        "idea_regen_count": MAX_LOOP_ITERATIONS,
    }
    out = await idea_regen_decision_node(state, CFG)
    assert out["idea_regen_pending"] is False


@pytest.mark.asyncio
async def test_idea_regen_no_plans():
    state = {"experiment_plans": [], "idea_regen_count": 0}
    out = await idea_regen_decision_node(state, CFG)
    assert out["idea_regen_pending"] is False
