"""Verify the parallel fan-out respects its concurrency cap.

The deep-read and critique stages fan out one agent call per paper/KO via the
LangGraph ``Send`` API, gated by a shared ``asyncio.Semaphore`` in Deps. This
test instruments the deep reader to record how many calls run simultaneously
and asserts the cap is both reached (real parallelism) and never exceeded.
"""

import asyncio

import pytest

from science_ai.orchestrator.graph.runner import GraphRunner


@pytest.mark.asyncio
async def test_deep_read_fanout_respects_concurrency_cap(install_agents, make_search):
    cap = 3
    n_papers = 9

    tracker = {"current": 0, "max": 0, "count": 0}
    lock = asyncio.Lock()

    class ConcurrencyTrackingReader:
        def __init__(self, llm, session_id=""):
            pass

        async def run(self, *, paper_text, paper_id="", title="", priority="high", **kwargs):
            async with lock:
                tracker["current"] += 1
                tracker["count"] += 1
                tracker["max"] = max(tracker["max"], tracker["current"])
            # Hold the slot so concurrent callers pile up against the semaphore.
            await asyncio.sleep(0.05)
            async with lock:
                tracker["current"] -= 1
            return {
                "paper_id": paper_id,
                "method": {"key_components": ["base"]},
                "research_problem": {},
            }

    install_agents(DeepReader=ConcurrencyTrackingReader)

    runner = GraphRunner(
        search_service=make_search(papers_per_call=n_papers),
        llm_backend="cli",
        fanout_concurrency=cap,
    )
    await runner.run("q", session_id="fanout-cap", phase=1, max_papers=n_papers)

    # Every paper was read exactly once...
    assert tracker["count"] == n_papers
    # ...real parallelism occurred and was capped at exactly the configured limit.
    assert tracker["max"] == cap


@pytest.mark.asyncio
async def test_fanout_concurrency_defaults_to_setting(monkeypatch):
    """The runner reads the cap from settings when not given explicitly."""
    monkeypatch.setattr("science_ai.config.settings.fanout_concurrency", 7)
    runner = GraphRunner(llm_backend="cli")
    assert runner._fanout_concurrency == 7

    explicit = GraphRunner(llm_backend="cli", fanout_concurrency=2)
    assert explicit._fanout_concurrency == 2
