"""Tests for human-in-the-loop gate nodes and interrupt/resume flow."""

import itertools
import sys
import types

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

class FakePaper:
    def __init__(self, pid):
        self.paper_id = pid
        self.title = f"Title {pid}"
        self.abstract = f"Abstract {pid}"


class FakeSearch:
    def __init__(self):
        self._c = itertools.count()

    async def search(self, query, **kwargs):
        return [FakePaper(f"p{next(self._c)}") for _ in range(2)]


class FakePlanner:
    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, question, **kwargs):
        return {"search_queries": [{"keywords": ["base"]}], "scope": {}}


class FakeTriage:
    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, question, papers, **kwargs):
        return [{"paper_id": p["paper_id"], "priority": "must_read"} for p in papers]


class StaticReader:
    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, paper_text, paper_id="", title="", priority="high", **kwargs):
        return {"paper_id": paper_id, "method": {"key_components": ["base"]}, "research_problem": {}}


def _install_fakes(monkeypatch):
    def _mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        monkeypatch.setitem(sys.modules, name, m)

    _mod("science_ai.agents.query_planner", QueryPlanner=FakePlanner)
    _mod("science_ai.agents.paper_triage", PaperTriage=FakeTriage)
    _mod("science_ai.agents.deep_reader", DeepReader=StaticReader)


@pytest.mark.asyncio
async def test_plan_gate_interrupts_then_resumes(monkeypatch):
    """With the plan gate enabled, the graph pauses, then resumes to completion."""
    _install_fakes(monkeypatch)

    from science_ai.orchestrator.graph.runner import GraphRunner

    runner = GraphRunner(search_service=FakeSearch(), llm_backend="cli")
    sid = "hitl-plan"

    # Phase 1 with the plan gate — should interrupt before searching.
    saw_interrupt = False
    async for mode, chunk in runner.stream(
        "q", session_id=sid, phase=1, max_papers=5, hitl_gates=["plan"],
    ):
        if mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
            saw_interrupt = True
            break

    assert saw_interrupt, "expected the plan gate to interrupt the graph"

    pending = await runner.get_pending_interrupt(sid)
    assert pending is not None
    assert pending["type"] == "approve_plan"

    # Resume with approval — should now run to completion (no papers read yet).
    final_status = None
    async for mode, chunk in runner.resume(sid, {"action": "approve"}):
        if mode == "updates" and isinstance(chunk, dict):
            for upd in chunk.values():
                if isinstance(upd, dict) and upd.get("status"):
                    final_status = upd["status"]

    state = await runner.get_state(sid)
    assert state is not None
    # Search ran after approval → papers were found.
    assert state["papers_found"] > 0
    # No longer awaiting input.
    assert await runner.get_pending_interrupt(sid) is None


@pytest.mark.asyncio
async def test_plan_gate_reject_stops_pipeline(monkeypatch):
    """Rejecting at the plan gate ends the run without searching."""
    _install_fakes(monkeypatch)

    from science_ai.orchestrator.graph.runner import GraphRunner

    runner = GraphRunner(search_service=FakeSearch(), llm_backend="cli")
    sid = "hitl-reject"

    async for mode, chunk in runner.stream(
        "q", session_id=sid, phase=1, max_papers=5, hitl_gates=["plan"],
    ):
        if mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
            break

    async for _ in runner.resume(sid, {"action": "reject"}):
        pass

    state = await runner.get_state(sid)
    assert state["status"] == "rejected"
    # Rejected before search ran.
    assert state.get("papers_found", 0) == 0


@pytest.mark.asyncio
async def test_no_gate_no_interrupt(monkeypatch):
    """Without gates, the graph runs straight through (no interrupt)."""
    _install_fakes(monkeypatch)

    from science_ai.orchestrator.graph.runner import GraphRunner

    runner = GraphRunner(search_service=FakeSearch(), llm_backend="cli")
    sid = "hitl-none"

    async for mode, chunk in runner.stream(
        "q", session_id=sid, phase=1, max_papers=5, hitl_gates=[],
    ):
        assert not (mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk)

    assert await runner.get_pending_interrupt(sid) is None
