"""Build and compile the LangGraph research pipeline."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from science_ai.orchestrator.graph.edges import after_deep_read, after_verify
from science_ai.orchestrator.graph.nodes import (
    critique_node,
    deep_read_node,
    experiment_node,
    gap_detect_node,
    idea_node,
    index_node,
    plan_node,
    report_node,
    search_node,
    select_papers_node,
    triage_node,
    verify_node,
    zotero_export_node,
)
from science_ai.orchestrator.graph.state import ResearchState


def build_graph(*, checkpointer=None):
    """Construct and compile the research pipeline graph.

    Stage 1: linear topology with phase-exit conditional edges.
    """
    g = StateGraph(ResearchState)

    # --- Add nodes ---
    g.add_node("plan", plan_node)
    g.add_node("search", search_node)
    g.add_node("triage", triage_node)
    g.add_node("select_papers", select_papers_node)
    g.add_node("deep_read", deep_read_node)
    g.add_node("critique", critique_node)
    g.add_node("index", index_node)
    g.add_node("gap_detect", gap_detect_node)
    g.add_node("verify", verify_node)
    g.add_node("idea", idea_node)
    g.add_node("experiment", experiment_node)
    g.add_node("report", report_node)
    g.add_node("zotero_export", zotero_export_node)

    # --- Linear edges ---
    g.set_entry_point("plan")
    g.add_edge("plan", "search")
    g.add_edge("search", "triage")
    g.add_edge("triage", "select_papers")
    g.add_edge("select_papers", "deep_read")

    # Phase-exit after deep_read: phase 1 exits, phase 2+ continues
    g.add_conditional_edges(
        "deep_read",
        after_deep_read,
        {
            "exit_phase1": END,
            "continue_to_critique": "critique",
        },
    )

    g.add_edge("critique", "index")
    g.add_edge("index", "gap_detect")
    g.add_edge("gap_detect", "verify")

    # Phase-exit after verify: phase 2 exits, phase 3 continues
    g.add_conditional_edges(
        "verify",
        after_verify,
        {
            "exit_phase2": END,
            "continue_to_idea": "idea",
        },
    )

    g.add_edge("idea", "experiment")
    g.add_edge("experiment", "report")
    g.add_edge("report", "zotero_export")
    g.add_edge("zotero_export", END)

    return g.compile(checkpointer=checkpointer)
