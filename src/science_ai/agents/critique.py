"""Agent 4: Critique Agent — critical analysis of papers (Phase 2)."""

from __future__ import annotations

import logging
from typing import Any

from science_ai.agents.base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a critical academic reviewer. Analyze the paper's knowledge object and identify:

1. Assumption issues: Are assumptions reasonable? Validated?
2. Experimental weaknesses: Missing evaluations, weak baselines, limited datasets
3. Evidence gaps: Claims not fully supported by evidence
4. Generalization concerns: Will the method work beyond tested conditions?
5. Reproducibility risks: Missing details, unavailable data/code

Output valid JSON:
{
  "paper_id": "string",
  "critique": {
    "assumption_issues": [
      {"assumption": "...", "problem": "...", "severity": "low|medium|high"}
    ],
    "experimental_weaknesses": [
      {"issue": "...", "type": "missing_evaluation|weak_baseline|limited_data|other", "severity": "low|medium|high"}
    ],
    "evidence_gaps": [
      {"claim": "...", "problem": "...", "severity": "low|medium|high"}
    ],
    "generalization_concerns": ["..."],
    "reproducibility_risks": ["..."]
  },
  "overall_confidence": 0.0-1.0
}
"""


class CritiqueAgent(BaseAgent):
    """Performs critical analysis of papers. Phase 2 agent."""

    agent_name = "critique"
    default_task_type = "critique"

    async def run(
        self,
        *,
        knowledge_obj: dict[str, Any],
        paper_text: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Critique a paper based on its knowledge object.

        Args:
            knowledge_obj: Paper Knowledge Object from DeepReader.
            paper_text: Optional full text for deeper analysis.
        """
        import json

        context = f"Paper Knowledge Object:\n{json.dumps(knowledge_obj, indent=2)}"
        if paper_text:
            context += f"\n\nFull paper text:\n{paper_text}"

        messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"{context}\n\nProvide your critical analysis as JSON."
            ),
        ]

        result = await self.call_llm_json(messages=messages, max_tokens=4096)
        logger.info("CritiqueAgent: analyzed paper '%s'", knowledge_obj.get("title", ""))
        return result["parsed"]
