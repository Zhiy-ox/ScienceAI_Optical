"""Tests for graph construction."""

from science_ai.orchestrator.graph.builder import build_graph


def test_graph_compiles():
    graph = build_graph()
    assert graph is not None


def test_graph_has_expected_nodes():
    graph = build_graph()
    node_names = set(graph.get_graph().nodes.keys())
    expected = {
        "__start__", "__end__",
        "plan", "search", "triage", "select_papers",
        "deep_read", "critique", "index",
        "gap_detect", "verify",
        "idea", "experiment", "report", "zotero_export",
    }
    assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"
