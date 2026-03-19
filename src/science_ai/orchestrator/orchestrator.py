"""Main orchestrator — drives the research pipeline end-to-end."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from science_ai.agents.critique import CritiqueAgent
from science_ai.agents.deep_reader import DeepReader
from science_ai.agents.experiment_planner import ExperimentPlanner
from science_ai.agents.gap_detector import GapDetector
from science_ai.agents.idea_generator import IdeaGenerator
from science_ai.agents.paper_triage import PaperTriage
from science_ai.agents.query_planner import QueryPlanner
from science_ai.agents.report_writer import ReportWriter
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
        graph_store=None,
        embedding_fn=None,
        zotero_client=None,
        llm_backend: str | None = None,
    ) -> None:
        from science_ai.config import settings

        self.cost_tracker = cost_tracker or CostTracker()

        # Choose LLM backend: "cli" (free) or "api" (paid)
        backend = llm_backend or settings.llm_backend
        if backend == "cli":
            from science_ai.services.cli_llm_client import CLILLMClient
            self.llm = CLILLMClient(
                cost_tracker=self.cost_tracker,
                codex_cmd=settings.cli_codex_command,
                gemini_cmd=settings.cli_gemini_command,
                claude_cmd=settings.cli_claude_command,
                timeout=settings.cli_timeout_seconds,
            )
            logger.info("Using CLI backend (free mode): codex + gemini + claude")
        else:
            self.llm = LLMClient(cost_tracker=self.cost_tracker)
            logger.info("Using API backend (paid mode): litellm")

        self.search = search_service or PaperSearchService()
        self.router = model_router or ModelRouter()
        self.feedback = FeedbackController()
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.embedding_fn = embedding_fn
        self.zotero_client = zotero_client

    async def run_phase1(
        self,
        question: str,
        *,
        session_id: str | None = None,
        max_papers_to_read: int = 15,
        source: str = "web",
    ) -> dict[str, Any]:
        """Run Phase 1: plan → search → triage → read."""
        session_id = session_id or str(uuid.uuid4())
        logger.info("Starting Phase 1 pipeline for session %s (source=%s)", session_id, source)

        # Step 1: Query Planning
        logger.info("Step 1: Query Planning")
        planner = QueryPlanner(self.llm, session_id=session_id)
        plan = await planner.run(question=question)

        # Step 2: Paper Search
        logger.info("Step 2: Paper Search")
        all_papers = []

        # Fetch from web sources
        if source in ("web", "both"):
            all_papers = await self._execute_search(plan)

        # Fetch from Zotero
        if source in ("zotero", "both") and self.zotero_client:
            try:
                zotero_papers = self.zotero_client.search(question, limit=50)
                # Deduplicate against existing papers
                seen_titles = {p.title.lower().strip() for p in all_papers}
                for zp in zotero_papers:
                    if zp.title.lower().strip() not in seen_titles:
                        all_papers.append(zp)
                        seen_titles.add(zp.title.lower().strip())
                logger.info("Added %d papers from Zotero", len(zotero_papers))
            except Exception:
                logger.exception("Zotero search failed")
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
            "_all_papers": all_papers,  # kept for Zotero export
        }

    async def run_phase2(
        self,
        question: str,
        *,
        session_id: str | None = None,
        max_papers_to_read: int = 15,
        source: str = "web",
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
            source=source,
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

        # Populate graph store if available
        if self.graph_store:
            logger.info("Populating knowledge graph with %d papers", len(knowledge_objects))
            for ko in knowledge_objects:
                try:
                    await self.graph_store.ingest_knowledge_object(ko)
                except Exception:
                    logger.exception("Failed to ingest paper %s into graph", ko.get("paper_id"))

        # Step 6: Gap Detection (all 4 mechanisms + LLM synthesis)
        logger.info("Step 6: Gap Detection")
        gap_detector = GapDetector(
            self.llm,
            session_id=session_id,
            embedding_fn=self.embedding_fn,
            graph_store=self.graph_store,
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

    async def run_phase3(
        self,
        question: str,
        *,
        session_id: str | None = None,
        max_papers_to_read: int = 15,
        user_background: str = "",
        source: str = "web",
    ) -> dict[str, Any]:
        """Run full pipeline (Phase 1 + 2 + 3): adds ideas, experiments, and report.

        Phase 3 additions:
        - Idea Generator → research ideas from verified gaps
        - Experiment Planner → concrete experiment plans
        - Feedback Loop 3 → regenerate infeasible ideas
        - Report Writer → comprehensive final report
        """
        # Run Phase 2 first (which includes Phase 1)
        phase2_result = await self.run_phase2(
            question=question,
            session_id=session_id,
            max_papers_to_read=max_papers_to_read,
            source=source,
        )

        session_id = phase2_result["session_id"]
        knowledge_objects = phase2_result.get("knowledge_objects", [])
        verified_gaps = phase2_result.get("verified_gaps", [])

        if not verified_gaps:
            logger.warning("No verified gaps found — skipping idea generation")
            phase2_result["ideas"] = []
            phase2_result["experiment_plans"] = []
            phase2_result["report"] = None
            return phase2_result

        # Step 8: Idea Generation
        logger.info("Step 8: Idea Generation (%d verified gaps)", len(verified_gaps))
        idea_gen = IdeaGenerator(self.llm, session_id=session_id)
        ideas = await idea_gen.run(
            verified_gaps=verified_gaps,
            knowledge_objects=knowledge_objects,
            user_background=user_background,
        )

        # Step 9: Experiment Planning + Feedback Loop 3
        logger.info("Step 9: Experiment Planning (%d ideas)", len(ideas))
        exp_planner = ExperimentPlanner(self.llm, session_id=session_id)
        experiment_plans: list[dict[str, Any]] = []

        for idea in ideas:
            try:
                plan = await exp_planner.run(
                    idea=idea, knowledge_objects=knowledge_objects,
                )
                feasibility = plan.get("feasibility_score", 0.5)

                # Feedback Loop 3: regenerate infeasible ideas
                if self.feedback.should_regenerate_idea(session_id, feasibility):
                    logger.info(
                        "Feedback Loop 3: idea '%s' infeasible (%.2f), regenerating",
                        idea.get("title", ""), feasibility,
                    )
                    # Regenerate with feasibility constraints
                    new_ideas = await idea_gen.run(
                        verified_gaps=[g for g in verified_gaps if g.get("gap_id") == idea.get("source_gap")],
                        knowledge_objects=knowledge_objects,
                        user_background=user_background + f"\nConstraint: previous idea was infeasible due to: {plan.get('experiment_plan', {}).get('risks', [])}",
                    )
                    if new_ideas:
                        idea = new_ideas[0]  # Use the regenerated idea
                        plan = await exp_planner.run(
                            idea=idea, knowledge_objects=knowledge_objects,
                        )

                experiment_plans.append(plan)
            except Exception:
                logger.exception("Failed to plan experiment for idea '%s'", idea.get("title", ""))

        # Step 10: Report Generation
        logger.info("Step 10: Report Generation")
        report_writer = ReportWriter(self.llm, session_id=session_id)
        cost_summary = self.cost_tracker.session_summary(session_id)

        try:
            report = await report_writer.run(
                question=question,
                plan=phase2_result.get("plan", {}),
                knowledge_objects=knowledge_objects,
                critiques=phase2_result.get("critiques", []),
                verified_gaps=verified_gaps,
                ideas=ideas,
                experiment_plans=experiment_plans,
                cost_summary=cost_summary,
            )
        except Exception:
            logger.exception("Failed to generate report")
            report = None

        # Export to Zotero if client is configured
        zotero_collection_key = None
        if self.zotero_client:
            try:
                from science_ai.services.paper_search import PaperMeta
                # Reconstruct all_papers from phase1 (stored in triage_results via paper_id)
                all_papers_meta = phase2_result.get("_all_papers", [])
                zotero_collection_key = self.zotero_client.export_session(
                    session_id=session_id,
                    question=question,
                    triage_results=phase2_result.get("triage_results", []),
                    knowledge_objects=knowledge_objects,
                    critiques=phase2_result.get("critiques", []),
                    verified_gaps=verified_gaps,
                    ideas=ideas,
                    report=report,
                    all_papers=all_papers_meta,
                )
                logger.info("Exported to Zotero collection: %s", zotero_collection_key)
            except Exception:
                logger.exception("Failed to export session to Zotero")

        cost_summary = self.cost_tracker.session_summary(session_id)
        logger.info(
            "Phase 3 complete: %d ideas, %d experiment plans, report=%s, cost $%.4f",
            len(ideas), len(experiment_plans),
            "yes" if report else "no",
            cost_summary["total_usd"],
        )

        result = {
            **phase2_result,
            "ideas": ideas,
            "experiment_plans": experiment_plans,
            "report": report,
            "cost_summary": cost_summary,
            "status": "completed",
        }
        if zotero_collection_key:
            result["zotero_collection_key"] = zotero_collection_key
        return result

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
