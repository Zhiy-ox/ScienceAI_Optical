"""Tests for Gap Detection Mechanism D: Evaluation Blind Spots."""

from science_ai.agents.gap_detection.evaluation_blindspots import EvaluationBlindspotDetector


def _make_ko(paper_id, datasets=None, metrics=None, baselines=None):
    """Helper to create a minimal knowledge object with experiment info."""
    return {
        "paper_id": paper_id,
        "experiments": {
            "datasets": datasets or [],
            "metrics": metrics or [],
            "baselines": baselines or [],
        },
    }


def test_dataset_bias_detected():
    detector = EvaluationBlindspotDetector()
    kos = [
        _make_ko("p1", datasets=["ImageNet", "CIFAR-10"]),
        _make_ko("p2", datasets=["ImageNet"]),
        _make_ko("p3", datasets=["ImageNet"]),
        _make_ko("p4", datasets=["ImageNet", "COCO"]),
    ]
    gaps = detector._check_dataset_bias(kos)

    assert len(gaps) >= 1
    assert any(g["blindspot_type"] == "dataset_bias" for g in gaps)
    ds_gap = next(g for g in gaps if g["blindspot_type"] == "dataset_bias")
    assert "imagenet" in ds_gap["evidence"]["dominant_dataset"]


def test_no_dataset_bias_with_diverse_datasets():
    detector = EvaluationBlindspotDetector()
    kos = [
        _make_ko("p1", datasets=["ImageNet"]),
        _make_ko("p2", datasets=["COCO"]),
        _make_ko("p3", datasets=["Pascal VOC"]),
        _make_ko("p4", datasets=["ADE20K"]),
    ]
    gaps = detector._check_dataset_bias(kos)
    assert len(gaps) == 0


def test_missing_human_evaluation():
    detector = EvaluationBlindspotDetector()
    kos = [
        _make_ko("p1", metrics=["BLEU", "ROUGE"]),
        _make_ko("p2", metrics=["BLEU", "F1"]),
        _make_ko("p3", metrics=["ROUGE", "F1"]),
    ]
    gaps = detector._check_metric_gaps(kos)

    assert any(g["blindspot_type"] == "missing_human_evaluation" for g in gaps)


def test_human_evaluation_present():
    detector = EvaluationBlindspotDetector()
    kos = [
        _make_ko("p1", metrics=["BLEU", "human evaluation"]),
        _make_ko("p2", metrics=["BLEU", "F1"]),
        _make_ko("p3", metrics=["ROUGE"]),
    ]
    gaps = detector._check_metric_gaps(kos)

    assert not any(g.get("blindspot_type") == "missing_human_evaluation" for g in gaps)


def test_baseline_staleness():
    detector = EvaluationBlindspotDetector()
    kos = [
        _make_ko("p1", baselines=["BERT", "GPT-2"]),
        _make_ko("p2", baselines=["BERT", "RoBERTa"]),
        _make_ko("p3", baselines=["BERT", "XLNet"]),
    ]
    gaps = detector._check_baseline_staleness(kos, current_year=2026)

    assert len(gaps) >= 1
    assert any(g["blindspot_type"] == "baseline_staleness" for g in gaps)


def test_full_detection_pipeline():
    detector = EvaluationBlindspotDetector()
    kos = [
        _make_ko("p1", datasets=["SQuAD"], metrics=["F1", "EM"], baselines=["BERT"]),
        _make_ko("p2", datasets=["SQuAD"], metrics=["F1"], baselines=["BERT"]),
        _make_ko("p3", datasets=["SQuAD"], metrics=["F1", "EM"], baselines=["BERT", "GPT-2"]),
        _make_ko("p4", datasets=["SQuAD", "NQ"], metrics=["F1"], baselines=["BERT"]),
    ]
    gaps = detector.detect(kos)

    # Should find at least: dataset bias (SQuAD), missing human eval, baseline staleness (BERT)
    types = {g["blindspot_type"] for g in gaps}
    assert "dataset_bias" in types
    assert "missing_human_evaluation" in types
    assert "baseline_staleness" in types
