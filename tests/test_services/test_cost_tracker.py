"""Tests for the cost tracker."""

from science_ai.cost.tracker import CostTracker


def test_record_call_computes_cost():
    tracker = CostTracker()
    cost = tracker.record_call(
        session_id="s1",
        agent="deep_reader",
        model="claude-opus-4-6",
        reasoning_effort="high",
        input_tokens=50_000,
        output_tokens=3_000,
        cached_tokens=10_000,
    )
    # (40000/1M * 5.0) + (10000/1M * 0.50) + (3000/1M * 25.0)
    # = 0.2 + 0.005 + 0.075 = 0.28
    assert abs(cost - 0.28) < 0.001


def test_session_total():
    tracker = CostTracker()
    tracker.record_call("s1", "agent1", "claude-sonnet-4-6", "medium", 10_000, 1_000)
    tracker.record_call("s1", "agent2", "claude-sonnet-4-6", "medium", 10_000, 1_000)
    tracker.record_call("s2", "agent1", "claude-sonnet-4-6", "medium", 10_000, 1_000)

    total_s1 = tracker.session_total("s1")
    total_s2 = tracker.session_total("s2")

    assert total_s1 > 0
    assert total_s2 > 0
    assert total_s1 == total_s2 * 2  # s1 has 2 calls, s2 has 1


def test_session_summary():
    tracker = CostTracker()
    tracker.record_call("s1", "reader", "claude-opus-4-6", "high", 50_000, 3_000)
    tracker.record_call("s1", "triage", "gemini/gemini-3.1-pro", "low", 30_000, 1_000)

    summary = tracker.session_summary("s1")
    assert summary["session_id"] == "s1"
    assert summary["call_count"] == 2
    assert summary["total_usd"] > 0
    assert "claude-opus-4-6" in summary["by_model"]
    assert "gemini/gemini-3.1-pro" in summary["by_model"]


def test_unknown_model_returns_zero_cost():
    tracker = CostTracker()
    cost = tracker.record_call("s1", "agent", "unknown-model", "", 10_000, 1_000)
    assert cost == 0.0
