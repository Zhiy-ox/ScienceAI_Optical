"""Build and compile the LangGraph research pipeline."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from science_ai.orchestrator.graph.edges import (
    after_gap_retry_decision,
    after_gaps_gate,
    after_idea_regen_decision,
    after_plan_gate,
    after_refine_decision,
)
from science_ai.orchestrator.graph.nodes import (
    critique_dispatch,
    critique_one,
    deep_read_dispatch,
    deep_read_one,
    experiment_node,
    gap_detect_node,
    gap_retry_decision_node,
    gaps_gate_node,
    idea_node,
    idea_regen_decision_node,
    index_node,
    plan_gate_node,
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

    Stages 1-4: linear topology with phase-exit conditional edges,
    three bounded feedback loops, and parallel fan-out for deep-read
    and critique via the Send API.
    """
    g = StateGraph(ResearchState)

    # --- Nodes ---
    g.add_node("plan", plan_node)
    g.add_node("plan_gate", plan_gate_node)
    g.add_node("gaps_gate", gaps_gate_node)
    g.add_node("search", search_node)
    g.add_node("triage", triage_node)
    g.add_node("select_papers", select_papers_node)
    # Fan-out nodes for deep read
    g.add_node("deep_read_one", deep_read_one)
    # Feedback decision + fan-out for critique
    g.add_node("refine_decision", refine_decision_node)
    g.add_node("critique_one", critique_one)
    g.add_node("index", index_node)
    g.add_node("gap_detect", gap_detect_node)
    g.add_node("verify", verify_node)
    g.add_node("gap_retry_decision", gap_retry_decision_node)
    g.add_node("idea", idea_node)
    g.add_node("experiment", experiment_node)
    g.add_node("idea_regen_decision", idea_regen_decision_node)
    g.add_node("report", report_node)
    g.add_node("zotero_export", zotero_export_node)

    # --- Edges ---
    g.set_entry_point("plan")

    # HITL gate: plan → plan_gate → (search | END if rejected)
    g.add_edge("plan", "plan_gate")
    g.add_conditional_edges(
        "plan_gate",
        after_plan_gate,
        {"approved": "search", "rejected": END},
    )

    g.add_edge("search", "triage")
    g.add_edge("triage", "select_papers")

    # Fan-out: select_papers → deep_read_one (parallel via Send)
    # Empty-list fallback sends to refine_decision directly.
    g.add_conditional_edges(
        "select_papers", deep_read_dispatch,
        ["deep_read_one", "refine_decision"],
    )

    # Fan-in: all deep_read_one results merge via reducer → refine_decision
    g.add_edge("deep_read_one", "refine_decision")

    # Loop 1 (search refinement) + Phase-1 exit
    g.add_conditional_edges(
        "refine_decision",
        after_refine_decision,
        {
            "refine": "search",
            "exit_phase1": END,
            "continue_to_critique": "index",
        },
    )

    # Fan-out: index → critique_one (parallel via Send)
    # Empty-list fallback sends to gap_detect directly.
    g.add_conditional_edges(
        "index", critique_dispatch,
        ["critique_one", "gap_detect"],
    )

    # Fan-in: all critique_one results merge → gap_detect
    g.add_edge("critique_one", "gap_detect")

    g.add_edge("gap_detect", "verify")
    g.add_edge("verify", "gap_retry_decision")

    # Loop 2 (gap re-detection) + Phase-2 exit.
    # Phase-3 path routes through the gaps HITL gate before ideation.
    g.add_conditional_edges(
        "gap_retry_decision",
        after_gap_retry_decision,
        {
            "retry": "gap_detect",
            "exit_phase2": END,
            "continue_to_idea": "gaps_gate",
        },
    )

    # HITL gate: gaps_gate → (idea | END if rejected)
    g.add_conditional_edges(
        "gaps_gate",
        after_gaps_gate,
        {"approved": "idea", "rejected": END},
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
