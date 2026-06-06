"""Parity harness — compare legacy vs. graph orchestrator outputs.

Used during cutover (Stage 7) to confirm the LangGraph pipeline produces
structurally equivalent results to the legacy sequential orchestrator on a
fixed question set before flipping the default mode.

The comparison logic (`compare_results`) is a pure function and is unit-tested.
`run_parity` runs both pipelines live (requires configured LLM backends).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Metrics compared for structural parity. Searches/LLM outputs are
# non-deterministic, so callers may allow a tolerance on the counts.
_COUNT_FIELDS = (
    "knowledge_objects",
    "gaps",
    "verified_gaps",
    "ideas",
    "experiment_plans",
)


def _metrics(result: dict[str, Any]) -> dict[str, int]:
    """Extract comparable scalar metrics from a result dict."""
    papers = result.get("papers_found")
    if not papers:
        papers = len(result.get("_all_papers", []) or result.get("all_papers", []) or [])
    return {
        "papers_found": int(papers or 0),
        "knowledge_objects": len(result.get("knowledge_objects", [])),
        "gaps": len(result.get("gaps", [])),
        "verified_gaps": len(result.get("verified_gaps", [])),
        "ideas": len(result.get("ideas", [])),
        "experiment_plans": len(result.get("experiment_plans", [])),
        "report": 1 if result.get("report") else 0,
    }


@dataclass
class FieldComparison:
    field: str
    legacy: int
    graph: int
    match: bool

    @property
    def delta(self) -> int:
        return self.graph - self.legacy


@dataclass
class ParityReport:
    comparisons: list[FieldComparison] = field(default_factory=list)
    overall_match: bool = False

    def summary(self) -> str:
        lines = [
            f"{'PASS' if self.overall_match else 'FAIL'} — legacy vs. graph parity",
        ]
        for c in self.comparisons:
            mark = "✓" if c.match else "✗"
            lines.append(
                f"  {mark} {c.field:<18} legacy={c.legacy:<5} graph={c.graph:<5} "
                f"(Δ{c.delta:+d})"
            )
        return "\n".join(lines)


def compare_results(
    legacy: dict[str, Any],
    graph: dict[str, Any],
    *,
    tolerance: int = 0,
) -> ParityReport:
    """Compare two result dicts metric-by-metric.

    ``tolerance`` allows count fields (papers/KOs/gaps/etc.) to differ by up to
    N due to non-determinism. ``report`` presence is always compared exactly.
    """
    lm = _metrics(legacy)
    gm = _metrics(graph)

    comparisons: list[FieldComparison] = []
    for key in ("papers_found", *_COUNT_FIELDS, "report"):
        lv, gv = lm[key], gm[key]
        if key == "report":
            match = lv == gv
        else:
            match = abs(gv - lv) <= tolerance
        comparisons.append(FieldComparison(field=key, legacy=lv, graph=gv, match=match))

    overall = all(c.match for c in comparisons)
    return ParityReport(comparisons=comparisons, overall_match=overall)


async def run_parity(
    question: str,
    *,
    phase: int = 3,
    max_papers: int = 10,
    user_background: str = "",
    source: str = "web",
    tolerance: int = 2,
) -> ParityReport:
    """Run both orchestrators on the same question and compare (live).

    Requires a configured LLM backend. Imports are lazy so this module can be
    imported (and `compare_results` tested) without the agent/LLM stack.
    """
    from science_ai.cost.tracker import CostTracker
    from science_ai.orchestrator.graph.runner import GraphRunner
    from science_ai.orchestrator.orchestrator import ResearchOrchestrator

    # --- Legacy ---
    legacy_orch = ResearchOrchestrator(cost_tracker=CostTracker())
    if phase >= 3:
        legacy = await legacy_orch.run_phase3(
            question, max_papers_to_read=max_papers,
            user_background=user_background, source=source,
        )
    elif phase == 2:
        legacy = await legacy_orch.run_phase2(
            question, max_papers_to_read=max_papers, source=source,
        )
    else:
        legacy = await legacy_orch.run_phase1(
            question, max_papers_to_read=max_papers, source=source,
        )

    # --- Graph ---
    runner = GraphRunner()
    graph = await runner.run(
        question, phase=phase, max_papers=max_papers,
        user_background=user_background, source=source,
    )

    report = compare_results(legacy, graph, tolerance=tolerance)
    logger.info("Parity result:\n%s", report.summary())
    return report
