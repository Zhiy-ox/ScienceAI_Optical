"""Per-node timing observability.

Every node is wrapped so each execution appends a record to the checkpointed
``node_metrics`` list; the ``/research/{id}/trace`` endpoint rolls those up.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import science_ai.api.routes as routes
from science_ai.orchestrator.graph.runner import GraphRunner


@pytest.mark.asyncio
async def test_node_metrics_recorded_for_each_node(install_agents, fake_search):
    install_agents()
    runner = GraphRunner(search_service=fake_search, llm_backend="cli")
    result = await runner.run("q", session_id="obs-1", phase=1, max_papers=5)

    metrics = result.get("node_metrics", [])
    assert metrics, "expected per-node timing records"

    # Every record is well-formed.
    for m in metrics:
        assert set(m) >= {"node", "duration_s"}
        assert isinstance(m["duration_s"], float)
        assert m["duration_s"] >= 0.0

    # The Phase-1 backbone nodes all show up in the trace.
    nodes_seen = {m["node"] for m in metrics}
    assert {"plan", "plan_gate", "search", "triage", "select_papers"} <= nodes_seen


@pytest.mark.asyncio
async def test_fanout_nodes_each_emit_a_metric(install_agents, make_search):
    """A parallel fan-out (3 papers) yields three deep_read_one records."""
    install_agents()
    runner = GraphRunner(search_service=make_search(papers_per_call=3), llm_backend="cli")
    result = await runner.run("q", session_id="obs-fanout", phase=1, max_papers=3)

    deep_reads = [m for m in result["node_metrics"] if m["node"] == "deep_read_one"]
    assert len(deep_reads) == 3


@pytest.mark.asyncio
async def test_trace_endpoint_aggregates_by_node():
    state = {
        "status": "completed",
        "node_metrics": [
            {"node": "plan", "duration_s": 0.5, "status": "planned"},
            {"node": "deep_read_one", "duration_s": 0.2, "status": None},
            {"node": "deep_read_one", "duration_s": 0.3, "status": None},
        ],
    }
    fake_runner = SimpleNamespace(get_state=AsyncMock(return_value=state))

    with patch.object(routes, "_get_graph_runner", AsyncMock(return_value=fake_runner)):
        out = await routes.get_session_trace("sid")

    assert out["node_count"] == 3
    assert out["total_duration_s"] == pytest.approx(1.0)
    by_node = {a["node"]: a for a in out["by_node"]}
    assert by_node["deep_read_one"]["calls"] == 2
    assert by_node["deep_read_one"]["total_s"] == pytest.approx(0.5)
    # Sorted by total_s descending — deep_read_one (0.5) before plan (0.5 tie) ok,
    # but the highest must lead.
    assert out["by_node"][0]["total_s"] >= out["by_node"][-1]["total_s"]


@pytest.mark.asyncio
async def test_trace_endpoint_404_when_no_state():
    from fastapi import HTTPException

    fake_runner = SimpleNamespace(get_state=AsyncMock(return_value=None))
    with patch.object(routes, "_get_graph_runner", AsyncMock(return_value=fake_runner)):
        with pytest.raises(HTTPException) as exc:
            await routes.get_session_trace("missing")
    assert exc.value.status_code == 404
