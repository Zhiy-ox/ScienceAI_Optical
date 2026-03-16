"""Agent 5: Gap Detector — identifies research gaps using all four mechanisms."""

from __future__ import annotations

import json
import logging
from typing import Any

from science_ai.agents.base import BaseAgent
from science_ai.agents.gap_detection.assumption_chain import AssumptionChainAnalyzer
from science_ai.agents.gap_detection.citation_graph import CitationGraphAnalyzer
from science_ai.agents.gap_detection.evaluation_blindspots import EvaluationBlindspotDetector
from science_ai.agents.gap_detection.method_problem_matrix import MethodProblemMatrix

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a research gap detection AI. You will be given:
1. Paper knowledge objects from deep reading
2. Critique reports identifying weaknesses
3. Pre-computed structural analysis from four mechanisms:
   A) Method-Problem Matrix gaps
   B) Assumption Chain Analysis gaps
   C) Citation Graph Structural gaps
   D) Evaluation Blind Spots

Your job is to synthesize ALL inputs and produce a final ranked list of research gaps.

For each pre-computed gap, assess whether it is meaningful and adjust confidence scores.
Also identify any additional gaps from patterns you observe.

For each gap, output:
{
  "gap_id": "GAP-XXX",
  "detection_mechanism": "method_problem_matrix|assumption_chain|citation_graph|evaluation_blindspot|synthesis",
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
    """Detects research gaps using all four mechanisms:

    A) Method-Problem Matrix (computed locally)
    B) Assumption Chain Analysis (computed locally)
    C) Citation Graph Structural Analysis (from graph store)
    D) Evaluation Blind Spots (computed locally)
    + LLM synthesis for final ranking
    """

    agent_name = "gap_detector"
    default_task_type = "gap_detection"

    def __init__(self, llm_client, session_id: str = "", embedding_fn=None, graph_store=None):
        super().__init__(llm_client, session_id)
        self.matrix = MethodProblemMatrix()
        self.eval_detector = EvaluationBlindspotDetector()
        self.assumption_analyzer = AssumptionChainAnalyzer()
        self.citation_analyzer = CitationGraphAnalyzer()
        self.embedding_fn = embedding_fn
        self.graph_store = graph_store

    async def run(
        self,
        *,
        knowledge_objects: list[dict[str, Any]],
        critiques: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Detect research gaps using all available mechanisms."""

        # --- Mechanism A: Method-Problem Matrix ---
        logger.info("Running Mechanism A: Method-Problem Matrix")
        self.matrix.build_from_knowledge_objects(knowledge_objects)
        matrix_gaps = self.matrix.find_empty_cells()
        shared_lim_gaps = self.matrix.find_shared_limitation_gaps()

        if self.embedding_fn and matrix_gaps:
            matrix_gaps = await self.matrix.filter_by_similarity(
                matrix_gaps, self.embedding_fn, threshold=0.3
            )

        matrix_summary = self.matrix.get_matrix_summary()
        logger.info(
            "Matrix: %d problems × %d methods, %d empty cells, %d shared-limitation gaps",
            matrix_summary["num_problems"], matrix_summary["num_methods"],
            len(matrix_gaps), len(shared_lim_gaps),
        )

        # --- Mechanism B: Assumption Chain Analysis ---
        logger.info("Running Mechanism B: Assumption Chain Analysis")
        assumption_gaps = self.assumption_analyzer.detect(knowledge_objects)
        logger.info("Assumption chain: %d gaps found", len(assumption_gaps))

        # --- Mechanism C: Citation Graph Structural Analysis ---
        citation_gaps: list[dict[str, Any]] = []
        if self.graph_store:
            logger.info("Running Mechanism C: Citation Graph Analysis")
            citation_gaps = await self.citation_analyzer.detect(self.graph_store, knowledge_objects)
            logger.info("Citation graph: %d gaps found", len(citation_gaps))
        else:
            logger.info("Skipping Mechanism C: no graph store available")

        # --- Mechanism D: Evaluation Blind Spots ---
        logger.info("Running Mechanism D: Evaluation Blind Spots")
        eval_gaps = self.eval_detector.detect(knowledge_objects)
        logger.info("Eval blind spots: %d found", len(eval_gaps))

        # --- LLM Synthesis: combine all mechanisms + final ranking ---
        precomputed = {
            "mechanism_a_matrix": {
                "summary": matrix_summary,
                "empty_cell_gaps": matrix_gaps[:15],
                "shared_limitation_gaps": shared_lim_gaps,
            },
            "mechanism_b_assumption_chain": assumption_gaps[:15],
            "mechanism_c_citation_graph": citation_gaps[:15],
            "mechanism_d_evaluation_blindspots": eval_gaps,
        }

        logger.info("Running LLM synthesis across all mechanisms")
        context = f"Paper Knowledge Objects ({len(knowledge_objects)} papers):\n"
        context += json.dumps(knowledge_objects, indent=2)

        if critiques:
            context += f"\n\nCritique Reports ({len(critiques)} reports):\n"
            context += json.dumps(critiques, indent=2)

        context += f"\n\nPre-computed Gap Analysis (4 mechanisms):\n{json.dumps(precomputed, indent=2)}"

        messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"{context}\n\n"
                "Synthesize all four mechanisms. Validate pre-computed gaps, identify additional "
                "patterns, and output a final ranked list of all gaps as JSON."
            ),
        ]

        result = await self.call_llm_json(messages=messages, max_tokens=8192)
        gaps = result["parsed"].get("gaps", [])

        total_precomputed = len(matrix_gaps) + len(assumption_gaps) + len(citation_gaps) + len(eval_gaps)
        logger.info(
            "GapDetector: %d final gaps from %d pre-computed (A=%d, B=%d, C=%d, D=%d)",
            len(gaps), total_precomputed,
            len(matrix_gaps), len(assumption_gaps), len(citation_gaps), len(eval_gaps),
        )
        return gaps
