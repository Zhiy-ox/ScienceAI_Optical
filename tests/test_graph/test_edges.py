"""Tests for conditional edge routing functions (phase exits + feedback loops)."""

from science_ai.orchestrator.graph.edges import (
    after_gap_retry_decision,
    after_idea_regen_decision,
    after_refine_decision,
)


# --- Loop 1 + Phase-1 exit ---------------------------------------------------

def test_refine_loops_when_keywords_present():
    assert after_refine_decision({"refine_keywords": ["opa"], "phase": 3}) == "refine"


def test_refine_keywords_take_priority_over_phase_exit():
    # Even in phase 1, a pending refinement loops first.
    assert after_refine_decision({"refine_keywords": ["opa"], "phase": 1}) == "refine"


def test_refine_phase1_exits_when_no_keywords():
    assert after_refine_decision({"refine_keywords": [], "phase": 1}) == "exit_phase1"


def test_refine_phase2_continues_to_critique():
    assert after_refine_decision({"refine_keywords": [], "phase": 2}) == "continue_to_critique"


def test_refine_phase3_continues_to_critique():
    assert after_refine_decision({"phase": 3}) == "continue_to_critique"


# --- Loop 2 + Phase-2 exit ---------------------------------------------------

def test_gap_retry_loops_when_pending():
    assert after_gap_retry_decision({"gap_retry_pending": True, "phase": 3}) == "retry"


def test_gap_retry_phase2_exits():
    assert after_gap_retry_decision({"gap_retry_pending": False, "phase": 2}) == "exit_phase2"


def test_gap_retry_phase3_continues_to_idea():
    assert after_gap_retry_decision({"gap_retry_pending": False, "phase": 3}) == "continue_to_idea"


def test_gap_retry_pending_takes_priority_over_phase2_exit():
    assert after_gap_retry_decision({"gap_retry_pending": True, "phase": 2}) == "retry"


# --- Loop 3 ------------------------------------------------------------------

def test_idea_regen_loops_when_pending():
    assert after_idea_regen_decision({"idea_regen_pending": True}) == "regen"


def test_idea_regen_continues_to_report():
    assert after_idea_regen_decision({"idea_regen_pending": False}) == "continue_to_report"


def test_idea_regen_default_continues():
    assert after_idea_regen_decision({}) == "continue_to_report"
