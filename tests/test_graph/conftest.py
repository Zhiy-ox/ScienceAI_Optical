"""Shared fixtures and fake agents for the graph orchestrator tests.

The real agents pull in the litellm/cryptography import chain; these fakes are
injected into ``sys.modules`` so the nodes' lazy ``from science_ai.agents...``
imports resolve to lightweight stand-ins. The whole agent set is installed by
default (unexecuted nodes never import, so installing extras is harmless), and
any single agent can be overridden per-test to drive a specific feedback loop:

    def test_x(install_agents, graph_runner):
        install_agents(DeepReader=NovelReader)   # override one, keep the rest
        result = await graph_runner.run(...)
"""

from __future__ import annotations

import itertools
import sys
import types

import pytest


# --------------------------------------------------------------------------
# Fake papers + search service
# --------------------------------------------------------------------------

class FakePaper:
    def __init__(self, pid: str):
        self.paper_id = pid
        self.title = f"Title {pid}"
        self.abstract = f"Abstract for {pid}"


class FakeSearch:
    """Returns ``papers_per_call`` unique, never-before-seen papers per call.

    Distinct papers per call are what let Feedback Loop 1 (search refinement)
    discover new material and cycle. A larger ``papers_per_call`` is used to
    exercise the parallel fan-out concurrency cap.
    """

    def __init__(self, papers_per_call: int = 2) -> None:
        self._counter = itertools.count()
        self._papers_per_call = papers_per_call

    async def search(self, query, **kwargs):
        return [FakePaper(f"p{next(self._counter)}") for _ in range(self._papers_per_call)]


# --------------------------------------------------------------------------
# Default fake agents (one per pipeline stage)
# --------------------------------------------------------------------------

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


class StaticReader:
    """Deep reader whose key component equals the plan keyword.

    0% keyword novelty → Feedback Loop 1 never fires. This is the default; tests
    that want refinement override ``DeepReader`` with a novelty-producing reader.
    """

    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, paper_text, paper_id="", title="", priority="high", **kwargs):
        return {
            "paper_id": paper_id,
            "method": {"key_components": ["base"]},
            "research_problem": {},
        }


class FakeCritic:
    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, knowledge_obj, **kwargs):
        return {
            "paper_id": knowledge_obj.get("paper_id"),
            "limitations": [],
            "verification_score": 1.0,
        }


class FakeGapDetector:
    """Always reports a single candidate gap."""

    def __init__(self, llm, session_id="", embedding_fn=None, graph_store=None):
        pass

    async def run(self, *, knowledge_objects, critiques, **kwargs):
        return [{"gap_id": "g1", "description": "a candidate gap", "type": "method"}]


class FakeVerifier:
    """Verifies every gap as genuinely novel (verification ratio = 1.0).

    Loop 2 never fires with this default; tests that want a retry override
    ``VerificationAgent`` with a failing verifier.
    """

    def __init__(self, llm, session_id="", search_service=None):
        pass

    async def run(self, *, gaps, **kwargs):
        return [{**g, "status": "verified_gap"} for g in gaps]


class FakeIdeaGenerator:
    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, verified_gaps, knowledge_objects, user_background="", **kwargs):
        return [
            {"title": f"Idea for {g.get('gap_id', '?')}", "feasibility": 0.9}
            for g in verified_gaps
        ]


class FakeExperimentPlanner:
    """Plans a feasible experiment (feasibility 0.9 ≥ 0.4 → Loop 3 never fires)."""

    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, idea, knowledge_objects, **kwargs):
        return {
            "idea": idea.get("title"),
            "feasibility_score": 0.9,
            "experiment_plan": {"steps": ["step 1"], "risks": []},
        }


class FakeReportWriter:
    def __init__(self, llm, session_id=""):
        pass

    async def run(self, *, question, **kwargs):
        return {"title": f"Report: {question}", "sections": []}


# class name -> (module path, default fake). The node code does
# ``from <module path> import <class name>``.
_AGENT_REGISTRY: dict[str, tuple[str, type]] = {
    "QueryPlanner": ("science_ai.agents.query_planner", FakePlanner),
    "PaperTriage": ("science_ai.agents.paper_triage", FakeTriage),
    "DeepReader": ("science_ai.agents.deep_reader", StaticReader),
    "CritiqueAgent": ("science_ai.agents.critique", FakeCritic),
    "GapDetector": ("science_ai.agents.gap_detector", FakeGapDetector),
    "VerificationAgent": ("science_ai.agents.verification", FakeVerifier),
    "IdeaGenerator": ("science_ai.agents.idea_generator", FakeIdeaGenerator),
    "ExperimentPlanner": ("science_ai.agents.experiment_planner", FakeExperimentPlanner),
    "ReportWriter": ("science_ai.agents.report_writer", FakeReportWriter),
}


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def install_agents(monkeypatch):
    """Return an installer that injects fake agent modules into ``sys.modules``.

    Call it once per test, overriding individual agents by class name:

        install_agents()                          # all defaults
        install_agents(DeepReader=NovelReader)    # override one
    """

    def _install(**overrides):
        unknown = set(overrides) - set(_AGENT_REGISTRY)
        if unknown:
            raise TypeError(f"Unknown agent override(s): {sorted(unknown)}")
        for cls_name, (module_path, default_cls) in _AGENT_REGISTRY.items():
            cls = overrides.get(cls_name, default_cls)
            module = types.ModuleType(module_path)
            setattr(module, cls_name, cls)
            monkeypatch.setitem(sys.modules, module_path, module)

    return _install


@pytest.fixture
def fake_search():
    """A fresh FakeSearch per test (two new papers per call)."""
    return FakeSearch()


@pytest.fixture
def make_search():
    """Factory for FakeSearch with a custom papers-per-call count."""
    def _make(papers_per_call: int = 2) -> FakeSearch:
        return FakeSearch(papers_per_call=papers_per_call)
    return _make


@pytest.fixture
def graph_runner(fake_search):
    """A GraphRunner wired to the fake search and the CLI backend (MemorySaver)."""
    from science_ai.orchestrator.graph.runner import GraphRunner

    return GraphRunner(search_service=fake_search, llm_backend="cli")
