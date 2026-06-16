"""Node functions for the LangGraph research pipeline.

Each node wraps an existing agent and returns a partial-state dict that
LangGraph merges back into ResearchState via its reducers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from science_ai.orchestrator.feedback import (
    FEASIBILITY_THRESHOLD,
    KEYWORD_NOVELTY_THRESHOLD,
    MAX_LOOP_ITERATIONS,
    VERIFICATION_THRESHOLD,
    keyword_novelty_ratio,
    verification_pass_ratio,
)
from science_ai.orchestrator.graph.deps import get_deps
from science_ai.orchestrator.graph.ids import assign_sequential_ids, stamp_linked_id
from science_ai.orchestrator.graph.state import ResearchState

logger = logging.getLogger(__name__)


def emit_progress(stage: str, msg: str, **extra: Any) -> None:
    """Emit a human-readable progress event to the SSE stream, if streaming.

    Safe no-op when called outside a streaming context (e.g. ainvoke, tests).
    """
    try:
        from langgraph.config import get_stream_writer
        writer = get_stream_writer()
    except Exception:
        return
    if writer is None:
        return
    payload = {"stage": stage, "msg": msg}
    payload.update(extra)
    try:
        writer(payload)
    except Exception:
        pass


# ------------------------------------------------------------------
# Stage 1: Plan
# ------------------------------------------------------------------

async def plan_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    emit_progress("plan", "Generating research plan…")

    from science_ai.agents.query_planner import QueryPlanner

    planner = QueryPlanner(deps.llm, session_id=sid)
    plan = await planner.run(question=state["question"])

    n_queries = len(plan.get("search_queries", []))
    emit_progress("plan", f"Plan ready — {n_queries} search queries")
    logger.info("[graph] plan_node complete for %s", sid)
    return {"plan": plan, "status": "planned"}


# ------------------------------------------------------------------
# Human-in-the-loop gates (Stage 6)
#
# A gate node pauses the graph via interrupt() when its gate is enabled in
# state["hitl_gates"]. The interrupt payload is surfaced to the client (via
# SSE / status); the client resumes with Command(resume={"action": ...}).
# Decision shape: {"action": "approve"|"edit"|"reject", "plan"/"verified_gaps": <edited>}
# When the gate is disabled, the node is a transparent passthrough.
# ------------------------------------------------------------------

async def plan_gate_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Optional approval gate after planning, before searching."""
    if "plan" not in state.get("hitl_gates", []):
        return {}  # passthrough

    from langgraph.types import interrupt

    decision = interrupt({
        "type": "approve_plan",
        "message": "Review the research plan before searching.",
        "plan": state.get("plan"),
    }) or {}

    action = decision.get("action", "approve")
    if action == "reject":
        emit_progress("plan_gate", "Plan rejected — stopping")
        return {"status": "rejected"}
    if action == "edit" and decision.get("plan"):
        emit_progress("plan_gate", "Plan edited and approved")
        return {"plan": decision["plan"], "status": "plan_approved"}
    emit_progress("plan_gate", "Plan approved")
    return {"status": "plan_approved"}


async def gaps_gate_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Optional approval gate after verification, before idea generation."""
    if "gaps" not in state.get("hitl_gates", []):
        return {}  # passthrough

    from langgraph.types import interrupt

    decision = interrupt({
        "type": "approve_gaps",
        "message": "Review verified gaps before generating ideas.",
        "verified_gaps": state.get("verified_gaps", []),
    }) or {}

    action = decision.get("action", "approve")
    if action == "reject":
        emit_progress("gaps_gate", "Gaps rejected — stopping")
        return {"status": "rejected", "verified_gaps": []}
    if action == "edit" and decision.get("verified_gaps") is not None:
        emit_progress("gaps_gate", "Gaps edited and approved")
        return {"verified_gaps": decision["verified_gaps"], "status": "gaps_approved"}
    emit_progress("gaps_gate", "Gaps approved")
    return {"status": "gaps_approved"}


# ------------------------------------------------------------------
# Stage 2: Search
# ------------------------------------------------------------------

async def search_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Search for papers.

    Re-entrant: on a refinement pass (``refine_keywords`` set), searches only the
    new keywords; otherwise runs the plan's queries. Only papers not already in
    ``all_papers`` are returned, so the ``operator.add`` reducer never duplicates.
    """
    deps = get_deps(config)
    plan = state.get("plan", {})
    source = state.get("source", "web")
    question = state["question"]
    emit_progress("search", "Searching for papers…")

    existing = state.get("all_papers", [])
    seen_ids: set[str] = {p["paper_id"] for p in existing}
    seen_titles: set[str] = {p.get("title", "").lower().strip() for p in existing}
    refine_keywords = state.get("refine_keywords", [])

    new_papers: list[Any] = []

    def _add(papers: list[Any]) -> None:
        for p in papers:
            if p.paper_id in seen_ids:
                continue
            title_key = p.title.lower().strip()
            if title_key in seen_titles:
                continue
            seen_ids.add(p.paper_id)
            seen_titles.add(title_key)
            new_papers.append(p)

    if refine_keywords:
        # --- Refinement pass: search the newly-discovered keywords ---
        for kw in refine_keywords[:5]:
            try:
                _add(await deps.search.search(kw, limit=30))
            except Exception:
                logger.exception("Refinement search failed for keyword: %s", kw)
    else:
        # --- Initial pass: run the plan's search queries (+ optional Zotero) ---
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
                    _add(await deps.search.search(
                        query_str, sources=[src], limit=50, year_range=year_range,
                    ))
                except Exception:
                    logger.exception("Search failed for query: %s", query_str)

        if source in ("zotero", "both") and deps.zotero_client:
            try:
                _add(deps.zotero_client.search(question, limit=50))
            except Exception:
                logger.exception("Zotero search failed")

    paper_dicts = [
        {"paper_id": p.paper_id, "title": p.title, "abstract": p.abstract}
        for p in new_papers
    ]
    total = len(existing) + len(paper_dicts)

    emit_progress("search", f"Found {total} papers ({len(paper_dicts)} new)", count=total)
    logger.info(
        "[graph] search_node: +%d new papers (%d total)%s",
        len(paper_dicts), total, " [refinement]" if refine_keywords else "",
    )
    return {
        "all_papers": paper_dicts,
        "papers_found": total,
        "refine_keywords": [],  # consume so the reducer state is clean for the next pass
        "status": "searched",
    }


# ------------------------------------------------------------------
# Stage 3: Triage
# ------------------------------------------------------------------

async def triage_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Triage papers. Re-entrant: only triages papers not already triaged."""
    deps = get_deps(config)
    sid = state["session_id"]
    all_papers = state.get("all_papers", [])

    if not all_papers:
        return {"triage_results": [], "status": "no_papers_found"}

    already = {r.get("paper_id") for r in state.get("triage_results", [])}
    to_triage = [p for p in all_papers if p["paper_id"] not in already]

    if not to_triage:
        logger.info("[graph] triage_node: nothing new to triage")
        return {"status": "triaged"}

    emit_progress("triage", f"Triaging {len(to_triage)} papers…")

    from science_ai.agents.paper_triage import PaperTriage

    triage_agent = PaperTriage(deps.llm, session_id=sid)
    triage_results = await triage_agent.run(
        question=state["question"], papers=to_triage,
    )

    must_read = sum(1 for r in triage_results if r.get("priority") == "must_read")
    emit_progress("triage", f"Triaged — {must_read} must-read", count=len(triage_results))
    logger.info("[graph] triage_node: %d new results", len(triage_results))
    return {"triage_results": triage_results, "status": "triaged"}


# ------------------------------------------------------------------
# Stage 4: Select papers for deep reading
# ------------------------------------------------------------------

async def select_papers_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Pick the next batch of papers to deep-read.

    Excludes already-read papers. On a refinement pass the total budget doubles
    (matches the legacy ``max_papers * 2`` ceiling).
    """
    triage_results = state.get("triage_results", [])
    max_papers = state.get("max_papers", 15)
    already_read = {ko.get("paper_id") for ko in state.get("knowledge_objects", [])}
    is_refinement = state.get("search_refine_count", 0) > 0

    cap = max_papers * 2 if is_refinement else max_papers
    remaining = max(0, cap - len(already_read))

    must_read = [
        r for r in triage_results
        if r.get("priority") == "must_read" and r.get("paper_id") not in already_read
    ]
    worth_reading = [
        r for r in triage_results
        if r.get("priority") == "worth_reading" and r.get("paper_id") not in already_read
    ]

    papers_to_read = must_read[:remaining]
    leftover = remaining - len(papers_to_read)
    if leftover > 0:
        papers_to_read.extend(worth_reading[:leftover])

    emit_progress("select", f"Selected {len(papers_to_read)} papers to deep-read")
    logger.info("[graph] select_papers_node: %d selected", len(papers_to_read))
    return {"papers_to_read": papers_to_read, "status": "selected"}


# ------------------------------------------------------------------
# Stage 5: Deep Read — parallel fan-out via Send
# ------------------------------------------------------------------

def deep_read_dispatch(state: ResearchState) -> list:
    """Fan-out: emit one Send per paper to deep-read in parallel.

    Returns a list of ``Send("deep_read_one", {...})`` commands. LangGraph
    runs them concurrently; results reduce into ``knowledge_objects`` via
    the ``operator.add`` reducer.
    """
    from langgraph.types import Send

    papers_to_read = state.get("papers_to_read", [])
    all_papers = state.get("all_papers", [])
    paper_lookup = {p["paper_id"]: p for p in all_papers}
    already_read = {ko.get("paper_id") for ko in state.get("knowledge_objects", [])}

    sends = []
    for triage in papers_to_read:
        pid = triage.get("paper_id", "")
        if pid in already_read:
            continue
        paper = paper_lookup.get(pid)
        if not paper:
            continue
        priority = "high" if triage.get("priority") == "must_read" else "medium"
        sends.append(Send("deep_read_one", {
            "session_id": state["session_id"],
            "paper_id": pid,
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", ""),
            "priority": priority,
        }))

    if not sends:
        logger.info("[graph] deep_read_dispatch: nothing to read, skipping to refine_decision")
        return [Send("refine_decision", state)]

    logger.info("[graph] deep_read_dispatch: %d papers to fan-out", len(sends))
    return sends


async def deep_read_one(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    """Read a single paper. Runs concurrently, capped by Deps.fanout_semaphore."""
    deps = get_deps(config)
    sid = state["session_id"]
    pid = state["paper_id"]

    from science_ai.agents.deep_reader import DeepReader

    async with deps.fanout_semaphore:
        reader = DeepReader(deps.llm, session_id=sid)
        emit_progress("deep_read", f"Reading: {state.get('title', pid)[:60]}")
        try:
            ko = await reader.run(
                paper_text=state.get("abstract", ""),
                paper_id=pid,
                title=state.get("title", ""),
                priority=state.get("priority", "medium"),
            )
            logger.info("[graph] deep_read_one: %s done", pid)
            return {"knowledge_objects": [ko]}
        except Exception:
            logger.exception("Failed to deep-read paper %s", pid)
            return {"knowledge_objects": []}


# ------------------------------------------------------------------
# Stage 6: Critique — parallel fan-out via Send
# ------------------------------------------------------------------

def critique_dispatch(state: ResearchState) -> list:
    """Fan-out: emit one Send per KO to critique in parallel.

    If no KOs need critiquing, returns a Send to ``gap_detect`` to avoid
    a dead-end in the graph.
    """
    from langgraph.types import Send

    knowledge_objects = state.get("knowledge_objects", [])
    already_critiqued = {c.get("paper_id") for c in state.get("critiques", [])}

    sends = []
    for ko in knowledge_objects:
        pid = ko.get("paper_id", "")
        if pid in already_critiqued:
            continue
        sends.append(Send("critique_one", {
            "session_id": state["session_id"],
            "knowledge_obj": ko,
        }))

    if not sends:
        logger.info("[graph] critique_dispatch: nothing to critique, skipping to gap_detect")
        return [Send("gap_detect", state)]

    logger.info("[graph] critique_dispatch: %d KOs to fan-out", len(sends))
    return sends


async def critique_one(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    """Critique a single knowledge object. Runs concurrently."""
    deps = get_deps(config)
    sid = state["session_id"]
    ko = state["knowledge_obj"]

    from science_ai.agents.critique import CritiqueAgent

    async with deps.fanout_semaphore:
        emit_progress("critique", f"Critiquing paper {ko.get('paper_id', '')}")
        critique_agent = CritiqueAgent(deps.llm, session_id=sid)
        try:
            critique = await critique_agent.run(knowledge_obj=ko)
            logger.info("[graph] critique_one: %s done", ko.get("paper_id"))
            return {"critiques": [critique]}
        except Exception:
            logger.exception("Failed to critique paper %s", ko.get("paper_id"))
            return {"critiques": []}


# ------------------------------------------------------------------
# Stage 7: Index (vector + graph stores)
# ------------------------------------------------------------------

async def index_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    knowledge_objects = state.get("knowledge_objects", [])

    if deps.vector_store and deps.embedding_fn:
        # Embedding + upsert per object is independent I/O — run concurrently.
        results = await asyncio.gather(
            *(
                deps.vector_store.index_knowledge_object(ko, deps.embedding_fn)
                for ko in knowledge_objects
            ),
            return_exceptions=True,
        )
        for ko, res in zip(knowledge_objects, results):
            if isinstance(res, BaseException):
                logger.error(
                    "Failed to index paper %s", ko.get("paper_id"), exc_info=res,
                )

    if deps.graph_store:
        for ko in knowledge_objects:
            try:
                await deps.graph_store.ingest_knowledge_object(ko)
            except Exception:
                logger.exception("Failed to ingest paper %s into graph", ko.get("paper_id"))

    emit_progress("index", f"Indexed {len(knowledge_objects)} knowledge objects")
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

    emit_progress("gap_detect", "Detecting research gaps…")

    from science_ai.agents.gap_detector import GapDetector

    gap_detector = GapDetector(
        deps.llm, session_id=sid,
        embedding_fn=deps.embedding_fn, graph_store=deps.graph_store,
    )

    # On a retry pass (Feedback Loop 2), feed prior verification failures as context.
    run_kwargs: dict[str, Any] = {
        "knowledge_objects": knowledge_objects,
        "critiques": critiques,
    }
    previous_failures = state.get("previous_failures")
    if previous_failures:
        run_kwargs["previous_failures"] = previous_failures

    gaps = await gap_detector.run(**run_kwargs)

    # Stamp canonical IDs so verification / ideation can reference gaps reliably,
    # regardless of the placeholder IDs the LLM emits.
    gaps = assign_sequential_ids(gaps, "GAP")

    emit_progress("gap_detect", f"Found {len(gaps)} candidate gaps", count=len(gaps))
    logger.info("[graph] gap_detect_node: %d gaps", len(gaps))
    return {"gaps": gaps, "status": "gaps_detected"}


# ------------------------------------------------------------------
# Stage 9: Verification
# ------------------------------------------------------------------

async def verify_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    gaps = state.get("gaps", [])

    emit_progress("verify", f"Verifying novelty of {len(gaps)} gaps…")

    from science_ai.agents.verification import VerificationAgent

    verifier = VerificationAgent(
        deps.llm, session_id=sid, search_service=deps.search,
    )
    verification_results = await verifier.run(gaps=gaps)

    # The verifier returns one result per gap in order; re-stamp the canonical
    # gap_id and carry the gap's description so verified_gaps stay linkable to
    # their source gap during ideation (the LLM's own gap_id is unreliable).
    # Positional stamping is only safe when the counts line up — if the agent
    # dropped or added results, re-stamping would mislink every result after
    # the mismatch, so fall back to matching on the agent-provided gap_id.
    if len(verification_results) == len(gaps):
        for gap, result in zip(gaps, verification_results):
            if isinstance(result, dict):
                stamp_linked_id(result, gap, "gap_id")
                result.setdefault("description", gap.get("description", ""))
    else:
        logger.warning(
            "verify_node: %d results for %d gaps — keeping agent-provided gap_ids",
            len(verification_results), len(gaps),
        )
        gaps_by_id = {g.get("gap_id"): g for g in gaps if isinstance(g, dict)}
        for result in verification_results:
            if isinstance(result, dict):
                gap = gaps_by_id.get(result.get("gap_id"))
                if gap:
                    result.setdefault("description", gap.get("description", ""))

    verified_gaps = [
        v for v in verification_results if v.get("status") == "verified_gap"
    ]

    emit_progress(
        "verify", f"{len(verified_gaps)} gaps verified as novel",
        count=len(verified_gaps),
    )
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

def _top_candidate_gaps(gaps: list[dict], limit: int = 5) -> list[dict]:
    """Rank candidate gaps for fallback ideation (highest confidence first)."""
    impact_rank = {"high": 3, "medium": 2, "low": 1}

    def score(gap: dict) -> float:
        conf = gap.get("confidence", 0.5)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.5
        impact = impact_rank.get(str(gap.get("potential_impact", "medium")).lower(), 2)
        return conf * impact

    return sorted(gaps, key=score, reverse=True)[:limit]


async def idea_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]
    verified_gaps = state.get("verified_gaps", [])
    knowledge_objects = state.get("knowledge_objects", [])

    gaps_for_ideation = verified_gaps
    if not gaps_for_ideation:
        # The verifier marked nothing as strictly novel — common when related
        # work already exists (gaps come back "active_area"/"emerging"). Rather
        # than abandoning Phase 3, ideate on the strongest *candidate* gaps so
        # the run still yields ideas, experiments, and a report.
        candidate_gaps = state.get("gaps", [])
        if not candidate_gaps:
            logger.info("[graph] idea_node: no gaps at all, skipping ideation")
            return {"ideas": [], "status": "no_gaps"}
        gaps_for_ideation = _top_candidate_gaps(candidate_gaps)
        emit_progress(
            "idea",
            f"No strictly-novel gaps; ideating on {len(gaps_for_ideation)} "
            "top candidates…",
        )
        logger.info(
            "[graph] idea_node: 0 verified gaps → falling back to %d candidates",
            len(gaps_for_ideation),
        )
    else:
        emit_progress("idea", f"Generating ideas from {len(verified_gaps)} gaps…")

    from science_ai.agents.idea_generator import IdeaGenerator

    # On a regeneration pass (Feedback Loop 3), append the feasibility constraint.
    user_background = state.get("user_background", "")
    regen_constraint = state.get("regen_constraint", "")
    if regen_constraint:
        user_background = f"{user_background}\n{regen_constraint}".strip()

    idea_gen = IdeaGenerator(deps.llm, session_id=sid)
    ideas = await idea_gen.run(
        verified_gaps=gaps_for_ideation,
        knowledge_objects=knowledge_objects,
        user_background=user_background,
    )

    # Stamp canonical idea IDs so experiment plans can reference them reliably.
    ideas = assign_sequential_ids(ideas, "IDEA")

    emit_progress("idea", f"Generated {len(ideas)} research ideas", count=len(ideas))
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

    emit_progress("experiment", f"Planning experiments for {len(ideas)} ideas…")

    from science_ai.agents.experiment_planner import ExperimentPlanner

    exp_planner = ExperimentPlanner(deps.llm, session_id=sid)

    # Plans are independent per idea — run them concurrently, bounded by the
    # same semaphore that limits the deep-read/critique fan-out.
    async def plan_one(idea: dict) -> dict | None:
        async with deps.fanout_semaphore:
            try:
                plan = await exp_planner.run(
                    idea=idea, knowledge_objects=knowledge_objects,
                )
            except Exception:
                logger.exception(
                    "Failed to plan experiment for idea '%s'", idea.get("title", ""),
                )
                return None
        # Link the plan back to its source idea's canonical ID.
        if isinstance(plan, dict):
            stamp_linked_id(plan, idea, "idea_id")
        return plan

    results = await asyncio.gather(*(plan_one(idea) for idea in ideas))
    experiment_plans: list[dict] = [p for p in results if p is not None]

    emit_progress("experiment", f"Planned {len(experiment_plans)} experiments")
    logger.info("[graph] experiment_node: %d plans", len(experiment_plans))
    return {"experiment_plans": experiment_plans, "status": "experiments_planned"}


# ------------------------------------------------------------------
# Stage 12: Report Writing
# ------------------------------------------------------------------

async def report_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    deps = get_deps(config)
    sid = state["session_id"]

    emit_progress("report", "Writing final report…")

    from science_ai.agents.report_writer import ReportWriter

    report_writer = ReportWriter(deps.llm, session_id=sid)
    cost_summary = deps.cost_tracker.session_summary(sid)

    report: dict[str, Any] | None = None
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

    # Never leave the user empty-handed: if the writer failed or returned an
    # unusable shape, synthesize a structured report from what the pipeline
    # already produced.
    if not isinstance(report, dict) or not report.get("sections"):
        report = _fallback_report(state, cost_summary)
        logger.info("[graph] report_node: used fallback report synthesis")

    emit_progress("report", "Report complete")
    logger.info("[graph] report_node complete")
    return {"report": report, "status": "report_written"}


def _fallback_report(state: ResearchState, cost_summary: dict) -> dict[str, Any]:
    """Build a minimal, honest report from pipeline state.

    Used when the LLM report writer fails (timeout, malformed JSON) or returns
    an empty report — so Phase 3 always ends with something readable.
    """
    question = state.get("question", "")
    kos = state.get("knowledge_objects", [])
    verified_gaps = state.get("verified_gaps", [])
    gaps = verified_gaps or state.get("gaps", [])
    ideas = state.get("ideas", [])
    plans = state.get("experiment_plans", [])

    def _bullets(items: list[dict], *fields: str) -> str:
        lines = []
        for it in items:
            text = next((str(it[f]) for f in fields if it.get(f)), None)
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines) or "_None recorded._"

    sections = [
        {
            "heading": "Executive Summary",
            "content": (
                f"Analysis of {len(kos)} papers for the question "
                f"“{question}” produced {len(gaps)} research gap(s), "
                f"{len(ideas)} idea(s), and {len(plans)} experiment plan(s). "
                "This summary was assembled directly from pipeline outputs "
                "because the report writer did not return a full draft."
            ),
        },
        {
            "heading": "Papers Analyzed",
            "content": _bullets(kos, "title", "paper_id"),
        },
        {
            "heading": "Research Gaps",
            "content": _bullets(gaps, "description", "gap_id"),
        },
        {
            "heading": "Research Ideas",
            "content": _bullets(ideas, "title", "description", "idea_id"),
        },
    ]
    return {
        "title": f"Research Report: {question}" if question else "Research Report",
        "sections": sections,
        "citations": [
            {"paper_id": ko.get("paper_id"), "title": ko.get("title")}
            for ko in kos if ko.get("paper_id")
        ],
        "cost_summary": cost_summary,
        "fallback": True,
    }


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


# ------------------------------------------------------------------
# Feedback-loop decision nodes (Stage 2)
#
# Each decision node *only* inspects state and sets transient control fields.
# The matching router in edges.py reads those fields to pick the next node.
# Loop counters live in state (checkpointed), bounded by MAX_LOOP_ITERATIONS.
# ------------------------------------------------------------------

# Keywords for extracting discovered terms from knowledge objects (Loop 1).

def _discovered_keywords(knowledge_objects: list[dict]) -> list[str]:
    discovered: list[str] = []
    for ko in knowledge_objects:
        method = ko.get("method", {})
        if method.get("key_components"):
            discovered.extend(method["key_components"])
        problem = ko.get("research_problem", {})
        statement = problem.get("statement")
        if statement and len(statement.split()) >= 2:
            discovered.append(statement)
    return discovered


async def refine_decision_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Loop 1: decide whether to refine the search with newly-discovered keywords."""
    plan = state.get("plan", {})
    knowledge_objects = state.get("knowledge_objects", [])
    count = state.get("search_refine_count", 0)

    original_keywords: list[str] = []
    for sq in plan.get("search_queries", []):
        original_keywords.extend(sq.get("keywords", []))
    discovered = _discovered_keywords(knowledge_objects)
    ratio = keyword_novelty_ratio(original_keywords, discovered)

    if count < MAX_LOOP_ITERATIONS and discovered and ratio > KEYWORD_NOVELTY_THRESHOLD:
        original_set = {k.lower() for k in original_keywords}
        new_keywords = [k for k in discovered if k.lower() not in original_set]
        logger.info(
            "[graph] refine_decision: %.0f%% new keywords → refining (iter %d)",
            ratio * 100, count + 1,
        )
        return {
            "refine_keywords": new_keywords[:5],
            "search_refine_count": count + 1,
            "status": "refining_search",
        }

    return {"refine_keywords": []}


async def gap_retry_decision_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Loop 2: decide whether to re-run gap detection after weak verification."""
    verification_results = state.get("verification_results", [])
    count = state.get("gap_retry_count", 0)
    ratio = verification_pass_ratio(verification_results)

    if (
        count < MAX_LOOP_ITERATIONS
        and verification_results
        and ratio < VERIFICATION_THRESHOLD
    ):
        failed = [
            v for v in verification_results if v.get("status") != "verified_gap"
        ]
        logger.info(
            "[graph] gap_retry_decision: only %.0f%% verified → retrying (iter %d)",
            ratio * 100, count + 1,
        )
        return {
            "previous_failures": failed,
            "gap_retry_count": count + 1,
            "gap_retry_pending": True,
            "status": "retrying_gaps",
        }

    return {"gap_retry_pending": False, "previous_failures": []}


async def idea_regen_decision_node(state: ResearchState, config: RunnableConfig) -> dict[str, Any]:
    """Loop 3: decide whether to regenerate ideas whose experiments are infeasible."""
    experiment_plans = state.get("experiment_plans", [])
    count = state.get("idea_regen_count", 0)

    if not experiment_plans:
        return {"idea_regen_pending": False}

    min_feasibility = min(
        (p.get("feasibility_score", 0.5) for p in experiment_plans), default=1.0
    )

    if count < MAX_LOOP_ITERATIONS and min_feasibility < FEASIBILITY_THRESHOLD:
        # Collect risks from the infeasible plans to constrain regeneration.
        risks: list[str] = []
        for p in experiment_plans:
            if p.get("feasibility_score", 0.5) < FEASIBILITY_THRESHOLD:
                plan_risks = p.get("experiment_plan", {}).get("risks", [])
                if isinstance(plan_risks, list):
                    risks.extend(str(r) for r in plan_risks)
        constraint = (
            "Constraint: previous ideas were infeasible due to: "
            + "; ".join(risks[:5])
        )
        logger.info(
            "[graph] idea_regen_decision: feasibility=%.2f → regenerating (iter %d)",
            min_feasibility, count + 1,
        )
        return {
            "regen_constraint": constraint,
            "idea_regen_count": count + 1,
            "idea_regen_pending": True,
            "status": "regenerating_ideas",
        }

    return {"idea_regen_pending": False, "regen_constraint": ""}


def _build_cost_summary(deps: Any, session_id: str) -> dict:
    return deps.cost_tracker.session_summary(session_id)
