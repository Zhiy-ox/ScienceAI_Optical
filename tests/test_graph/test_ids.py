"""Canonical ID assignment + cross-reference linkage through the pipeline.

The agents emit placeholder IDs ("GAP-XXX" / "g1"); the nodes overwrite them
with deterministic sequential IDs and keep the verification → idea → experiment
linkage stable. These tests drive a full Phase 3 run with multi-item fakes and
assert the IDs end up canonical and consistent.
"""

import pytest

from science_ai.orchestrator.graph.ids import assign_sequential_ids, stamp_linked_id
from science_ai.orchestrator.graph.runner import GraphRunner


# --- unit-level: the helpers themselves ---

def test_assign_sequential_ids_overwrites_and_pads():
    items = [{"gap_id": "junk"}, {}, {"gap_id": "GAP-XXX"}]
    out = assign_sequential_ids(items, "GAP")
    assert [i["gap_id"] for i in out] == ["GAP-001", "GAP-002", "GAP-003"]


def test_assign_sequential_ids_custom_key():
    items = [{}, {}]
    assign_sequential_ids(items, "IDEA")
    assert [i["idea_id"] for i in items] == ["IDEA-001", "IDEA-002"]


def test_stamp_linked_id_copies_when_present_else_noop():
    target = {}
    stamp_linked_id(target, {"gap_id": "GAP-007"}, "gap_id")
    assert target["gap_id"] == "GAP-007"
    # No source key → target untouched.
    stamp_linked_id(target, {}, "idea_id")
    assert "idea_id" not in target


# --- integration: IDs propagate through a real Phase 3 graph run ---

class MultiGapDetector:
    """Emits three gaps with unreliable/placeholder IDs."""

    def __init__(self, llm, session_id="", embedding_fn=None, graph_store=None):
        pass

    async def run(self, *, knowledge_objects, critiques, **kwargs):
        return [
            {"gap_id": "GAP-XXX", "description": "gap one"},
            {"gap_id": "GAP-XXX", "description": "gap two"},
            {"gap_id": "dup", "description": "gap three"},
        ]


class EchoVerifier:
    """Verifies all gaps but emits a placeholder gap_id (must be re-stamped)."""

    def __init__(self, llm, session_id="", search_service=None):
        pass

    async def run(self, *, gaps, **kwargs):
        return [{"gap_id": "GAP-XXX", "status": "verified_gap"} for _ in gaps]


class GapRefIdeaGenerator:
    """One idea per verified gap, referencing that gap's id as source_gap."""

    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, verified_gaps, knowledge_objects, user_background="", **kwargs):
        return [
            {"idea_id": "IDEA-XXX", "title": f"idea {i}", "source_gap": g["gap_id"]}
            for i, g in enumerate(verified_gaps)
        ]


@pytest.mark.asyncio
async def test_ids_are_canonical_and_linked_through_phase3(install_agents, fake_search):
    install_agents(
        GapDetector=MultiGapDetector,
        VerificationAgent=EchoVerifier,
        IdeaGenerator=GapRefIdeaGenerator,
    )
    runner = GraphRunner(search_service=fake_search, llm_backend="cli")
    result = await runner.run("q", session_id="ids-p3", phase=3, max_papers=5)

    # Gaps got canonical sequential IDs despite identical placeholders.
    assert [g["gap_id"] for g in result["gaps"]] == ["GAP-001", "GAP-002", "GAP-003"]

    # Verification results were re-stamped to the canonical gap IDs (by position)
    # and carry the gap descriptions.
    vr = result["verification_results"]
    assert [v["gap_id"] for v in vr] == ["GAP-001", "GAP-002", "GAP-003"]
    assert vr[0]["description"] == "gap one"

    # Ideas got canonical IDs and their source_gap points at a real gap ID.
    ideas = result["ideas"]
    assert [i["idea_id"] for i in ideas] == ["IDEA-001", "IDEA-002", "IDEA-003"]
    valid_gap_ids = {g["gap_id"] for g in result["verified_gaps"]}
    assert all(i["source_gap"] in valid_gap_ids for i in ideas)

    # Experiment plans link back to their source idea's canonical ID.
    plans = result["experiment_plans"]
    idea_ids = {i["idea_id"] for i in ideas}
    assert plans and all(p["idea_id"] in idea_ids for p in plans)
