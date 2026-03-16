"""FastAPI routes for the Science AI research API."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException

from science_ai.api.schemas import (
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

# In-memory session store (Phase 1 — will move to Redis/DB later)
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
        "result": None,
    }
    _cost_trackers[session_id] = CostTracker()

    background_tasks.add_task(
        _run_pipeline, session_id, request.question, request.max_papers
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
        cost_summary=result.get("cost_summary"),
    )


async def _run_pipeline(session_id: str, question: str, max_papers: int) -> None:
    """Background task that runs the full Phase 1 pipeline."""
    tracker = _cost_trackers.get(session_id, CostTracker())
    orchestrator = ResearchOrchestrator(cost_tracker=tracker)

    try:
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
