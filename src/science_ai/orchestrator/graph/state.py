"""Typed state schema for the research pipeline graph."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ResearchState(TypedDict, total=False):
    # --- inputs (set at kickoff, read-only thereafter) ---
    session_id: str
    question: str
    max_papers: int
    phase: int  # 1 | 2 | 3
    user_background: str
    source: str  # web | zotero | both
    hitl_gates: list[str]  # opt-in approval gates, e.g. ["plan", "gaps"]; [] = autonomous

    # --- stage outputs ---
    plan: dict[str, Any]
    all_papers: Annotated[list[dict], operator.add]
    triage_results: Annotated[list[dict], operator.add]
    papers_to_read: list[dict]
    knowledge_objects: Annotated[list[dict], operator.add]
    critiques: Annotated[list[dict], operator.add]
    gaps: list[dict]
    verification_results: list[dict]
    verified_gaps: list[dict]
    ideas: list[dict]
    experiment_plans: list[dict]
    report: dict[str, Any] | None
    zotero_collection_key: str | None

    # --- loop counters ---
    search_refine_count: int
    gap_retry_count: int
    idea_regen_count: int

    # --- loop control (transient, set by decision nodes, read by routers) ---
    refine_keywords: list[str]       # new keywords to search in a refinement pass
    previous_failures: list[dict]    # failed verifications fed back to gap_detect
    regen_constraint: str            # feasibility constraint fed back to idea
    gap_retry_pending: bool
    idea_regen_pending: bool

    # --- meta ---
    status: str
    papers_found: int
    cost_summary: dict[str, Any]
    node_metrics: Annotated[list[dict], operator.add]  # per-node timing trace
