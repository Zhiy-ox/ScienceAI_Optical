"""Tests for the model router."""

import pytest

from science_ai.orchestrator.model_router import ModelRouter


def test_routes_known_task():
    router = ModelRouter()
    model, effort = router.route("query_planning")
    assert model == "gpt-5.4"
    assert effort == "medium"


def test_routes_paper_triage():
    router = ModelRouter()
    model, effort = router.route("paper_triage")
    assert model == "gemini/gemini-3.1-pro"
    assert effort == "low"


def test_routes_deep_read_high():
    router = ModelRouter()
    model, effort = router.route("deep_read_high")
    assert model == "claude-opus-4-6"
    assert effort == "high"


def test_unknown_task_raises():
    router = ModelRouter()
    with pytest.raises(ValueError, match="Unknown task type"):
        router.route("nonexistent_task")


def test_overrides():
    router = ModelRouter(overrides={
        "paper_triage": {"model": "claude-sonnet-4-6", "reasoning_effort": "medium"}
    })
    model, effort = router.route("paper_triage")
    assert model == "claude-sonnet-4-6"


def test_estimate_cost():
    router = ModelRouter()
    cost = router.estimate_cost("paper_triage", input_tokens=30_000, output_tokens=2_000)
    # Gemini: (30000/1M * 2.0) + (2000/1M * 12.0) = 0.06 + 0.024 = 0.084
    assert abs(cost - 0.084) < 0.001
