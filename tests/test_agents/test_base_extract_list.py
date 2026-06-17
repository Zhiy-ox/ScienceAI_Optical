"""BaseAgent.extract_list: tolerate the JSON envelope shapes LLMs actually emit.

Regression for a silent data-loss bug: agents called ``parsed.get("ideas", [])``
directly, but the CLI client wraps a bare top-level array as ``{"results": [...]}``.
That returned ``[]`` and dropped an entire stage's output (e.g. all Phase-3 ideas).
"""

from science_ai.agents.base import BaseAgent


def test_requested_key_wins():
    parsed = {"ideas": [{"title": "a"}, {"title": "b"}]}
    assert BaseAgent.extract_list(parsed, "ideas") == parsed["ideas"]


def test_cli_results_envelope():
    # CLI client wraps bare arrays under "results".
    parsed = {"results": [{"gap_id": "GAP-001"}]}
    assert BaseAgent.extract_list(parsed, "gaps") == parsed["results"]


def test_bare_list():
    parsed = [{"title": "a"}]
    assert BaseAgent.extract_list(parsed, "ideas") == parsed


def test_single_list_value_fallback():
    parsed = {"unexpected_key": [{"x": 1}]}
    assert BaseAgent.extract_list(parsed, "ideas") == [{"x": 1}]


def test_no_list_returns_empty():
    assert BaseAgent.extract_list({"note": "nothing here"}, "ideas") == []
    assert BaseAgent.extract_list("not even json", "ideas") == []


def test_requested_key_preferred_over_results():
    parsed = {"ideas": [{"title": "real"}], "results": [{"title": "noise"}]}
    assert BaseAgent.extract_list(parsed, "ideas") == [{"title": "real"}]
