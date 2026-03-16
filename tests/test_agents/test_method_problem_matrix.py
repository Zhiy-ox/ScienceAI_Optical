"""Tests for Gap Detection Mechanism A: Method-Problem Matrix."""

import pytest

from science_ai.agents.gap_detection.method_problem_matrix import MethodProblemMatrix


def _make_ko(paper_id, problem, method, limitations=None):
    """Helper to create a minimal knowledge object."""
    ko = {
        "paper_id": paper_id,
        "research_problem": {"statement": problem},
        "method": {"core_idea": method},
    }
    if limitations:
        ko["limitations"] = [{"description": lim} for lim in limitations]
    return ko


def test_build_matrix_basic():
    matrix = MethodProblemMatrix()
    kos = [
        _make_ko("p1", "image classification", "convolutional neural network"),
        _make_ko("p2", "image classification", "vision transformer"),
        _make_ko("p3", "object detection", "convolutional neural network"),
    ]
    matrix.build_from_knowledge_objects(kos)

    assert len(matrix.problems) == 2
    assert len(matrix.methods) == 2
    summary = matrix.get_matrix_summary()
    assert summary["total_cells"] == 4
    assert summary["filled_cells"] == 3
    assert summary["empty_cells"] == 1


def test_find_empty_cells():
    matrix = MethodProblemMatrix()
    kos = [
        _make_ko("p1", "problem A", "method X"),
        _make_ko("p2", "problem A", "method Y"),
        _make_ko("p3", "problem B", "method X"),
        # (problem B, method Y) is missing
    ]
    matrix.build_from_knowledge_objects(kos)
    gaps = matrix.find_empty_cells()

    assert len(gaps) == 1
    assert gaps[0]["problem"] == "problem b"
    assert gaps[0]["method"] == "method y"
    assert gaps[0]["type"] == "empty_cell"


def test_find_shared_limitation_gaps():
    matrix = MethodProblemMatrix()
    kos = [
        _make_ko("p1", "problem A", "method 1", ["limited to English data"]),
        _make_ko("p2", "problem A", "method 2", ["limited to English data"]),
        _make_ko("p3", "problem A", "method 3", ["limited to English data", "slow inference"]),
    ]
    matrix.build_from_knowledge_objects(kos)
    gaps = matrix.find_shared_limitation_gaps()

    assert len(gaps) == 1
    assert gaps[0]["type"] == "shared_limitation"
    assert gaps[0]["methods_tried"] == 3
    assert "limited to english data" in gaps[0]["shared_limitations"]


def test_no_shared_limitation_with_few_methods():
    matrix = MethodProblemMatrix()
    kos = [
        _make_ko("p1", "problem A", "method 1", ["limitation 1"]),
        _make_ko("p2", "problem A", "method 2", ["limitation 1"]),
    ]
    matrix.build_from_knowledge_objects(kos)
    gaps = matrix.find_shared_limitation_gaps()
    assert len(gaps) == 0  # Need 3+ methods


@pytest.mark.asyncio
async def test_filter_by_similarity():
    matrix = MethodProblemMatrix()

    # Mock embedding function that returns simple vectors
    async def mock_embed(text):
        if "image" in text.lower():
            return [1.0, 0.0, 0.0]
        elif "text" in text.lower():
            return [0.0, 1.0, 0.0]
        elif "audio" in text.lower():
            return [0.0, 0.0, 1.0]
        return [0.5, 0.5, 0.0]

    gaps = [
        {"problem": "image classification", "method": "image features CNN", "type": "empty_cell"},
        {"problem": "text analysis", "method": "audio processing", "type": "empty_cell"},
    ]

    filtered = await matrix.filter_by_similarity(gaps, mock_embed, threshold=0.3)

    # "image classification" × "image features CNN" should pass (high cosine)
    # "text analysis" × "audio processing" should be filtered (low cosine)
    assert len(filtered) == 1
    assert "image" in filtered[0]["problem"]
