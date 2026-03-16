"""Tests for the feedback controller."""

from science_ai.orchestrator.feedback import FeedbackController


def test_search_refinement_triggers_on_new_keywords():
    fc = FeedbackController()
    original = ["liquid crystal", "optical phased array"]
    # More than 30% new
    discovered = ["liquid crystal", "OPA", "beam steering", "metasurface", "ferroelectric"]

    assert fc.should_refine_search("s1", original, discovered) is True


def test_search_refinement_does_not_trigger_on_familiar_keywords():
    fc = FeedbackController()
    original = ["liquid crystal", "optical phased array", "beam steering"]
    discovered = ["liquid crystal", "optical phased array"]

    assert fc.should_refine_search("s1", original, discovered) is False


def test_search_refinement_respects_max_iterations():
    fc = FeedbackController(max_iterations=2)
    original = ["a"]
    new = ["b", "c", "d"]

    assert fc.should_refine_search("s1", original, new) is True
    assert fc.should_refine_search("s1", original, new) is True
    assert fc.should_refine_search("s1", original, new) is False  # max hit


def test_gap_verification_triggers_on_low_verified_ratio():
    fc = FeedbackController()
    results = [
        {"status": "active_area"},
        {"status": "active_area"},
        {"status": "verified_gap"},
        {"status": "emerging"},
        {"status": "active_area"},
    ]
    # 1/5 = 20% verified < 30% threshold
    assert fc.should_retry_gap_detection("s1", results) is True


def test_idea_feasibility_triggers_on_low_score():
    fc = FeedbackController()
    assert fc.should_regenerate_idea("s1", 0.3) is True
    assert fc.should_regenerate_idea("s2", 0.5) is False
