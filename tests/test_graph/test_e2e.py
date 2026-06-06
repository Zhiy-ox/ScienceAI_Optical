"""End-to-end graph execution with faked agents.

Validates that the compiled graph runs through ``ainvoke`` and that Feedback
Loop 1 (search refinement) actually cycles and terminates at the max-iteration
bound.

The agent submodules are injected into ``sys.modules`` so the nodes' lazy
imports resolve to in-test fakes — the real agents (and their heavy
litellm/cryptography import chain) are never loaded.
"""

import itertools
import sys
import types

import pytest

from science_ai.orchestrator.feedback import MAX_LOOP_ITERATIONS


class FakePaper:
    def __init__(self, pid: str):
        self.paper_id = pid
        self.title = f"Title {pid}"
        self.abstract = f"Abstract for {pid}"


class FakeSearch:
    """Returns two unique, never-before-seen papers on every call."""

    def __init__(self):
        self._counter = itertools.count()

    async def search(self, query, **kwargs):
        return [FakePaper(f"p{next(self._counter)}") for _ in range(2)]


class FakePlanner:
    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, question, **kwargs):
        return {
            "search_queries": [{"keywords": ["base"], "source": "semantic_scholar"}],
            "scope": {},
        }


class FakeTriage:
    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, question, papers, **kwargs):
        return [{"paper_id": p["paper_id"], "priority": "must_read"} for p in papers]


def _install_fake_agents(monkeypatch, deep_reader_cls):
    """Register fake agent submodules so node-level lazy imports resolve to fakes."""
    def _mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        monkeypatch.setitem(sys.modules, name, m)

    _mod("science_ai.agents.query_planner", QueryPlanner=FakePlanner)
    _mod("science_ai.agents.paper_triage", PaperTriage=FakeTriage)
    _mod("science_ai.agents.deep_reader", DeepReader=deep_reader_cls)


@pytest.mark.asyncio
async def test_phase1_refinement_loop_bounded(monkeypatch):
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

    _install_fake_agents(monkeypatch, NovelReader)

    from science_ai.orchestrator.graph.runner import GraphRunner

    runner = GraphRunner(search_service=FakeSearch(), llm_backend="cli")
    result = await runner.run(
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
async def test_phase1_no_refinement_when_no_new_keywords(monkeypatch):
    class StaticReader:
        def __init__(self, llm, session_id=""):
            pass

        async def run(self, *, paper_text, paper_id="", title="", priority="high", **kwargs):
            # key_component equals the plan keyword → 0% novelty → no refinement
            return {
                "paper_id": paper_id,
                "method": {"key_components": ["base"]},
                "research_problem": {},
            }

    _install_fake_agents(monkeypatch, StaticReader)

    from science_ai.orchestrator.graph.runner import GraphRunner

    runner = GraphRunner(search_service=FakeSearch(), llm_backend="cli")
    result = await runner.run(
        "test", session_id="e2e-norefine", phase=1, max_papers=10,
    )

    assert result["search_refine_count"] == 0
    assert len(result["knowledge_objects"]) == 2


@pytest.mark.asyncio
async def test_get_state_returns_completed_run(monkeypatch):
    """After a run, get_state returns the checkpointed final state."""

    class SimpleReader:
        def __init__(self, llm, session_id=""):
            pass

        async def run(self, *, paper_text, paper_id="", title="", priority="high", **kwargs):
            return {
                "paper_id": paper_id,
                "method": {"key_components": ["base"]},
                "research_problem": {},
            }

    _install_fake_agents(monkeypatch, SimpleReader)

    from science_ai.orchestrator.graph.runner import GraphRunner

    runner = GraphRunner(search_service=FakeSearch(), llm_backend="cli")
    sid = "e2e-getstate"
    await runner.run("test question", session_id=sid, phase=1, max_papers=10)

    state = await runner.get_state(sid)
    assert state is not None
    assert state["session_id"] == sid
    assert state["question"] == "test question"
    assert len(state["knowledge_objects"]) > 0


@pytest.mark.asyncio
async def test_stream_yields_progress_and_updates(monkeypatch):
    """stream() yields both custom progress events and node updates."""

    class SimpleReader:
        def __init__(self, llm, session_id=""):
            pass

        async def run(self, *, paper_text, paper_id="", title="", priority="high", **kwargs):
            return {
                "paper_id": paper_id,
                "method": {"key_components": ["base"]},
                "research_problem": {},
            }

    _install_fake_agents(monkeypatch, SimpleReader)

    from science_ai.orchestrator.graph.runner import GraphRunner

    runner = GraphRunner(search_service=FakeSearch(), llm_backend="cli")

    modes_seen = set()
    progress_stages = []
    node_names = []

    async for mode, chunk in runner.stream(
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
