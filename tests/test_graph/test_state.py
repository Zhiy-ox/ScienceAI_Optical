"""Tests for the ResearchState schema."""

from science_ai.orchestrator.graph.state import ResearchState


def test_state_can_be_constructed():
    state: ResearchState = {
        "session_id": "test-123",
        "question": "What is OPA?",
        "phase": 1,
        "max_papers": 10,
        "source": "web",
        "user_background": "",
        "all_papers": [],
        "triage_results": [],
        "knowledge_objects": [],
        "critiques": [],
        "status": "starting",
        "papers_found": 0,
        "search_refine_count": 0,
        "gap_retry_count": 0,
        "idea_regen_count": 0,
    }
    assert state["session_id"] == "test-123"
    assert state["phase"] == 1


def test_state_total_false_allows_partial():
    state: ResearchState = {
        "session_id": "s1",
        "question": "test",
    }
    assert state["session_id"] == "s1"
