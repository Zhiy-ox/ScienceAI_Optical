"""Agent 5: Gap Detector — identifies research gaps using multiple mechanisms."""

from __future__ import annotations

import json
import logging
from typing import Any

from science_ai.agents.base import BaseAgent
from science_ai.agents.gap_detection.evaluation_blindspots import EvaluationBlindspotDetector
from science_ai.agents.gap_detection.method_problem_matrix import MethodProblemMatrix

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a research gap detection AI. You will be given:
1. Paper knowledge objects from deep reading
2. Critique reports identifying weaknesses
3. Pre-computed structural analysis (method-problem matrix gaps, evaluation blind spots)

Your job is to synthesize all inputs and produce a final ranked list of research gaps.

For the pre-computed gaps, assess whether each is meaningful and adjust confidence scores.
Also identify additional gaps using:
- Assumption Chain Analysis: shared unverified assumptions, assumption conflicts
- Any patterns you observe across the papers

For each gap, output:
{
  "gap_id": "GAP-XXX",
  "detection_mechanism": "method_problem_matrix|assumption_chain|evaluation_blindspot|synthesis",
  "description": "clear description of the gap",
  "evidence": [
    {"paper_id": "...", "relevant_finding": "..."}
  ],
  "confidence": 0.0-1.0,
  "potential_impact": "low|medium|high",
  "novelty_verified": false
}

Output JSON with key "gaps" containing an array sorted by confidence × impact (highest first).
"""


class GapDetector(BaseAgent):
    """Detects research gaps using four mechanisms:

    A) Method-Problem Matrix (computed locally)
    D) Evaluation Blind Spots (computed locally)
    B) Assumption Chain Analysis (LLM-driven)
    + Synthesis of all signals
    """

    agent_name = "gap_detector"
    default_task_type = "gap_detection"

    def __init__(self, llm_client, session_id: str = "", embedding_fn=None):
        super().__init__(llm_client, session_id)
        self.matrix = MethodProblemMatrix()
        self.eval_detector = EvaluationBlindspotDetector()
        self.embedding_fn = embedding_fn  # async callable(text) -> list[float]

    async def run(
        self,
        *,
        knowledge_objects: list[dict[str, Any]],
        critiques: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Detect research gaps using all available mechanisms.

        Args:
            knowledge_objects: List of Paper Knowledge Objects.
            critiques: Optional list of critique reports.
        """
        # --- Mechanism A: Method-Problem Matrix ---
        logger.info("Running Mechanism A: Method-Problem Matrix")
        self.matrix.build_from_knowledge_objects(knowledge_objects)
        matrix_gaps = self.matrix.find_empty_cells()
        shared_lim_gaps = self.matrix.find_shared_limitation_gaps()

        # Filter empty cells by embedding similarity if we have an embedding function
        if self.embedding_fn and matrix_gaps:
            matrix_gaps = await self.matrix.filter_by_similarity(
                matrix_gaps, self.embedding_fn, threshold=0.3
            )

        matrix_summary = self.matrix.get_matrix_summary()
        logger.info(
            "Matrix: %d problems × %d methods, %d empty cells (filtered), %d shared-limitation gaps",
            matrix_summary["num_problems"],
            matrix_summary["num_methods"],
            len(matrix_gaps),
            len(shared_lim_gaps),
        )

        # --- Mechanism D: Evaluation Blind Spots ---
        logger.info("Running Mechanism D: Evaluation Blind Spots")
        eval_gaps = self.eval_detector.detect(knowledge_objects)
        logger.info("Eval blind spots: %d found", len(eval_gaps))

        # --- Prepare pre-computed analysis for LLM synthesis ---
        precomputed = {
            "matrix_summary": matrix_summary,
            "matrix_gaps": matrix_gaps[:20],  # limit to top 20 for context
            "shared_limitation_gaps": shared_lim_gaps,
            "evaluation_blindspots": eval_gaps,
        }

        # --- LLM synthesis: Mechanism B + final ranking ---
        logger.info("Running LLM synthesis (Mechanism B: Assumption Chain + ranking)")
        context = f"Paper Knowledge Objects ({len(knowledge_objects)} papers):\n"
        context += json.dumps(knowledge_objects, indent=2)

        if critiques:
            context += f"\n\nCritique Reports ({len(critiques)} reports):\n"
            context += json.dumps(critiques, indent=2)

        context += f"\n\nPre-computed Gap Analysis:\n{json.dumps(precomputed, indent=2)}"

        messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"{context}\n\n"
                "Synthesize all inputs. Validate pre-computed gaps, add assumption chain gaps, "
                "and output a final ranked list of all gaps as JSON."
            ),
        ]

        result = await self.call_llm_json(messages=messages, max_tokens=8192)
        gaps = result["parsed"].get("gaps", [])

        logger.info(
            "GapDetector: %d final gaps (matrix=%d, eval=%d, llm-synthesized=%d)",
            len(gaps), len(matrix_gaps), len(eval_gaps), len(gaps),
        )
        return gaps
