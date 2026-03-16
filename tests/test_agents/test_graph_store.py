"""Tests for the InMemoryGraphStore."""

import pytest

from science_ai.storage.graph_store import InMemoryGraphStore


@pytest.fixture
def graph():
    return InMemoryGraphStore()


@pytest.mark.asyncio
async def test_ingest_knowledge_object(graph):
    ko = {
        "paper_id": "test-1",
        "title": "Test Paper",
        "year": 2025,
        "venue": "NeurIPS",
        "authors": ["Alice", "Bob"],
        "research_problem": {"statement": "Solve X"},
        "method": {"core_idea": "Use Y", "description": "Detailed Y"},
        "assumptions": [
            {"assumption": "Data is clean", "type": "explicit"},
        ],
        "experiments": {"datasets": ["MNIST", "CIFAR"]},
    }
    await graph.ingest_knowledge_object(ko)

    assert "test-1" in graph.papers
    assert "Solve X" in graph.problems
    assert "Use Y" in graph.methods
    assert "Data is clean" in graph.assumptions
    assert "MNIST" in graph.datasets
    assert "CIFAR" in graph.datasets
    assert "Solve X" in graph.paper_problems["test-1"]
    assert "Use Y" in graph.paper_methods["test-1"]


@pytest.mark.asyncio
async def test_add_citation(graph):
    await graph.add_citation("p1", "p2")
    assert "p2" in graph.citations["p1"]


@pytest.mark.asyncio
async def test_method_problem_coverage(graph):
    ko1 = {
        "paper_id": "p1", "title": "P1", "year": 2024,
        "research_problem": {"statement": "Problem A"},
        "method": {"core_idea": "Method X"},
        "assumptions": [], "experiments": {"datasets": []},
    }
    ko2 = {
        "paper_id": "p2", "title": "P2", "year": 2024,
        "research_problem": {"statement": "Problem A"},
        "method": {"core_idea": "Method Y"},
        "assumptions": [], "experiments": {"datasets": []},
    }
    await graph.ingest_knowledge_object(ko1)
    await graph.ingest_knowledge_object(ko2)

    coverage = await graph.get_method_problem_coverage()
    assert len(coverage) == 2
    methods = {c["method"] for c in coverage}
    assert "Method X" in methods
    assert "Method Y" in methods
