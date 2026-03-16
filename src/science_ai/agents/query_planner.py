"""Agent 1: Query Planner — decomposes research questions into structured search plans."""

from __future__ import annotations

import logging
from typing import Any

from science_ai.agents.base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a research planning AI. Your job is to take a user's research question \
and produce a structured research plan.

You MUST output valid JSON with this exact schema:
{
  "research_question": "the user's original question",
  "decomposed_questions": ["sub-question 1", "sub-question 2", ...],
  "search_queries": [
    {"keywords": ["term1", "term2"], "source": "semantic_scholar"},
    {"keywords": ["term3", "term4"], "source": "arxiv"}
  ],
  "scope": {
    "year_range": [start_year, end_year],
    "venues": ["venue1", "venue2"],
    "min_citations": 5
  },
  "reading_priority": "description of reading strategy"
}

Guidelines:
- Decompose the question into 3-6 focused sub-questions
- Generate 4-8 diverse search queries across both Semantic Scholar and arXiv
- Include both English and Chinese keyword variants if the topic has Chinese research
- Set year_range based on the field maturity (emerging fields: recent 3 years; established: 5+ years)
- List top venues for the specific field
- Describe a reading priority: surveys first, then high-citation methods, then latest work
"""


class QueryPlanner(BaseAgent):
    """Decomposes a research question into a structured search plan."""

    agent_name = "query_planner"
    default_task_type = "query_planning"

    async def run(self, *, question: str, **kwargs: Any) -> dict[str, Any]:
        """Generate a research plan from a natural language question.

        Args:
            question: The user's research question.

        Returns:
            Structured research plan dict.
        """
        messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"Research question:\n{question}\n\n"
                "Generate the research plan as JSON."
            ),
        ]

        result = await self.call_llm_json(messages=messages, max_tokens=4096)
        plan = result["parsed"]

        logger.info(
            "QueryPlanner: %d sub-questions, %d search queries",
            len(plan.get("decomposed_questions", [])),
            len(plan.get("search_queries", [])),
        )

        return plan
