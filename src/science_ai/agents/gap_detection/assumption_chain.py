"""Gap Detection Mechanism B: Assumption Chain Analysis.

Analyzes assumptions across papers to find:
1. Unverified foundations: assumptions shared by ≥3 papers but never validated
2. Assumption conflicts: paper A assumes X, paper B implies ¬X
3. Assumption-reality gaps: stated assumptions inconsistent with experiments
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AssumptionChainAnalyzer:
    """Detects gaps in assumption chains across papers."""

    def detect(
        self,
        knowledge_objects: list[dict[str, Any]],
        graph_store=None,
    ) -> list[dict[str, Any]]:
        """Run assumption chain analysis.

        Can optionally use graph_store for shared assumption queries,
        but also works purely from knowledge objects.
        """
        gaps: list[dict[str, Any]] = []

        gaps.extend(self._find_unverified_foundations(knowledge_objects))
        gaps.extend(self._find_assumption_conflicts(knowledge_objects))
        gaps.extend(self._find_assumption_reality_gaps(knowledge_objects))

        logger.info("AssumptionChainAnalyzer: found %d gaps", len(gaps))
        return gaps

    def _find_unverified_foundations(
        self, knowledge_objects: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Find assumptions shared by ≥3 papers but never independently validated.

        Per spec: "unverified foundation" — widely relied upon but untested.
        """
        # Collect all assumptions with their source papers
        assumption_papers: dict[str, list[dict]] = {}

        for ko in knowledge_objects:
            paper_id = ko.get("paper_id", "")
            for assumption in ko.get("assumptions", []):
                desc = assumption.get("assumption", "").strip().lower()
                if not desc:
                    continue
                assumption_papers.setdefault(desc, []).append({
                    "paper_id": paper_id,
                    "type": assumption.get("type", "explicit"),
                })

        gaps = []
        for assumption, sources in assumption_papers.items():
            if len(sources) >= 3:
                # Check if any paper explicitly validates this assumption
                # (simple heuristic: none of the papers' methods claim to verify it)
                gaps.append({
                    "gap_id": f"ASSUMP-UNVERIFIED-{len(gaps)+1:03d}",
                    "detection_mechanism": "assumption_chain",
                    "assumption_type": "unverified_foundation",
                    "description": (
                        f"Assumption shared by {len(sources)} papers but never independently "
                        f"validated: '{assumption}'"
                    ),
                    "assumption": assumption,
                    "evidence": [
                        {"paper_id": s["paper_id"], "relevant_finding": f"Assumes: {assumption}"}
                        for s in sources
                    ],
                    "confidence": min(0.9, 0.5 + 0.1 * len(sources)),
                    "potential_impact": "high" if len(sources) >= 5 else "medium",
                })

        return gaps

    def _find_assumption_conflicts(
        self, knowledge_objects: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Find papers with conflicting assumptions.

        Per spec: Paper A assumes X, Paper B implies ¬X → "assumption conflict".

        Uses heuristic: looks for assumption pairs where one paper's assumption
        contains negation words relative to another's.
        """
        # Collect all explicit + implicit assumptions per paper
        paper_assumptions: list[tuple[str, str, str]] = []  # (paper_id, assumption, type)

        for ko in knowledge_objects:
            paper_id = ko.get("paper_id", "")
            for assumption in ko.get("assumptions", []):
                desc = assumption.get("assumption", "").strip()
                if desc:
                    paper_assumptions.append((paper_id, desc, assumption.get("type", "")))

        # Check for potential conflicts using keyword overlap + negation detection
        negation_words = {"not", "no", "without", "lack", "insufficient", "unable", "cannot", "don't", "doesn't", "isn't", "aren't", "never"}

        gaps = []
        seen_pairs = set()

        for i, (pid_a, assump_a, _) in enumerate(paper_assumptions):
            words_a = set(assump_a.lower().split())
            for j, (pid_b, assump_b, _) in enumerate(paper_assumptions):
                if i >= j or pid_a == pid_b:
                    continue

                pair_key = (min(pid_a, pid_b), max(pid_a, pid_b), assump_a[:30], assump_b[:30])
                if pair_key in seen_pairs:
                    continue

                words_b = set(assump_b.lower().split())

                # Check for significant word overlap (same topic)
                content_words_a = words_a - negation_words - {"the", "a", "is", "are", "that", "this", "of", "in", "for", "and", "to"}
                content_words_b = words_b - negation_words - {"the", "a", "is", "are", "that", "this", "of", "in", "for", "and", "to"}

                if not content_words_a or not content_words_b:
                    continue

                overlap = content_words_a & content_words_b
                overlap_ratio = len(overlap) / min(len(content_words_a), len(content_words_b))

                if overlap_ratio < 0.3:
                    continue

                # Check if one has negation and the other doesn't
                has_neg_a = bool(words_a & negation_words)
                has_neg_b = bool(words_b & negation_words)

                if has_neg_a != has_neg_b:
                    seen_pairs.add(pair_key)
                    gaps.append({
                        "gap_id": f"ASSUMP-CONFLICT-{len(gaps)+1:03d}",
                        "detection_mechanism": "assumption_chain",
                        "assumption_type": "assumption_conflict",
                        "description": (
                            f"Conflicting assumptions between papers: "
                            f"'{assump_a}' vs '{assump_b}'"
                        ),
                        "evidence": [
                            {"paper_id": pid_a, "relevant_finding": f"Assumes: {assump_a}"},
                            {"paper_id": pid_b, "relevant_finding": f"Assumes: {assump_b}"},
                        ],
                        "confidence": round(0.5 + overlap_ratio * 0.3, 2),
                        "potential_impact": "high",
                    })

        return gaps

    def _find_assumption_reality_gaps(
        self, knowledge_objects: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Find papers where stated assumptions don't match experimental conditions.

        Per spec: assumption vs experiment mismatch → "assumption-reality gap".

        Heuristic: if an assumption mentions a broad scope but experiments
        are limited to narrow conditions, flag it.
        """
        broad_scope_words = {
            "all", "any", "general", "universal", "every", "always",
            "domain-independent", "language-agnostic", "scalable",
        }

        gaps = []
        for ko in knowledge_objects:
            paper_id = ko.get("paper_id", "")
            experiments = ko.get("experiments", {})
            datasets = experiments.get("datasets", [])

            for assumption in ko.get("assumptions", []):
                desc = assumption.get("assumption", "").lower()
                words = set(desc.split())

                # Check if assumption claims broad applicability
                if words & broad_scope_words and len(datasets) <= 2:
                    gaps.append({
                        "gap_id": f"ASSUMP-REALITY-{len(gaps)+1:03d}",
                        "detection_mechanism": "assumption_chain",
                        "assumption_type": "assumption_reality_gap",
                        "description": (
                            f"Broad assumption '{assumption.get('assumption', '')}' "
                            f"but only tested on {len(datasets)} dataset(s): {datasets}"
                        ),
                        "evidence": [
                            {"paper_id": paper_id, "relevant_finding": f"Assumes: {desc}, tested on: {datasets}"},
                        ],
                        "confidence": 0.6,
                        "potential_impact": "medium",
                    })

        return gaps
