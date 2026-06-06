"""Conditional edge routers for phase-exit and feedback-loop routing.

Routers are *pure* functions: they only read state (including the transient
control flags set by the decision nodes in nodes.py) and return a label that
builder.py maps to the next node. All loop counters live in state and are
bounded inside the decision nodes, so these routers cannot loop forever.
"""

from __future__ import annotations

from science_ai.orchestrator.graph.state import ResearchState


def after_refine_decision(state: ResearchState) -> str:
    """Loop 1 + Phase-1 exit.

    refine_keywords set  → loop back to search
    phase <= 1           → end (Phase 1 stops after deep reading)
    otherwise            → continue to critique
    """
    if state.get("refine_keywords"):
        return "refine"
    if state.get("phase", 3) <= 1:
        return "exit_phase1"
    return "continue_to_critique"


def after_gap_retry_decision(state: ResearchState) -> str:
    """Loop 2 + Phase-2 exit.

    gap_retry_pending    → loop back to gap detection
    phase <= 2           → end (Phase 2 stops after verification)
    otherwise            → continue to idea generation
    """
    if state.get("gap_retry_pending"):
        return "retry"
    if state.get("phase", 3) <= 2:
        return "exit_phase2"
    return "continue_to_idea"


def after_idea_regen_decision(state: ResearchState) -> str:
    """Loop 3.

    idea_regen_pending   → loop back to idea generation
    otherwise            → continue to report writing
    """
    if state.get("idea_regen_pending"):
        return "regen"
    return "continue_to_report"


def after_plan_gate(state: ResearchState) -> str:
    """HITL gate: a rejected plan ends the run, otherwise continue to search."""
    if state.get("status") == "rejected":
        return "rejected"
    return "approved"


def after_gaps_gate(state: ResearchState) -> str:
    """HITL gate: rejected gaps end the run, otherwise continue to ideation."""
    if state.get("status") == "rejected":
        return "rejected"
    return "approved"
