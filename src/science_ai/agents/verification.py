"""Agent 6: Verification Agent — verifies novelty of research gaps (Phase 2)."""

from __future__ import annotations

import json
import logging
from typing import Any

from science_ai.agents.base import BaseAgent
from science_ai.services.paper_search import PaperSearchService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a research novelty verification AI. For each candidate research gap, \
determine whether it is:
- "verified_gap": No existing work addresses this gap
- "active_area": Recent published work already addresses this
- "emerging": Preprints or very recent work is starting to address this

Generate search queries to verify each gap, then assess the search results.

Output JSON:
{
  "gap_id": "GAP-XXX",
  "status": "verified_gap|active_area|emerging",
  "search_queries_used": ["query1", "query2"],
  "relevant_papers_found": [
    {"paper_id": "...", "title": "...", "relevance": "description"}
  ],
  "reasoning": "explanation of the verdict"
}
"""


class VerificationAgent(BaseAgent):
    """Verifies novelty of candidate research gaps. Phase 2 agent."""

    agent_name = "verification"
    default_task_type = "verification"

    def __init__(self, llm_client, session_id: str = "", search_service: PaperSearchService | None = None):
        super().__init__(llm_client, session_id)
        self.search = search_service or PaperSearchService()

    async def run(
        self,
        *,
        gaps: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Verify each candidate gap for novelty.

        Args:
            gaps: List of candidate gap dicts from GapDetector.
        """
        results = []
        for gap in gaps:
            result = await self._verify_single_gap(gap)
            results.append(result)

        verified = sum(1 for r in results if r.get("status") == "verified_gap")
        logger.info(
            "VerificationAgent: %d/%d gaps verified as novel",
            verified, len(gaps),
        )
        return results

    async def _verify_single_gap(self, gap: dict[str, Any]) -> dict[str, Any]:
        """Verify a single gap by searching for existing work."""
        # First, ask LLM to generate search queries for this gap
        gen_messages = [
            self.build_system_message(
                "Generate 2-3 search queries to check if this research gap "
                "has already been addressed. Output JSON: {\"queries\": [\"q1\", \"q2\"]}"
            ),
            self.build_user_message(
                f"Research gap:\n{json.dumps(gap, indent=2)}"
            ),
        ]
        query_result = await self.call_llm_json(messages=gen_messages, max_tokens=512)
        queries = query_result["parsed"].get("queries", [gap.get("description", "")])

        # Search for each query
        found_papers = []
        for q in queries[:3]:
            papers = await self.search.search(q, limit=10)
            found_papers.extend(
                {"paper_id": p.paper_id, "title": p.title, "abstract": p.abstract[:200]}
                for p in papers[:5]
            )

        # Ask LLM to assess if any found papers address the gap
        assess_messages = [
            self.build_system_message(SYSTEM_PROMPT),
            self.build_user_message(
                f"Gap to verify:\n{json.dumps(gap, indent=2)}\n\n"
                f"Search results:\n{json.dumps(found_papers, indent=2)}\n\n"
                "Assess whether this gap is verified, active, or emerging."
            ),
        ]
        result = await self.call_llm_json(messages=assess_messages, max_tokens=2048)
        return result["parsed"]
