"""Main orchestrator — drives the research pipeline end-to-end."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from science_ai.agents.critique import CritiqueAgent
from science_ai.agents.deep_reader import DeepReader
from science_ai.agents.gap_detector import GapDetector
from science_ai.agents.paper_triage import PaperTriage
from science_ai.agents.query_planner import QueryPlanner
from science_ai.agents.verification import VerificationAgent
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

    Phase 2 additions:
        5. Critique Agent → critical analysis of deep-read papers
        6. Gap Detector → identify research gaps (mechanisms A + D + LLM synthesis)
        7. Verification Agent → verify gap novelty via search
        + Feedback Loop 1: search refinement when new keywords discovered
        + Feedback Loop 2: retry gap detection if too few verified
        + Vector store indexing for semantic search
    """

    def __init__(
        self,
        cost_tracker: CostTracker | None = None,
        search_service: PaperSearchService | None = None,
        model_router: ModelRouter | None = None,
        vector_store=None,
        embedding_fn=None,
    ) -> None:
        self.cost_tracker = cost_tracker or CostTracker()
        self.llm = LLMClient(cost_tracker=self.cost_tracker)
        self.search = search_service or PaperSearchService()
        self.router = model_router or ModelRouter()
        self.feedback = FeedbackController()
        self.vector_store = vector_store
        self.embedding_fn = embedding_fn

    async def run_phase1(
        self,
        question: str,
        *,
        session_id: str | None = None,
        max_papers_to_read: int = 15,
    ) -> dict[str, Any]:
        """Run Phase 1: plan → search → triage → read."""
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
        paper_lookup = {p.paper_id: p for p in all_papers}

        for triage in papers_to_read:
            pid = triage.get("paper_id", "")
            paper = paper_lookup.get(pid)
            if not paper:
                continue

            priority = "high" if triage.get("priority") == "must_read" else "medium"
            text = paper.abstract or ""

            try:
                ko = await reader.run(
                    paper_text=text, paper_id=pid, title=paper.title, priority=priority,
                )
                knowledge_objects.append(ko)
            except Exception:
                logger.exception("Failed to deep-read paper %s", pid)

        # --- Feedback Loop 1: Search Refinement ---
        knowledge_objects, all_papers, triage_results = await self._search_refinement_loop(
            question=question,
            plan=plan,
            knowledge_objects=knowledge_objects,
            all_papers=all_papers,
            triage_results=triage_results,
            paper_lookup=paper_lookup,
            reader=reader,
            triage_agent=triage_agent,
            session_id=session_id,
            max_papers_to_read=max_papers_to_read,
        )

        cost_summary = self.cost_tracker.session_summary(session_id)
        logger.info(
            "Phase 1 complete: %d knowledge objects, total cost $%.4f",
            len(knowledge_objects), cost_summary["total_usd"],
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

    async def run_phase2(
        self,
        question: str,
        *,
        session_id: str | None = None,
        max_papers_to_read: int = 15,
    ) -> dict[str, Any]:
        """Run Phase 1 + Phase 2: adds critique, gap detection, and verification.

        Returns dict with all Phase 1 results plus:
        - critiques: critical analysis of each paper
        - gaps: detected research gaps
        - verified_gaps: gaps verified for novelty
        """
        # Run Phase 1 first
        phase1_result = await self.run_phase1(
            question=question,
            session_id=session_id,
            max_papers_to_read=max_papers_to_read,
        )

        session_id = phase1_result["session_id"]
        knowledge_objects = phase1_result.get("knowledge_objects", [])

        if not knowledge_objects:
            phase1_result["critiques"] = []
            phase1_result["gaps"] = []
            phase1_result["verified_gaps"] = []
            return phase1_result

        # Step 5: Critique Agent — critical analysis of deep-read papers
        logger.info("Step 5: Critique (%d papers)", len(knowledge_objects))
        critique_agent = CritiqueAgent(self.llm, session_id=session_id)
        critiques = []
        for ko in knowledge_objects:
            try:
                critique = await critique_agent.run(knowledge_obj=ko)
                critiques.append(critique)
            except Exception:
                logger.exception("Failed to critique paper %s", ko.get("paper_id"))

        # Index into vector store if available
        if self.vector_store and self.embedding_fn:
            logger.info("Indexing %d knowledge objects into vector store", len(knowledge_objects))
            for ko in knowledge_objects:
                try:
                    await self.vector_store.index_knowledge_object(ko, self.embedding_fn)
                except Exception:
                    logger.exception("Failed to index paper %s", ko.get("paper_id"))

        # Step 6: Gap Detection (mechanisms A + D + LLM synthesis)
        logger.info("Step 6: Gap Detection")
        gap_detector = GapDetector(
            self.llm,
            session_id=session_id,
            embedding_fn=self.embedding_fn,
        )
        gaps = await gap_detector.run(
            knowledge_objects=knowledge_objects,
            critiques=critiques,
        )

        # Step 7: Verification Agent — verify gap novelty
        logger.info("Step 7: Verification (%d gaps)", len(gaps))
        verifier = VerificationAgent(
            self.llm, session_id=session_id, search_service=self.search
        )
        verification_results = await verifier.run(gaps=gaps)

        # --- Feedback Loop 2: Gap Re-detection ---
        if self.feedback.should_retry_gap_detection(session_id, verification_results):
            logger.info("Feedback Loop 2: retrying gap detection with adjusted parameters")
            # Provide the verification failures as context for better detection
            failed_gaps = [
                v for v in verification_results if v.get("status") != "verified_gap"
            ]
            gaps = await gap_detector.run(
                knowledge_objects=knowledge_objects,
                critiques=critiques,
                previous_failures=failed_gaps,
            )
            verification_results = await verifier.run(gaps=gaps)

        verified_gaps = [
            v for v in verification_results if v.get("status") == "verified_gap"
        ]

        cost_summary = self.cost_tracker.session_summary(session_id)
        logger.info(
            "Phase 2 complete: %d critiques, %d gaps, %d verified, cost $%.4f",
            len(critiques), len(gaps), len(verified_gaps), cost_summary["total_usd"],
        )

        return {
            **phase1_result,
            "critiques": critiques,
            "gaps": gaps,
            "verification_results": verification_results,
            "verified_gaps": verified_gaps,
            "cost_summary": cost_summary,
            "status": "completed",
        }

    async def _search_refinement_loop(
        self,
        *,
        question: str,
        plan: dict,
        knowledge_objects: list[dict],
        all_papers: list,
        triage_results: list[dict],
        paper_lookup: dict,
        reader,
        triage_agent,
        session_id: str,
        max_papers_to_read: int,
    ) -> tuple[list[dict], list, list[dict]]:
        """Feedback Loop 1: Refine search if deep reading discovers new keywords.

        Per spec: triggers when >30% of discovered keywords are new.
        """
        # Extract original keywords from plan
        original_keywords = []
        for sq in plan.get("search_queries", []):
            original_keywords.extend(sq.get("keywords", []))

        # Extract discovered keywords from knowledge objects
        discovered_keywords = []
        for ko in knowledge_objects:
            method = ko.get("method", {})
            if method.get("key_components"):
                discovered_keywords.extend(method["key_components"])
            problem = ko.get("research_problem", {})
            if problem.get("statement"):
                # Extract key terms (simple heuristic: multi-word phrases)
                words = problem["statement"].split()
                if len(words) >= 2:
                    discovered_keywords.append(problem["statement"])

        if not self.feedback.should_refine_search(session_id, original_keywords, discovered_keywords):
            return knowledge_objects, all_papers, triage_results

        logger.info("Feedback Loop 1: Refining search with new keywords")

        # Generate new search queries from discovered keywords
        new_keywords = [
            k for k in discovered_keywords
            if k.lower() not in {ok.lower() for ok in original_keywords}
        ]

        for kw in new_keywords[:5]:  # limit to 5 new searches
            try:
                new_papers = await self.search.search(kw, limit=30)
                seen_ids = {p.paper_id for p in all_papers}
                added = [p for p in new_papers if p.paper_id not in seen_ids]
                all_papers.extend(added)

                if added:
                    # Triage new papers
                    new_for_triage = [
                        {"paper_id": p.paper_id, "title": p.title, "abstract": p.abstract}
                        for p in added
                    ]
                    new_triage = await triage_agent.run(question=question, papers=new_for_triage)
                    triage_results.extend(new_triage)

                    # Deep read new must-reads
                    for t in new_triage:
                        if t.get("priority") == "must_read" and len(knowledge_objects) < max_papers_to_read * 2:
                            pid = t.get("paper_id", "")
                            paper = next((p for p in added if p.paper_id == pid), None)
                            if paper:
                                try:
                                    ko = await reader.run(
                                        paper_text=paper.abstract or "",
                                        paper_id=pid,
                                        title=paper.title,
                                        priority="high",
                                    )
                                    knowledge_objects.append(ko)
                                except Exception:
                                    logger.exception("Failed to deep-read refined paper %s", pid)
            except Exception:
                logger.exception("Refinement search failed for keyword: %s", kw)

        logger.info(
            "Search refinement done: now %d papers, %d knowledge objects",
            len(all_papers), len(knowledge_objects),
        )
        return knowledge_objects, all_papers, triage_results

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
                    query_str, sources=[source], limit=50, year_range=year_range,
                )
                for p in papers:
                    if p.paper_id not in seen_ids:
                        seen_ids.add(p.paper_id)
                        all_papers.append(p)
            except Exception:
                logger.exception("Search failed for query: %s", query_str)

        return all_papers
