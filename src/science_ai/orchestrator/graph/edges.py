"""Conditional edge functions for phase-exit routing.

Stage 1 uses only phase-exit edges (linear graph, no feedback loops).
Feedback-loop edges will be added in Stage 2.
"""

from __future__ import annotations

from science_ai.orchestrator.graph.state import ResearchState

END = "__end__"


def after_deep_read(state: ResearchState) -> str:
    """Exit after deep_read if phase == 1, otherwise continue to critique."""
    if state.get("phase", 3) <= 1:
        return "exit_phase1"
    return "continue_to_critique"


def after_verify(state: ResearchState) -> str:
    """Exit after verify if phase == 2, otherwise continue to idea generation."""
    if state.get("phase", 3) <= 2:
        return "exit_phase2"
    return "continue_to_idea"
