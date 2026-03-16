"""Tests for Gap Detection Mechanism C: Citation Graph Analysis."""

import pytest

from science_ai.agents.gap_detection.citation_graph import CitationGraphAnalyzer
from science_ai.storage.graph_store import InMemoryGraphStore


def _make_ko(paper_id, problem, method, year=2024, assumptions=None, datasets=None):
    return {
        "paper_id": paper_id,
        "title": f"Paper {paper_id}",
        "year": year,
        "venue": "Test",
        "authors": ["Author A"],
        "research_problem": {"statement": problem},
        "method": {"core_idea": method, "description": f"Description of {method}"},
        "assumptions": assumptions or [],
        "experiments": {"datasets": datasets or []},
    }


@pytest.fixture
def graph():
    return InMemoryGraphStore()


@pytest.mark.asyncio
async def test_community_silos(graph):
    # Two communities with no cross-citations
    kos = [
        _make_ko("p1", "NLP translation", "transformer"),
        _make_ko("p2", "NLP translation", "seq2seq"),
        _make_ko("p3", "image segmentation", "U-Net"),
        _make_ko("p4", "image segmentation", "mask-rcnn"),
    ]
    for ko in kos:
        await graph.ingest_knowledge_object(ko)

    # No cross-citations between NLP and vision
    await graph.add_citation("p1", "p2")
    await graph.add_citation("p3", "p4")

    silos = await graph.find_community_silos()
    assert len(silos) >= 1
    # Should find NLP vs vision silo
    fields = {(s["field1"], s["field2"]) for s in silos}
    assert any(
        ("NLP translation" in f1 and "image segmentation" in f2)
        or ("image segmentation" in f1 and "NLP translation" in f2)
        for f1, f2 in fields
    )


@pytest.mark.asyncio
async def test_broken_chains(graph):
    kos = [
        _make_ko("base", "problem A", "method X", year=2022),
        _make_ko("critic", "problem A", "method Y", year=2023),
    ]
    for ko in kos:
        await graph.ingest_knowledge_object(ko)

    graph.criticisms["critic"] = {"base"}

    chains = await graph.find_broken_chains()
    assert len(chains) == 1
    assert chains[0]["base_id"] == "base"
    assert chains[0]["critic_id"] == "critic"


@pytest.mark.asyncio
async def test_shared_unverified_assumptions(graph):
    kos = [
        _make_ko("p1", "prob", "m1", assumptions=[{"assumption": "Data is clean", "type": "implicit"}]),
        _make_ko("p2", "prob", "m2", assumptions=[{"assumption": "Data is clean", "type": "implicit"}]),
        _make_ko("p3", "prob", "m3", assumptions=[{"assumption": "Data is clean", "type": "explicit"}]),
    ]
    for ko in kos:
        await graph.ingest_knowledge_object(ko)

    results = await graph.find_shared_unverified_assumptions(min_papers=3)
    assert len(results) == 1
    assert results[0]["assumption"] == "Data is clean"
    assert results[0]["cnt"] == 3


@pytest.mark.asyncio
async def test_citation_analyzer_integration(graph):
    kos = [
        _make_ko("p1", "NLP", "method A", assumptions=[{"assumption": "Shared X", "type": "explicit"}]),
        _make_ko("p2", "NLP", "method B", assumptions=[{"assumption": "Shared X", "type": "explicit"}]),
        _make_ko("p3", "NLP", "method C", assumptions=[{"assumption": "Shared X", "type": "explicit"}]),
        _make_ko("p4", "Vision", "method D"),
        _make_ko("p5", "Vision", "method E"),
    ]
    for ko in kos:
        await graph.ingest_knowledge_object(ko)

    analyzer = CitationGraphAnalyzer()
    gaps = await analyzer.detect(graph, kos)

    # Should find at least shared assumption gap
    assert len(gaps) >= 1
    types = {g.get("gap_type") for g in gaps}
    assert "shared_unverified_assumption" in types
