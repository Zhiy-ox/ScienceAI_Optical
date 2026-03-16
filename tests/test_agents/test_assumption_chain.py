"""Tests for Gap Detection Mechanism B: Assumption Chain Analysis."""

from science_ai.agents.gap_detection.assumption_chain import AssumptionChainAnalyzer


def _make_ko(paper_id, assumptions=None, datasets=None):
    ko = {
        "paper_id": paper_id,
        "assumptions": assumptions or [],
        "experiments": {"datasets": datasets or []},
    }
    return ko


def test_unverified_foundation_detected():
    analyzer = AssumptionChainAnalyzer()
    kos = [
        _make_ko("p1", [{"assumption": "Data is IID distributed", "type": "implicit"}]),
        _make_ko("p2", [{"assumption": "Data is IID distributed", "type": "explicit"}]),
        _make_ko("p3", [{"assumption": "Data is IID distributed", "type": "implicit"}]),
    ]
    gaps = analyzer._find_unverified_foundations(kos)
    assert len(gaps) == 1
    assert gaps[0]["assumption_type"] == "unverified_foundation"
    assert len(gaps[0]["evidence"]) == 3


def test_no_unverified_with_few_papers():
    analyzer = AssumptionChainAnalyzer()
    kos = [
        _make_ko("p1", [{"assumption": "Rare assumption", "type": "explicit"}]),
        _make_ko("p2", [{"assumption": "Rare assumption", "type": "explicit"}]),
    ]
    gaps = analyzer._find_unverified_foundations(kos)
    assert len(gaps) == 0  # need ≥3


def test_assumption_conflict_detected():
    analyzer = AssumptionChainAnalyzer()
    kos = [
        _make_ko("p1", [{"assumption": "The model requires large training data", "type": "explicit"}]),
        _make_ko("p2", [{"assumption": "The model does not require large training data", "type": "explicit"}]),
    ]
    gaps = analyzer._find_assumption_conflicts(kos)
    assert len(gaps) == 1
    assert gaps[0]["assumption_type"] == "assumption_conflict"


def test_assumption_reality_gap_detected():
    analyzer = AssumptionChainAnalyzer()
    kos = [
        _make_ko(
            "p1",
            assumptions=[{"assumption": "Method is applicable to all scientific domains", "type": "explicit"}],
            datasets=["PubMed"],  # Only 1 dataset
        ),
    ]
    gaps = analyzer._find_assumption_reality_gaps(kos)
    assert len(gaps) == 1
    assert gaps[0]["assumption_type"] == "assumption_reality_gap"


def test_full_detection():
    analyzer = AssumptionChainAnalyzer()
    kos = [
        _make_ko("p1", [
            {"assumption": "Labels are accurate", "type": "implicit"},
            {"assumption": "Method generalizes to any domain", "type": "explicit"},
        ], datasets=["MNIST"]),
        _make_ko("p2", [
            {"assumption": "Labels are accurate", "type": "implicit"},
        ]),
        _make_ko("p3", [
            {"assumption": "Labels are accurate", "type": "explicit"},
        ]),
    ]
    gaps = analyzer.detect(kos)
    # Should find: unverified foundation ("labels are accurate") + assumption-reality gap
    assert len(gaps) >= 1
    types = {g["assumption_type"] for g in gaps}
    assert "unverified_foundation" in types
