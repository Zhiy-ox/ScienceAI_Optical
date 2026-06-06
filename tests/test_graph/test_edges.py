"""Tests for conditional edge routing functions."""

from science_ai.orchestrator.graph.edges import after_deep_read, after_verify


def test_after_deep_read_phase1_exits():
    state = {"phase": 1}
    assert after_deep_read(state) == "exit_phase1"


def test_after_deep_read_phase2_continues():
    state = {"phase": 2}
    assert after_deep_read(state) == "continue_to_critique"


def test_after_deep_read_phase3_continues():
    state = {"phase": 3}
    assert after_deep_read(state) == "continue_to_critique"


def test_after_verify_phase2_exits():
    state = {"phase": 2}
    assert after_verify(state) == "exit_phase2"


def test_after_verify_phase3_continues():
    state = {"phase": 3}
    assert after_verify(state) == "continue_to_idea"


def test_after_verify_phase1_exits():
    state = {"phase": 1}
    assert after_verify(state) == "exit_phase2"


def test_after_deep_read_default_phase_continues():
    state = {}
    assert after_deep_read(state) == "continue_to_critique"
