"""Tests for the legacy-vs-graph parity comparison logic."""

from science_ai.orchestrator.parity import compare_results


def _result(papers=10, kos=8, gaps=4, verified=3, ideas=3, plans=3, report=True):
    return {
        "papers_found": papers,
        "knowledge_objects": [{}] * kos,
        "gaps": [{}] * gaps,
        "verified_gaps": [{}] * verified,
        "ideas": [{}] * ideas,
        "experiment_plans": [{}] * plans,
        "report": {"title": "x"} if report else None,
    }


def test_identical_results_match():
    report = compare_results(_result(), _result())
    assert report.overall_match
    assert all(c.match for c in report.comparisons)


def test_different_counts_fail_without_tolerance():
    report = compare_results(_result(gaps=4), _result(gaps=6))
    assert not report.overall_match
    gap_cmp = next(c for c in report.comparisons if c.field == "gaps")
    assert not gap_cmp.match
    assert gap_cmp.delta == 2


def test_within_tolerance_matches():
    report = compare_results(_result(gaps=4), _result(gaps=6), tolerance=2)
    assert report.overall_match


def test_tolerance_does_not_apply_to_report_presence():
    # report differs (present vs absent) — never tolerated
    report = compare_results(_result(report=True), _result(report=False), tolerance=10)
    assert not report.overall_match
    rep_cmp = next(c for c in report.comparisons if c.field == "report")
    assert not rep_cmp.match


def test_metrics_fall_back_to_all_papers_length():
    legacy = {"_all_papers": [{}] * 7}
    graph = {"papers_found": 7}
    report = compare_results(legacy, graph)
    papers_cmp = next(c for c in report.comparisons if c.field == "papers_found")
    assert papers_cmp.legacy == 7
    assert papers_cmp.graph == 7
    assert papers_cmp.match


def test_summary_renders_pass_and_fail():
    assert "PASS" in compare_results(_result(), _result()).summary()
    assert "FAIL" in compare_results(_result(gaps=1), _result(gaps=9)).summary()


def test_empty_results_match():
    report = compare_results({}, {})
    assert report.overall_match
