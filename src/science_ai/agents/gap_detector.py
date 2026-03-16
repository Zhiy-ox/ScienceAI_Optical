"""Agent 5: Gap Detector — identifies research gaps (Phase 2/3)."""

from __future__ import annotations

import json
import logging
from typing import Any

from science_ai.agents.base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a research gap detection AI. Analyze the collected paper knowledge objects \
and critique reports to identify research gaps using these four mechanisms:

A) Method-Problem Matrix: Which methods have NOT been applied to which problems?
B) Assumption Chain Analysis: Shared unverified assumptions, assumption conflicts
C) Citation Graph Structural Analysis: Community silos, broken chains, outdated high-citation nodes
D) Evaluation Blind Spot Detection: Dataset biases, missing metrics, outdated baselines

For each candidate gap, output:
{
  "gap_id": "GAP-XXX",
  "detection_mechanism": "method_problem_matrix|assumption_chain|citation_graph|evaluation_blindspot",
  "description": "clear description of the gap",
  "evidence": [
    {"paper_id": "...", "relevant_finding": "..."}
  ],
  "confidence": 0.0-1.0,
  "potential_impact": "low|medium|high",
  "novelty_verified": false
}

Output JSON with key "gaps" containing an array of gap objects.
"""


class GapDetector(BaseAgent):
    """Detects research gaps from collected knowledge. Phase 2/3 agent."""

    agent_name = "gap_detector"
    default_task_type = "gap_detection"

    async def run(
        self,
        *,
        knowledge_objects: list[dict[str, Any]],
        critiques: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Detect research gaps from paper analyses.

        Args:
            knowledge_objects: List of Paper Knowledge Objects.
            critiques: Optional list of critique reports.
        """
        context = f"Paper Knowledge Objects ({len(knowledge_objects)} papers):\n"
        context += json.dumps(knowledge_objects, indent=2)

        if critiques:
            context += f"\n\nCritique Reports ({len(critiques)} reports):\n"
            context += json.dumps(critiques, indent=2)

        messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"{context}\n\nIdentify all research gaps as JSON."
            ),
        ]

        result = await self.call_llm_json(messages=messages, max_tokens=8192)
        gaps = result["parsed"].get("gaps", [])
        logger.info("GapDetector: found %d candidate gaps", len(gaps))
        return gaps
