"""FastAPI routes for the Science AI research API."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException

from science_ai.api.schemas import (
    CostDetail,
    DetailedCostReport,
    HealthResponse,
    ResearchResult,
    SessionCreated,
    SessionStatus,
    StartResearchRequest,
)
from science_ai.cost.tracker import CostTracker
from science_ai.orchestrator.orchestrator import ResearchOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory session store (will move to Redis/DB later)
_sessions: dict[str, dict] = {}
_cost_trackers: dict[str, CostTracker] = {}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse()


@router.post("/research/start", response_model=SessionCreated)
async def start_research(
    request: StartResearchRequest,
    background_tasks: BackgroundTasks,
):
    """Start a new research session. The pipeline runs in the background."""
    session_id = str(uuid.uuid4())

    _sessions[session_id] = {
        "status": "running",
        "question": request.question,
        "phase": request.phase,
        "result": None,
    }
    _cost_trackers[session_id] = CostTracker()

    background_tasks.add_task(
        _run_pipeline,
        session_id,
        request.question,
        request.max_papers,
        request.phase,
        request.user_background,
    )

    return SessionCreated(session_id=session_id)


@router.get("/research/{session_id}/status", response_model=SessionStatus)
async def get_session_status(session_id: str):
    """Check the status of a research session."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    tracker = _cost_trackers.get(session_id)
    cost = tracker.session_total(session_id) if tracker else 0.0

    return SessionStatus(
        session_id=session_id,
        status=session["status"],
        cost_so_far=round(cost, 4),
    )


@router.get("/research/{session_id}/results", response_model=ResearchResult)
async def get_session_results(session_id: str):
    """Get the results of a completed research session."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session["status"] == "running":
        raise HTTPException(status_code=202, detail="Pipeline still running")

    result = session.get("result", {})
    if not result:
        raise HTTPException(status_code=500, detail="Pipeline failed with no result")

    return ResearchResult(
        session_id=session_id,
        status=result.get("status", "unknown"),
        plan=result.get("plan"),
        papers_found=result.get("papers_found", 0),
        triage_results=result.get("triage_results", []),
        knowledge_objects=result.get("knowledge_objects", []),
        critiques=result.get("critiques", []),
        gaps=result.get("gaps", []),
        verified_gaps=result.get("verified_gaps", []),
        ideas=result.get("ideas", []),
        experiment_plans=result.get("experiment_plans", []),
        report=result.get("report"),
        cost_summary=result.get("cost_summary"),
    )


@router.get("/research/{session_id}/cost", response_model=DetailedCostReport)
async def get_session_cost(session_id: str):
    """Get detailed cost report for a research session."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    tracker = _cost_trackers.get(session_id)
    if not tracker:
        raise HTTPException(status_code=404, detail="No cost data for session")

    records = tracker.all_records_for_session(session_id)
    summary = tracker.session_summary(session_id)

    # Group costs by agent
    by_agent: dict[str, float] = {}
    total_cached_tokens = 0
    for r in records:
        by_agent[r["agent"]] = by_agent.get(r["agent"], 0.0) + r["cost_usd"]
        total_cached_tokens += r.get("cached_tokens", 0)

    # Estimate cache savings (cached tokens charged at ~10% of input rate)
    # Savings = cached_tokens * (full_rate - cached_rate) / 1M
    cache_savings = 0.0
    for r in records:
        from science_ai.config import MODEL_PRICING
        pricing = MODEL_PRICING.get(r["model"], {})
        if pricing and r.get("cached_tokens", 0) > 0:
            full_rate = pricing.get("input_per_m", 0)
            cached_rate = pricing.get("cached_input_per_m", 0)
            savings = (r["cached_tokens"] / 1_000_000) * (full_rate - cached_rate)
            cache_savings += savings

    calls = [
        CostDetail(
            call_id=r["call_id"],
            agent=r["agent"],
            model=r["model"],
            reasoning_effort=r["reasoning_effort"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            cached_tokens=r["cached_tokens"],
            cost_usd=r["cost_usd"],
            timestamp=r["timestamp"],
        )
        for r in records
    ]

    return DetailedCostReport(
        session_id=session_id,
        total_usd=summary["total_usd"],
        by_model=summary["by_model"],
        by_agent={k: round(v, 4) for k, v in by_agent.items()},
        call_count=summary["call_count"],
        cache_savings_estimate_usd=round(cache_savings, 4),
        calls=calls,
    )


async def _run_pipeline(
    session_id: str,
    question: str,
    max_papers: int,
    phase: int,
    user_background: str = "",
) -> None:
    """Background task that runs the research pipeline."""
    tracker = _cost_trackers.get(session_id, CostTracker())

    # Use InMemoryGraphStore for Phase 3 (no Neo4j dependency required)
    graph_store = None
    if phase >= 3:
        from science_ai.storage.graph_store import InMemoryGraphStore
        graph_store = InMemoryGraphStore()

    orchestrator = ResearchOrchestrator(
        cost_tracker=tracker,
        graph_store=graph_store,
    )

    try:
        if phase >= 3:
            result = await orchestrator.run_phase3(
                question=question,
                session_id=session_id,
                max_papers_to_read=max_papers,
                user_background=user_background,
            )
        elif phase >= 2:
            result = await orchestrator.run_phase2(
                question=question,
                session_id=session_id,
                max_papers_to_read=max_papers,
            )
        else:
            result = await orchestrator.run_phase1(
                question=question,
                session_id=session_id,
                max_papers_to_read=max_papers,
            )
        _sessions[session_id]["result"] = result
        _sessions[session_id]["status"] = "completed"
    except Exception:
        logger.exception("Pipeline failed for session %s", session_id)
        _sessions[session_id]["status"] = "failed"
        _sessions[session_id]["result"] = {"status": "failed"}
