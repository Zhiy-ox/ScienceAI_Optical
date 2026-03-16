"""Agent 7: Idea Generator — generates research ideas from verified gaps (Phase 3)."""

from __future__ import annotations

import json
import logging
from typing import Any

from science_ai.agents.base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a creative research idea generator. Given verified research gaps and a \
collection of methods from the literature, generate novel research ideas.

Use these generation strategies:
1. Gap filling: Directly solve a verified gap
2. Method transfer: Apply a method from domain A to domain B
3. Constraint relaxation: Remove a limiting assumption from an existing method
4. Combinatorial innovation: Merge strengths of two methods

For each idea, output:
{
  "idea_id": "IDEA-XXX",
  "title": "one-line description",
  "source_gap": "GAP-XXX",
  "generation_strategy": "gap_filling|method_transfer|constraint_relaxation|combination",
  "description": "2-3 paragraph detailed description",
  "key_hypothesis": "the core hypothesis to test",
  "expected_contribution": "what this would contribute to the field",
  "related_work": ["paper1", "paper2"],
  "novelty_score": 0.0-1.0,
  "feasibility_score": 0.0-1.0,
  "impact_score": 0.0-1.0
}

Output JSON with key "ideas" containing an array.
"""


class IdeaGenerator(BaseAgent):
    """Generates research ideas from verified gaps. Phase 3 agent."""

    agent_name = "idea_generator"
    default_task_type = "idea_generation"

    async def run(
        self,
        *,
        verified_gaps: list[dict[str, Any]],
        knowledge_objects: list[dict[str, Any]],
        user_background: str = "",
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Generate research ideas.

        Args:
            verified_gaps: List of verified gap objects.
            knowledge_objects: Paper Knowledge Objects for method reference.
            user_background: Optional user research background for personalization.
        """
        context = f"Verified Research Gaps:\n{json.dumps(verified_gaps, indent=2)}\n\n"
        context += f"Available Methods (from {len(knowledge_objects)} papers):\n"

        # Extract just methods for context efficiency
        methods = [
            {"paper_id": ko.get("paper_id"), "method": ko.get("method")}
            for ko in knowledge_objects
            if ko.get("method")
        ]
        context += json.dumps(methods, indent=2)

        if user_background:
            context += f"\n\nResearcher's background: {user_background}"

        messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"{context}\n\nGenerate research ideas as JSON."
            ),
        ]

        result = await self.call_llm_json(messages=messages, max_tokens=8192)
        ideas = result["parsed"].get("ideas", [])
        logger.info("IdeaGenerator: generated %d ideas", len(ideas))
        return ideas
