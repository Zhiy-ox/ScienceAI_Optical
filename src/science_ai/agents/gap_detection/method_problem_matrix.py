"""Gap Detection Mechanism A: Method-Problem Matrix.

Builds an n×m matrix of Problems × Methods from knowledge objects,
identifies empty cells (gaps), and filters out unreasonable combinations
using embedding cosine similarity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MatrixCell:
    problem: str
    method: str
    papers: list[str] = field(default_factory=list)
    is_gap: bool = False


class MethodProblemMatrix:
    """Builds and analyzes the Method × Problem matrix for gap detection.

    From the architecture spec:
    - Method never applied to a problem → candidate gap
    - Method-problem embedding cosine < 0.3 → exclude (unreasonable combo)
    - Problem has 3+ methods but all share same limitation → high-value gap
    """

    def __init__(self) -> None:
        self.problems: dict[str, list[str]] = {}   # problem → [paper_ids]
        self.methods: dict[str, list[str]] = {}     # method → [paper_ids]
        self.cells: dict[tuple[str, str], list[str]] = {}  # (problem, method) → [paper_ids]
        self.limitations_by_problem: dict[str, list[dict]] = {}  # problem → [{method, limitations}]

    def build_from_knowledge_objects(
        self, knowledge_objects: list[dict[str, Any]]
    ) -> None:
        """Extract problems, methods, and their relationships from KOs."""
        for ko in knowledge_objects:
            paper_id = ko.get("paper_id", "")
            problem_stmt = ko.get("research_problem", {}).get("statement", "")
            method_idea = ko.get("method", {}).get("core_idea", "")

            if not problem_stmt or not method_idea:
                continue

            # Normalize keys
            problem_key = problem_stmt.strip().lower()
            method_key = method_idea.strip().lower()

            # Track problem
            if problem_key not in self.problems:
                self.problems[problem_key] = []
            self.problems[problem_key].append(paper_id)

            # Track method
            if method_key not in self.methods:
                self.methods[method_key] = []
            self.methods[method_key].append(paper_id)

            # Track cell
            cell_key = (problem_key, method_key)
            if cell_key not in self.cells:
                self.cells[cell_key] = []
            self.cells[cell_key].append(paper_id)

            # Track limitations per problem-method
            limitations = ko.get("limitations", [])
            if limitations:
                if problem_key not in self.limitations_by_problem:
                    self.limitations_by_problem[problem_key] = []
                self.limitations_by_problem[problem_key].append({
                    "method": method_key,
                    "paper_id": paper_id,
                    "limitations": [lim.get("description", "") for lim in limitations],
                })

    def find_empty_cells(self) -> list[dict[str, Any]]:
        """Find problem-method combinations with no papers (candidate gaps)."""
        gaps = []
        for problem in self.problems:
            for method in self.methods:
                cell_key = (problem, method)
                if cell_key not in self.cells:
                    gaps.append({
                        "problem": problem,
                        "method": method,
                        "type": "empty_cell",
                    })
        return gaps

    def find_shared_limitation_gaps(self) -> list[dict[str, Any]]:
        """Find problems where 3+ methods all have the same limitation pattern.

        Per spec: problem has 3+ methods tried, all with same limitation → high-value gap.
        """
        gaps = []
        for problem, method_lims in self.limitations_by_problem.items():
            if len(method_lims) < 3:
                continue

            # Collect all limitation strings
            all_limitations: list[str] = []
            for ml in method_lims:
                all_limitations.extend(ml["limitations"])

            if not all_limitations:
                continue

            # Find limitations mentioned by multiple methods
            lim_counts: dict[str, int] = {}
            for lim in all_limitations:
                lim_lower = lim.lower().strip()
                if lim_lower:
                    lim_counts[lim_lower] = lim_counts.get(lim_lower, 0) + 1

            shared = [lim for lim, count in lim_counts.items() if count >= 2]
            if shared:
                gaps.append({
                    "problem": problem,
                    "shared_limitations": shared,
                    "methods_tried": len(method_lims),
                    "type": "shared_limitation",
                })

        return gaps

    async def filter_by_similarity(
        self,
        gaps: list[dict[str, Any]],
        embedding_fn,
        threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Remove unreasonable method-problem combos using embedding cosine similarity.

        Per spec: method-problem cosine < 0.3 → exclude.
        """
        if not gaps:
            return []

        filtered = []
        for gap in gaps:
            if gap["type"] != "empty_cell":
                filtered.append(gap)
                continue

            problem_vec = await embedding_fn(gap["problem"])
            method_vec = await embedding_fn(gap["method"])

            similarity = self._cosine_similarity(problem_vec, method_vec)
            if similarity >= threshold:
                gap["similarity_score"] = round(similarity, 3)
                filtered.append(gap)
            else:
                logger.debug(
                    "Filtered out gap (cos=%.3f < %.3f): %s × %s",
                    similarity, threshold, gap["problem"][:40], gap["method"][:40],
                )

        logger.info(
            "Matrix filter: %d/%d gaps passed similarity threshold %.2f",
            len(filtered), len(gaps), threshold,
        )
        return filtered

    def get_matrix_summary(self) -> dict[str, Any]:
        """Return a summary of the matrix for reporting."""
        total_cells = len(self.problems) * len(self.methods)
        filled = len(self.cells)
        return {
            "num_problems": len(self.problems),
            "num_methods": len(self.methods),
            "total_cells": total_cells,
            "filled_cells": filled,
            "empty_cells": total_cells - filled,
            "fill_rate": round(filled / total_cells, 3) if total_cells > 0 else 0,
        }

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
