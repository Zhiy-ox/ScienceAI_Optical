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
        "deep_read", "refine_decision", "critique", "index",
        "gap_detect", "verify", "gap_retry_decision",
        "idea", "experiment", "idea_regen_decision",
        "report", "zotero_export",
    }
    assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


def test_graph_has_feedback_loop_edges():
    """The three feedback loops must create back-edges in the compiled graph."""
    graph = build_graph()
    edges = graph.get_graph().edges
    pairs = {(e.source, e.target) for e in edges}
    # Loop 1: refine_decision → search
    assert ("refine_decision", "search") in pairs
    # Loop 2: gap_retry_decision → gap_detect
    assert ("gap_retry_decision", "gap_detect") in pairs
    # Loop 3: idea_regen_decision → idea
    assert ("idea_regen_decision", "idea") in pairs
