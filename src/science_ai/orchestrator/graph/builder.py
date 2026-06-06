"""Build and compile the LangGraph research pipeline."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from science_ai.orchestrator.graph.edges import (
    after_gap_retry_decision,
    after_idea_regen_decision,
    after_refine_decision,
)
from science_ai.orchestrator.graph.nodes import (
    critique_node,
    deep_read_node,
    experiment_node,
    gap_detect_node,
    gap_retry_decision_node,
    idea_node,
    idea_regen_decision_node,
    index_node,
    plan_node,
    refine_decision_node,
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

    Stage 2: linear topology + three bounded feedback loops wired as
    conditional edges (search refinement, gap re-detection, idea regeneration).
    """
    g = StateGraph(ResearchState)

    # --- Add nodes ---
    g.add_node("plan", plan_node)
    g.add_node("search", search_node)
    g.add_node("triage", triage_node)
    g.add_node("select_papers", select_papers_node)
    g.add_node("deep_read", deep_read_node)
    g.add_node("refine_decision", refine_decision_node)
    g.add_node("critique", critique_node)
    g.add_node("index", index_node)
    g.add_node("gap_detect", gap_detect_node)
    g.add_node("verify", verify_node)
    g.add_node("gap_retry_decision", gap_retry_decision_node)
    g.add_node("idea", idea_node)
    g.add_node("experiment", experiment_node)
    g.add_node("idea_regen_decision", idea_regen_decision_node)
    g.add_node("report", report_node)
    g.add_node("zotero_export", zotero_export_node)

    # --- Plan → Search → Triage → Select → Deep read ---
    g.set_entry_point("plan")
    g.add_edge("plan", "search")
    g.add_edge("search", "triage")
    g.add_edge("triage", "select_papers")
    g.add_edge("select_papers", "deep_read")
    g.add_edge("deep_read", "refine_decision")

    # Loop 1 (search refinement) + Phase-1 exit
    g.add_conditional_edges(
        "refine_decision",
        after_refine_decision,
        {
            "refine": "search",
            "exit_phase1": END,
            "continue_to_critique": "critique",
        },
    )

    # --- Critique → Index → Gap detect → Verify ---
    g.add_edge("critique", "index")
    g.add_edge("index", "gap_detect")
    g.add_edge("gap_detect", "verify")
    g.add_edge("verify", "gap_retry_decision")

    # Loop 2 (gap re-detection) + Phase-2 exit
    g.add_conditional_edges(
        "gap_retry_decision",
        after_gap_retry_decision,
        {
            "retry": "gap_detect",
            "exit_phase2": END,
            "continue_to_idea": "idea",
        },
    )

    # --- Idea → Experiment ---
    g.add_edge("idea", "experiment")
    g.add_edge("experiment", "idea_regen_decision")

    # Loop 3 (idea regeneration)
    g.add_conditional_edges(
        "idea_regen_decision",
        after_idea_regen_decision,
        {
            "regen": "idea",
            "continue_to_report": "report",
        },
    )

    # --- Report → Zotero export → END ---
    g.add_edge("report", "zotero_export")
    g.add_edge("zotero_export", END)

    return g.compile(checkpointer=checkpointer)
