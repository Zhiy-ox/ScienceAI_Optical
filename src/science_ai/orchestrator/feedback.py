"""Feedback loop controllers for iterative refinement."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class FeedbackController:
    """Manages the three feedback loops defined in the architecture.

    Loop 1: Search Refinement — new keywords discovered during reading
    Loop 2: Gap Verification — gaps found to be active areas
    Loop 3: Idea Feasibility — infeasible ideas sent back for regeneration
    """

    def __init__(self, max_iterations: int = 3) -> None:
        self.max_iterations = max_iterations
        self.iteration_counts: dict[str, int] = {}

    def should_refine_search(
        self,
        session_id: str,
        original_keywords: list[str],
        discovered_keywords: list[str],
    ) -> bool:
        """Loop 1: Check if >30% of discovered keywords are new."""
        key = f"{session_id}:search_refine"
        if self.iteration_counts.get(key, 0) >= self.max_iterations:
            logger.info("Search refinement loop hit max iterations for %s", session_id)
            return False

        if not discovered_keywords:
            return False

        original_set = {k.lower() for k in original_keywords}
        new_keywords = [k for k in discovered_keywords if k.lower() not in original_set]
        ratio = len(new_keywords) / len(discovered_keywords) if discovered_keywords else 0

        if ratio > 0.3:
            self.iteration_counts[key] = self.iteration_counts.get(key, 0) + 1
            logger.info(
                "Loop 1 triggered: %.0f%% new keywords (%d/%d), iteration %d",
                ratio * 100, len(new_keywords), len(discovered_keywords),
                self.iteration_counts[key],
            )
            return True
        return False

    def should_retry_gap_detection(
        self,
        session_id: str,
        verification_results: list[dict[str, Any]],
    ) -> bool:
        """Loop 2: Check if too many gaps were invalidated."""
        key = f"{session_id}:gap_retry"
        if self.iteration_counts.get(key, 0) >= self.max_iterations:
            return False

        verified = sum(1 for r in verification_results if r.get("status") == "verified_gap")
        total = len(verification_results)

        if total > 0 and verified / total < 0.3:
            self.iteration_counts[key] = self.iteration_counts.get(key, 0) + 1
            logger.info(
                "Loop 2 triggered: only %d/%d gaps verified, iteration %d",
                verified, total, self.iteration_counts[key],
            )
            return True
        return False

    def should_regenerate_idea(
        self,
        session_id: str,
        feasibility_score: float,
    ) -> bool:
        """Loop 3: Check if an idea's experiment plan is infeasible."""
        key = f"{session_id}:idea_regen"
        if self.iteration_counts.get(key, 0) >= self.max_iterations:
            return False

        if feasibility_score < 0.4:
            self.iteration_counts[key] = self.iteration_counts.get(key, 0) + 1
            logger.info(
                "Loop 3 triggered: feasibility=%.2f, iteration %d",
                feasibility_score, self.iteration_counts[key],
            )
            return True
        return False
