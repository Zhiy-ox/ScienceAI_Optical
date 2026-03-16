"""Gap Detection Mechanism D: Evaluation Blind Spot Detection.

Analyzes evaluation practices across papers to find systematic gaps:
- Dataset bias: all papers test on same type of datasets
- Metric missing: no human evaluation, only automatic metrics
- Baseline outdated: everyone compares to old baselines
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


class EvaluationBlindspotDetector:
    """Detects evaluation blind spots across a collection of papers.

    From the architecture spec:
    1. Dataset bias: all papers only test on same-type datasets
    2. Metric missing: all use automatic metrics, no human evaluation
    3. Baseline outdated: all compare to old baselines (≥3 years)
    """

    def detect(
        self,
        knowledge_objects: list[dict[str, Any]],
        current_year: int = 2026,
    ) -> list[dict[str, Any]]:
        """Run all evaluation blind spot checks.

        Args:
            knowledge_objects: List of Paper Knowledge Objects.
            current_year: Current year for baseline age calculation.

        Returns:
            List of evaluation blind spot gap dicts.
        """
        gaps: list[dict[str, Any]] = []

        gaps.extend(self._check_dataset_bias(knowledge_objects))
        gaps.extend(self._check_metric_gaps(knowledge_objects))
        gaps.extend(self._check_baseline_staleness(knowledge_objects, current_year))

        logger.info("EvaluationBlindspotDetector: found %d blind spots", len(gaps))
        return gaps

    def _check_dataset_bias(
        self, knowledge_objects: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Check if all papers use the same datasets."""
        all_datasets: list[str] = []
        papers_with_experiments = 0

        for ko in knowledge_objects:
            experiments = ko.get("experiments", {})
            datasets = experiments.get("datasets", [])
            if datasets:
                papers_with_experiments += 1
                all_datasets.extend(d.lower().strip() for d in datasets)

        if papers_with_experiments < 3:
            return []

        dataset_counts = Counter(all_datasets)
        total_unique = len(dataset_counts)

        # If >60% of papers use the same dataset, flag it
        gaps = []
        for dataset, count in dataset_counts.most_common(3):
            usage_ratio = count / papers_with_experiments
            if usage_ratio > 0.6:
                gaps.append({
                    "gap_id": f"EVAL-DS-{dataset[:20].upper().replace(' ', '_')}",
                    "detection_mechanism": "evaluation_blindspot",
                    "blindspot_type": "dataset_bias",
                    "description": (
                        f"Dataset concentration: '{dataset}' is used by "
                        f"{count}/{papers_with_experiments} papers ({usage_ratio:.0%}). "
                        f"Only {total_unique} unique datasets across all papers."
                    ),
                    "evidence": {
                        "dominant_dataset": dataset,
                        "usage_count": count,
                        "total_papers": papers_with_experiments,
                        "unique_datasets": total_unique,
                    },
                    "confidence": min(0.9, usage_ratio),
                    "potential_impact": "high" if usage_ratio > 0.8 else "medium",
                })

        return gaps

    def _check_metric_gaps(
        self, knowledge_objects: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Check if papers lack human evaluation or diversity of metrics."""
        all_metrics: list[str] = []
        has_human_eval = False
        papers_with_metrics = 0

        human_eval_keywords = {"human", "manual", "expert", "annotator", "subjective", "mos"}

        for ko in knowledge_objects:
            experiments = ko.get("experiments", {})
            metrics = experiments.get("metrics", [])
            if metrics:
                papers_with_metrics += 1
                for m in metrics:
                    m_lower = m.lower()
                    all_metrics.append(m_lower)
                    if any(kw in m_lower for kw in human_eval_keywords):
                        has_human_eval = True

        if papers_with_metrics < 3:
            return []

        gaps = []

        # No human evaluation at all
        if not has_human_eval:
            gaps.append({
                "gap_id": "EVAL-NO-HUMAN",
                "detection_mechanism": "evaluation_blindspot",
                "blindspot_type": "missing_human_evaluation",
                "description": (
                    f"None of the {papers_with_metrics} papers include human evaluation. "
                    "All rely exclusively on automatic metrics."
                ),
                "evidence": {
                    "total_papers": papers_with_metrics,
                    "all_metrics": list(set(all_metrics)),
                },
                "confidence": 0.85,
                "potential_impact": "high",
            })

        # Check metric diversity
        metric_counts = Counter(all_metrics)
        unique_metrics = len(metric_counts)
        if unique_metrics <= 2 and papers_with_metrics >= 3:
            gaps.append({
                "gap_id": "EVAL-LOW-METRIC-DIV",
                "detection_mechanism": "evaluation_blindspot",
                "blindspot_type": "low_metric_diversity",
                "description": (
                    f"Only {unique_metrics} unique metrics across {papers_with_metrics} papers. "
                    "Limited evaluation perspective."
                ),
                "evidence": {
                    "metrics": dict(metric_counts),
                    "total_papers": papers_with_metrics,
                },
                "confidence": 0.7,
                "potential_impact": "medium",
            })

        return gaps

    def _check_baseline_staleness(
        self,
        knowledge_objects: list[dict[str, Any]],
        current_year: int,
    ) -> list[dict[str, Any]]:
        """Check if all baselines are outdated."""
        baseline_names: list[str] = []
        papers_with_baselines = 0

        for ko in knowledge_objects:
            experiments = ko.get("experiments", {})
            baselines = experiments.get("baselines", [])
            if baselines:
                papers_with_baselines += 1
                baseline_names.extend(b.lower().strip() for b in baselines)

        if papers_with_baselines < 3:
            return []

        # Check if the same baselines appear everywhere
        baseline_counts = Counter(baseline_names)
        most_common_baselines = baseline_counts.most_common(5)

        gaps = []

        # If one baseline is used by >70% of papers
        for baseline, count in most_common_baselines:
            ratio = count / papers_with_baselines
            if ratio > 0.7:
                gaps.append({
                    "gap_id": f"EVAL-STALE-BL-{baseline[:20].upper().replace(' ', '_')}",
                    "detection_mechanism": "evaluation_blindspot",
                    "blindspot_type": "baseline_staleness",
                    "description": (
                        f"Baseline '{baseline}' is used by {count}/{papers_with_baselines} "
                        f"papers ({ratio:.0%}). This baseline may be outdated and not "
                        "representative of current state-of-the-art."
                    ),
                    "evidence": {
                        "baseline": baseline,
                        "usage_count": count,
                        "total_papers": papers_with_baselines,
                    },
                    "confidence": 0.65,
                    "potential_impact": "medium",
                })

        return gaps
