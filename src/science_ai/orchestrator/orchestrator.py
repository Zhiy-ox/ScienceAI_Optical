"""Main orchestrator — drives the research pipeline end-to-end."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from science_ai.agents.query_planner import QueryPlanner
from science_ai.agents.paper_triage import PaperTriage
from science_ai.agents.deep_reader import DeepReader
from science_ai.cost.tracker import CostTracker
from science_ai.orchestrator.feedback import FeedbackController
from science_ai.orchestrator.model_router import ModelRouter
from science_ai.services.llm_client import LLMClient
from science_ai.services.paper_search import PaperSearchService

logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    """Orchestrates the full research pipeline.

    Phase 1 pipeline:
        1. Query Planner → structured research plan
        2. Paper Search → fetch papers from APIs
        3. Paper Triage → screen and rank papers
        4. Deep Reader → extract knowledge objects from top papers
    """

    def __init__(
        self,
        cost_tracker: CostTracker | None = None,
        search_service: PaperSearchService | None = None,
        model_router: ModelRouter | None = None,
    ) -> None:
        self.cost_tracker = cost_tracker or CostTracker()
        self.llm = LLMClient(cost_tracker=self.cost_tracker)
        self.search = search_service or PaperSearchService()
        self.router = model_router or ModelRouter()
        self.feedback = FeedbackController()

    async def run_phase1(
        self,
        question: str,
        *,
        session_id: str | None = None,
        max_papers_to_read: int = 15,
    ) -> dict[str, Any]:
        """Run the Phase 1 pipeline: plan → search → triage → read.

        Args:
            question: User's research question.
            session_id: Optional session ID (auto-generated if not provided).
            max_papers_to_read: Max papers for deep reading.

        Returns:
            Dict with plan, triage_results, knowledge_objects, and cost_summary.
        """
        session_id = session_id or str(uuid.uuid4())
        logger.info("Starting Phase 1 pipeline for session %s", session_id)

        # Step 1: Query Planning
        logger.info("Step 1: Query Planning")
        planner = QueryPlanner(self.llm, session_id=session_id)
        plan = await planner.run(question=question)

        # Step 2: Paper Search
        logger.info("Step 2: Paper Search")
        all_papers = await self._execute_search(plan)
        logger.info("Found %d unique papers", len(all_papers))

        if not all_papers:
            return {
                "session_id": session_id,
                "plan": plan,
                "triage_results": [],
                "knowledge_objects": [],
                "cost_summary": self.cost_tracker.session_summary(session_id),
                "status": "no_papers_found",
            }

        # Step 3: Paper Triage
        logger.info("Step 3: Paper Triage")
        triage_agent = PaperTriage(self.llm, session_id=session_id)
        papers_for_triage = [
            {"paper_id": p.paper_id, "title": p.title, "abstract": p.abstract}
            for p in all_papers
        ]
        triage_results = await triage_agent.run(
            question=question, papers=papers_for_triage
        )

        # Sort by relevance and pick top papers for deep reading
        must_read = [r for r in triage_results if r.get("priority") == "must_read"]
        worth_reading = [r for r in triage_results if r.get("priority") == "worth_reading"]

        papers_to_read = must_read[:max_papers_to_read]
        remaining_slots = max_papers_to_read - len(papers_to_read)
        if remaining_slots > 0:
            papers_to_read.extend(worth_reading[:remaining_slots])

        # Step 4: Deep Reading
        logger.info("Step 4: Deep Reading (%d papers)", len(papers_to_read))
        reader = DeepReader(self.llm, session_id=session_id)
        knowledge_objects = []

        # Build a lookup from paper_id to full paper data
        paper_lookup = {p.paper_id: p for p in all_papers}

        for triage in papers_to_read:
            pid = triage.get("paper_id", "")
            paper = paper_lookup.get(pid)
            if not paper:
                continue

            priority = "high" if triage.get("priority") == "must_read" else "medium"
            # Use abstract as text if full text not available
            text = paper.abstract or ""

            try:
                ko = await reader.run(
                    paper_text=text,
                    paper_id=pid,
                    title=paper.title,
                    priority=priority,
                )
                knowledge_objects.append(ko)
            except Exception:
                logger.exception("Failed to deep-read paper %s", pid)

        cost_summary = self.cost_tracker.session_summary(session_id)
        logger.info(
            "Phase 1 complete: %d knowledge objects, total cost $%.4f",
            len(knowledge_objects),
            cost_summary["total_usd"],
        )

        return {
            "session_id": session_id,
            "plan": plan,
            "papers_found": len(all_papers),
            "triage_results": triage_results,
            "knowledge_objects": knowledge_objects,
            "cost_summary": cost_summary,
            "status": "completed",
        }

    async def _execute_search(self, plan: dict) -> list:
        """Execute all search queries from the plan."""
        from science_ai.services.paper_search import PaperMeta

        all_papers: list[PaperMeta] = []
        seen_ids: set[str] = set()

        search_queries = plan.get("search_queries", [])
        scope = plan.get("scope", {})
        year_range = scope.get("year_range")
        if year_range and isinstance(year_range, list) and len(year_range) == 2:
            year_range = tuple(year_range)
        else:
            year_range = None

        for sq in search_queries:
            keywords = sq.get("keywords", [])
            source = sq.get("source", "semantic_scholar")
            query_str = " ".join(keywords)

            try:
                papers = await self.search.search(
                    query_str,
                    sources=[source],
                    limit=50,
                    year_range=year_range,
                )
                for p in papers:
                    if p.paper_id not in seen_ids:
                        seen_ids.add(p.paper_id)
                        all_papers.append(p)
            except Exception:
                logger.exception("Search failed for query: %s", query_str)

        return all_papers
