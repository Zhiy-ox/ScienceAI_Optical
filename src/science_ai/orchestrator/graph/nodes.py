"""Node functions for the LangGraph research pipeline.

Each node wraps an existing agent and returns a partial-state dict that
LangGraph merges back into ResearchState via its reducers.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from science_ai.orchestrator.graph.deps import get_deps
from science_ai.orchestrator.graph.state import ResearchState

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Stage 1: Plan
# ------------------------------------------------------------------

async def plan_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]

    from science_ai.agents.query_planner import QueryPlanner

    planner = QueryPlanner(deps.llm, session_id=sid)
    plan = await planner.run(question=state["question"])

    logger.info("[graph] plan_node complete for %s", sid)
    return {"plan": plan, "status": "planned"}


# ------------------------------------------------------------------
# Stage 2: Search
# ------------------------------------------------------------------

async def search_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    plan = state.get("plan", {})
    source = state.get("source", "web")
    question = state["question"]

    from science_ai.services.paper_search import PaperMeta

    all_papers: list[PaperMeta] = []
    seen_ids: set[str] = set()

    if source in ("web", "both"):
        search_queries = plan.get("search_queries", [])
        scope = plan.get("scope", {})
        year_range = scope.get("year_range")
        if year_range and isinstance(year_range, list) and len(year_range) == 2:
            year_range = tuple(year_range)
        else:
            year_range = None

        for sq in search_queries:
            keywords = sq.get("keywords", [])
            src = sq.get("source", "semantic_scholar")
            query_str = " ".join(keywords)
            try:
                papers = await deps.search.search(
                    query_str, sources=[src], limit=50, year_range=year_range,
                )
                for p in papers:
                    if p.paper_id not in seen_ids:
                        seen_ids.add(p.paper_id)
                        all_papers.append(p)
            except Exception:
                logger.exception("Search failed for query: %s", query_str)

    if source in ("zotero", "both") and deps.zotero_client:
        try:
            zotero_papers = deps.zotero_client.search(question, limit=50)
            seen_titles = {p.title.lower().strip() for p in all_papers}
            for zp in zotero_papers:
                if zp.title.lower().strip() not in seen_titles:
                    all_papers.append(zp)
                    seen_titles.add(zp.title.lower().strip())
            logger.info("Added %d papers from Zotero", len(zotero_papers))
        except Exception:
            logger.exception("Zotero search failed")

    paper_dicts = [
        {"paper_id": p.paper_id, "title": p.title, "abstract": p.abstract}
        for p in all_papers
    ]

    logger.info("[graph] search_node found %d papers", len(all_papers))
    return {
        "all_papers": paper_dicts,
        "papers_found": len(all_papers),
        "status": "searched",
    }


# ------------------------------------------------------------------
# Stage 3: Triage
# ------------------------------------------------------------------

async def triage_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    all_papers = state.get("all_papers", [])

    if not all_papers:
        return {"triage_results": [], "status": "no_papers_found"}

    from science_ai.agents.paper_triage import PaperTriage

    triage_agent = PaperTriage(deps.llm, session_id=sid)
    triage_results = await triage_agent.run(
        question=state["question"], papers=all_papers,
    )

    logger.info("[graph] triage_node: %d results", len(triage_results))
    return {"triage_results": triage_results, "status": "triaged"}


# ------------------------------------------------------------------
# Stage 4: Select papers for deep reading
# ------------------------------------------------------------------

async def select_papers_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    triage_results = state.get("triage_results", [])
    max_papers = state.get("max_papers", 15)

    must_read = [r for r in triage_results if r.get("priority") == "must_read"]
    worth_reading = [r for r in triage_results if r.get("priority") == "worth_reading"]

    papers_to_read = must_read[:max_papers]
    remaining = max_papers - len(papers_to_read)
    if remaining > 0:
        papers_to_read.extend(worth_reading[:remaining])

    logger.info("[graph] select_papers_node: %d selected", len(papers_to_read))
    return {"papers_to_read": papers_to_read, "status": "selected"}


# ------------------------------------------------------------------
# Stage 5: Deep Read (serial in Stage 1; parallel fan-out in Stage 4)
# ------------------------------------------------------------------

async def deep_read_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    papers_to_read = state.get("papers_to_read", [])
    all_papers = state.get("all_papers", [])

    paper_lookup = {p["paper_id"]: p for p in all_papers}

    from science_ai.agents.deep_reader import DeepReader

    reader = DeepReader(deps.llm, session_id=sid)
    knowledge_objects: list[dict] = []

    for triage in papers_to_read:
        pid = triage.get("paper_id", "")
        paper = paper_lookup.get(pid)
        if not paper:
            continue

        priority = "high" if triage.get("priority") == "must_read" else "medium"
        text = paper.get("abstract", "")

        try:
            ko = await reader.run(
                paper_text=text, paper_id=pid, title=paper.get("title", ""),
                priority=priority,
            )
            knowledge_objects.append(ko)
        except Exception:
            logger.exception("Failed to deep-read paper %s", pid)

    logger.info("[graph] deep_read_node: %d KOs", len(knowledge_objects))
    return {"knowledge_objects": knowledge_objects, "status": "deep_read"}


# ------------------------------------------------------------------
# Stage 6: Critique
# ------------------------------------------------------------------

async def critique_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    knowledge_objects = state.get("knowledge_objects", [])

    from science_ai.agents.critique import CritiqueAgent

    critique_agent = CritiqueAgent(deps.llm, session_id=sid)
    critiques: list[dict] = []
    for ko in knowledge_objects:
        try:
            critique = await critique_agent.run(knowledge_obj=ko)
            critiques.append(critique)
        except Exception:
            logger.exception("Failed to critique paper %s", ko.get("paper_id"))

    logger.info("[graph] critique_node: %d critiques", len(critiques))
    return {"critiques": critiques, "status": "critiqued"}


# ------------------------------------------------------------------
# Stage 7: Index (vector + graph stores)
# ------------------------------------------------------------------

async def index_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    knowledge_objects = state.get("knowledge_objects", [])

    if deps.vector_store and deps.embedding_fn:
        for ko in knowledge_objects:
            try:
                await deps.vector_store.index_knowledge_object(ko, deps.embedding_fn)
            except Exception:
                logger.exception("Failed to index paper %s", ko.get("paper_id"))

    if deps.graph_store:
        for ko in knowledge_objects:
            try:
                await deps.graph_store.ingest_knowledge_object(ko)
            except Exception:
                logger.exception("Failed to ingest paper %s into graph", ko.get("paper_id"))

    logger.info("[graph] index_node complete")
    return {"status": "indexed"}


# ------------------------------------------------------------------
# Stage 8: Gap Detection
# ------------------------------------------------------------------

async def gap_detect_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    knowledge_objects = state.get("knowledge_objects", [])
    critiques = state.get("critiques", [])

    from science_ai.agents.gap_detector import GapDetector

    gap_detector = GapDetector(
        deps.llm, session_id=sid,
        embedding_fn=deps.embedding_fn, graph_store=deps.graph_store,
    )
    gaps = await gap_detector.run(
        knowledge_objects=knowledge_objects, critiques=critiques,
    )

    logger.info("[graph] gap_detect_node: %d gaps", len(gaps))
    return {"gaps": gaps, "status": "gaps_detected"}


# ------------------------------------------------------------------
# Stage 9: Verification
# ------------------------------------------------------------------

async def verify_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    gaps = state.get("gaps", [])

    from science_ai.agents.verification import VerificationAgent

    verifier = VerificationAgent(
        deps.llm, session_id=sid, search_service=deps.search,
    )
    verification_results = await verifier.run(gaps=gaps)

    verified_gaps = [
        v for v in verification_results if v.get("status") == "verified_gap"
    ]

    logger.info(
        "[graph] verify_node: %d/%d verified",
        len(verified_gaps), len(verification_results),
    )
    return {
        "verification_results": verification_results,
        "verified_gaps": verified_gaps,
        "status": "verified",
    }


# ------------------------------------------------------------------
# Stage 10: Idea Generation
# ------------------------------------------------------------------

async def idea_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    verified_gaps = state.get("verified_gaps", [])
    knowledge_objects = state.get("knowledge_objects", [])

    if not verified_gaps:
        return {"ideas": [], "status": "no_gaps"}

    from science_ai.agents.idea_generator import IdeaGenerator

    idea_gen = IdeaGenerator(deps.llm, session_id=sid)
    ideas = await idea_gen.run(
        verified_gaps=verified_gaps,
        knowledge_objects=knowledge_objects,
        user_background=state.get("user_background", ""),
    )

    logger.info("[graph] idea_node: %d ideas", len(ideas))
    return {"ideas": ideas, "status": "ideas_generated"}


# ------------------------------------------------------------------
# Stage 11: Experiment Planning
# ------------------------------------------------------------------

async def experiment_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    ideas = state.get("ideas", [])
    knowledge_objects = state.get("knowledge_objects", [])

    from science_ai.agents.experiment_planner import ExperimentPlanner

    exp_planner = ExperimentPlanner(deps.llm, session_id=sid)
    experiment_plans: list[dict] = []

    for idea in ideas:
        try:
            plan = await exp_planner.run(
                idea=idea, knowledge_objects=knowledge_objects,
            )
            experiment_plans.append(plan)
        except Exception:
            logger.exception("Failed to plan experiment for idea '%s'", idea.get("title", ""))

    logger.info("[graph] experiment_node: %d plans", len(experiment_plans))
    return {"experiment_plans": experiment_plans, "status": "experiments_planned"}


# ------------------------------------------------------------------
# Stage 12: Report Writing
# ------------------------------------------------------------------

async def report_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]

    from science_ai.agents.report_writer import ReportWriter

    report_writer = ReportWriter(deps.llm, session_id=sid)
    cost_summary = deps.cost_tracker.session_summary(sid)

    try:
        report = await report_writer.run(
            question=state["question"],
            plan=state.get("plan", {}),
            knowledge_objects=state.get("knowledge_objects", []),
            critiques=state.get("critiques", []),
            verified_gaps=state.get("verified_gaps", []),
            ideas=state.get("ideas", []),
            experiment_plans=state.get("experiment_plans", []),
            cost_summary=cost_summary,
        )
    except Exception:
        logger.exception("Failed to generate report")
        report = None

    logger.info("[graph] report_node complete")
    return {"report": report, "status": "report_written"}


# ------------------------------------------------------------------
# Stage 13: Zotero Export
# ------------------------------------------------------------------

async def zotero_export_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]

    if not deps.zotero_client:
        return {"status": "completed", "cost_summary": _build_cost_summary(deps, sid)}

    try:
        key = deps.zotero_client.export_session(
            session_id=sid,
            question=state["question"],
            triage_results=state.get("triage_results", []),
            knowledge_objects=state.get("knowledge_objects", []),
            critiques=state.get("critiques", []),
            verified_gaps=state.get("verified_gaps", []),
            ideas=state.get("ideas", []),
            report=state.get("report"),
            all_papers=[],
        )
        logger.info("[graph] Exported to Zotero collection: %s", key)
        return {
            "zotero_collection_key": key,
            "status": "completed",
            "cost_summary": _build_cost_summary(deps, sid),
        }
    except Exception:
        logger.exception("Failed to export session to Zotero")
        return {"status": "completed", "cost_summary": _build_cost_summary(deps, sid)}


def _build_cost_summary(deps: Any, session_id: str) -> dict:
    return deps.cost_tracker.session_summary(session_id)
