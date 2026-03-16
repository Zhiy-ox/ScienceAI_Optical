"""Gap Detection Mechanism C: Citation Graph Structural Analysis.

Uses the knowledge graph (or in-memory graph) to detect:
1. Community silos: two high-cohesion but low cross-citation sub-communities
2. Broken chains: A proposes method → B criticizes → no C resolves
3. Stale high-citation nodes: highly cited but ≥3 years with no improvement
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CitationGraphAnalyzer:
    """Detects research gaps from citation graph structure."""

    async def detect(
        self,
        graph_store,
        knowledge_objects: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Run all citation graph analyses.

        Args:
            graph_store: GraphStore or InMemoryGraphStore instance.
            knowledge_objects: Optional KOs for supplementary analysis.
        """
        gaps: list[dict[str, Any]] = []

        gaps.extend(await self._find_silo_gaps(graph_store))
        gaps.extend(await self._find_broken_chain_gaps(graph_store))
        gaps.extend(await self._find_shared_assumption_gaps(graph_store))

        logger.info("CitationGraphAnalyzer: found %d gaps", len(gaps))
        return gaps

    async def _find_silo_gaps(self, graph_store) -> list[dict[str, Any]]:
        """Detect community silos — bridging opportunities."""
        try:
            silos = await graph_store.find_community_silos()
        except Exception:
            logger.exception("Failed to query community silos")
            return []

        gaps = []
        for i, silo in enumerate(silos):
            gaps.append({
                "gap_id": f"CITE-SILO-{i+1:03d}",
                "detection_mechanism": "citation_graph",
                "gap_type": "community_silo",
                "description": (
                    f"Low cross-citation between '{silo['field1']}' "
                    f"({silo['papers1']} papers) and '{silo['field2']}' "
                    f"({silo['papers2']} papers) — only {silo['cross_citations']} "
                    f"cross-citations. Potential bridging opportunity."
                ),
                "evidence": [
                    {"paper_id": "", "relevant_finding": f"Field 1: {silo['field1']}"},
                    {"paper_id": "", "relevant_finding": f"Field 2: {silo['field2']}"},
                ],
                "confidence": 0.7,
                "potential_impact": "high",
            })

        return gaps

    async def _find_broken_chain_gaps(self, graph_store) -> list[dict[str, Any]]:
        """Detect broken chains — criticized work with no follow-up."""
        try:
            chains = await graph_store.find_broken_chains()
        except Exception:
            logger.exception("Failed to query broken chains")
            return []

        gaps = []
        for i, chain in enumerate(chains):
            gaps.append({
                "gap_id": f"CITE-BROKEN-{i+1:03d}",
                "detection_mechanism": "citation_graph",
                "gap_type": "broken_chain",
                "description": (
                    f"Paper '{chain['base_title']}' was criticized by "
                    f"'{chain['critic_title']}' but no follow-up work has "
                    f"addressed the criticism."
                ),
                "evidence": [
                    {"paper_id": chain["base_id"], "relevant_finding": "Original work (criticized)"},
                    {"paper_id": chain["critic_id"], "relevant_finding": "Criticism (unresolved)"},
                ],
                "confidence": 0.75,
                "potential_impact": "high",
            })

        return gaps

    async def _find_shared_assumption_gaps(self, graph_store) -> list[dict[str, Any]]:
        """Find widely-shared assumptions from the graph (supplements mechanism B)."""
        try:
            assumptions = await graph_store.find_shared_unverified_assumptions(min_papers=3)
        except Exception:
            logger.exception("Failed to query shared assumptions from graph")
            return []

        gaps = []
        for i, a in enumerate(assumptions):
            gaps.append({
                "gap_id": f"CITE-ASSUMP-{i+1:03d}",
                "detection_mechanism": "citation_graph",
                "gap_type": "shared_unverified_assumption",
                "description": (
                    f"Assumption '{a['assumption']}' is shared by {a['cnt']} papers "
                    f"but appears to be unverified."
                ),
                "evidence": [
                    {"paper_id": pid, "relevant_finding": f"Assumes: {a['assumption']}"}
                    for pid in a["paper_ids"][:5]
                ],
                "confidence": min(0.85, 0.5 + 0.1 * a["cnt"]),
                "potential_impact": "high" if a["cnt"] >= 5 else "medium",
            })

        return gaps
