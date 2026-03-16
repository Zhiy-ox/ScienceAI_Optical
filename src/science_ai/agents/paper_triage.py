"""Agent 2: Paper Triage — batch screens papers by relevance using Gemini."""

from __future__ import annotations

import json
import logging
from typing import Any

from science_ai.agents.base import BaseAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a paper triage AI. You quickly assess batches of academic papers for \
relevance to a research question.

For each paper, output a JSON object with:
{
  "paper_id": "the paper's ID",
  "relevance_score": 0.0-1.0,
  "category": "survey" | "method" | "application" | "benchmark" | "theory",
  "priority": "must_read" | "worth_reading" | "skip",
  "brief_reason": "one sentence explaining relevance"
}

Scoring guidelines:
- 0.8-1.0: Directly addresses the research question → must_read
- 0.5-0.79: Related but tangential → worth_reading
- 0.0-0.49: Not relevant → skip

Output a JSON object with key "results" containing an array of assessments.
"""

BATCH_SIZE = 50


class PaperTriage(BaseAgent):
    """Batch-screens papers for relevance to a research question."""

    agent_name = "paper_triage"
    default_task_type = "paper_triage"

    async def run(
        self,
        *,
        question: str,
        papers: list[dict[str, str]],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Screen a list of papers.

        Args:
            question: The research question.
            papers: List of dicts with keys: paper_id, title, abstract.

        Returns:
            List of triage results, one per paper.
        """
        all_results: list[dict[str, Any]] = []

        # Process in batches
        for i in range(0, len(papers), BATCH_SIZE):
            batch = papers[i : i + BATCH_SIZE]
            batch_results = await self._triage_batch(question, batch)
            all_results.extend(batch_results)

        logger.info(
            "PaperTriage: screened %d papers — %d must_read, %d worth_reading, %d skip",
            len(all_results),
            sum(1 for r in all_results if r.get("priority") == "must_read"),
            sum(1 for r in all_results if r.get("priority") == "worth_reading"),
            sum(1 for r in all_results if r.get("priority") == "skip"),
        )

        return all_results

    async def _triage_batch(
        self, question: str, batch: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        """Triage a single batch of papers."""
        papers_text = "\n\n".join(
            f"--- Paper {j+1} ---\n"
            f"ID: {p['paper_id']}\n"
            f"Title: {p['title']}\n"
            f"Abstract: {p['abstract']}"
            for j, p in enumerate(batch)
        )

        messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"Research question: {question}\n\n"
                f"Papers to screen ({len(batch)} papers):\n\n{papers_text}\n\n"
                "Assess each paper and output JSON with key 'results'."
            ),
        ]

        result = await self.call_llm_json(messages=messages, max_tokens=8192)
        parsed = result["parsed"]

        # Handle both {"results": [...]} and direct list
        if isinstance(parsed, list):
            return parsed
        return parsed.get("results", [])
