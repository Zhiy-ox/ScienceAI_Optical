"""FastAPI routes for the Science AI research API."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException

from science_ai.api.schemas import (
    CostDetail,
    DetailedCostReport,
    HealthResponse,
    ProviderTestResult,
    ResearchResult,
    SessionCreated,
    SessionListItem,
    SessionStatus,
    SettingsResponse,
    SettingsTestResponse,
    SettingsUpdate,
    StartResearchRequest,
    ZoteroCollection,
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
        request.source,
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


def _mask_key(key: str) -> str:
    """Mask an API key, showing only last 4 chars."""
    if not key:
        return ""
    if len(key) <= 8:
        return "***" + key[-2:]
    return key[:3] + "..." + key[-4:]


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """Return current settings with masked API keys."""
    from science_ai.config import settings
    return SettingsResponse(
        openai_api_key=_mask_key(settings.openai_api_key),
        anthropic_api_key=_mask_key(settings.anthropic_api_key),
        google_api_key=_mask_key(settings.google_api_key),
        zotero_library_id=settings.zotero_library_id,
        zotero_api_key=_mask_key(settings.zotero_api_key),
        zotero_library_type=settings.zotero_library_type,
        cost_budget_usd=settings.cost_budget_usd,
        llm_backend=settings.llm_backend,
    )


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(update: SettingsUpdate):
    """Update settings and persist to .env file."""
    import pathlib
    from science_ai.config import settings

    env_path = pathlib.Path(".env")
    env_lines: dict[str, str] = {}

    # Read existing .env
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_lines[k.strip()] = v.strip()

    # Apply updates
    field_map = {
        "openai_api_key": "OPENAI_API_KEY",
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "google_api_key": "GOOGLE_API_KEY",
        "zotero_library_id": "ZOTERO_LIBRARY_ID",
        "zotero_api_key": "ZOTERO_API_KEY",
        "zotero_library_type": "ZOTERO_LIBRARY_TYPE",
        "cost_budget_usd": "COST_BUDGET_USD",
        "llm_backend": "LLM_BACKEND",
    }

    for field_name, env_name in field_map.items():
        value = getattr(update, field_name, None)
        if value is not None:
            env_lines[env_name] = str(value)
            setattr(settings, field_name, type(getattr(settings, field_name))(value))

    # Write .env
    env_path.write_text(
        "\n".join(f"{k}={v}" for k, v in env_lines.items()) + "\n"
    )

    return SettingsResponse(
        openai_api_key=_mask_key(settings.openai_api_key),
        anthropic_api_key=_mask_key(settings.anthropic_api_key),
        google_api_key=_mask_key(settings.google_api_key),
        zotero_library_id=settings.zotero_library_id,
        zotero_api_key=_mask_key(settings.zotero_api_key),
        zotero_library_type=settings.zotero_library_type,
        cost_budget_usd=settings.cost_budget_usd,
        llm_backend=settings.llm_backend,
    )


@router.post("/settings/test", response_model=SettingsTestResponse)
async def test_settings():
    """Test connectivity for each configured provider."""
    import httpx
    from science_ai.config import settings

    results: list[ProviderTestResult] = []

    # Test OpenAI
    if settings.openai_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                )
                ok = resp.status_code == 200
                results.append(ProviderTestResult(provider="openai", ok=ok, message="Connected" if ok else f"HTTP {resp.status_code}"))
        except Exception as e:
            results.append(ProviderTestResult(provider="openai", ok=False, message=str(e)))
    else:
        results.append(ProviderTestResult(provider="openai", ok=False, message="No API key configured"))

    # Test Anthropic
    if settings.anthropic_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                ok = resp.status_code == 200
                results.append(ProviderTestResult(provider="anthropic", ok=ok, message="Connected" if ok else f"HTTP {resp.status_code}"))
        except Exception as e:
            results.append(ProviderTestResult(provider="anthropic", ok=False, message=str(e)))
    else:
        results.append(ProviderTestResult(provider="anthropic", ok=False, message="No API key configured"))

    # Test Google
    if settings.google_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.google_api_key}",
                )
                ok = resp.status_code == 200
                results.append(ProviderTestResult(provider="google", ok=ok, message="Connected" if ok else f"HTTP {resp.status_code}"))
        except Exception as e:
            results.append(ProviderTestResult(provider="google", ok=False, message=str(e)))
    else:
        results.append(ProviderTestResult(provider="google", ok=False, message="No API key configured"))

    # Test CLI tools (if CLI backend is active)
    if settings.llm_backend == "cli":
        import shutil
        for tool_name, cmd in [("codex", settings.cli_codex_command), ("gemini", settings.cli_gemini_command), ("claude", settings.cli_claude_command)]:
            found = shutil.which(cmd)
            results.append(ProviderTestResult(
                provider=f"cli:{tool_name}",
                ok=found is not None,
                message=f"Found at {found}" if found else f"'{cmd}' not found in PATH",
            ))

    # Test Zotero
    if settings.zotero_library_id and settings.zotero_api_key:
        try:
            from science_ai.services.zotero_client import ZoteroClient
            zot = ZoteroClient(
                library_id=settings.zotero_library_id,
                api_key=settings.zotero_api_key,
                library_type=settings.zotero_library_type,
            )
            items = zot.zot.top(limit=1)
            results.append(ProviderTestResult(provider="zotero", ok=True, message=f"Connected ({len(items)} items accessible)"))
        except Exception as e:
            results.append(ProviderTestResult(provider="zotero", ok=False, message=str(e)))
    else:
        results.append(ProviderTestResult(provider="zotero", ok=False, message="No Zotero credentials configured"))

    return SettingsTestResponse(results=results)


# --- Sessions ---

@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions():
    """List all research sessions."""
    tracker_map = _cost_trackers
    items = []
    for sid, sess in _sessions.items():
        tracker = tracker_map.get(sid)
        cost = tracker.session_total(sid) if tracker else 0.0
        items.append(SessionListItem(
            session_id=sid,
            status=sess["status"],
            question=sess.get("question", ""),
            cost_so_far=round(cost, 4),
        ))
    return items


# --- Zotero ---

@router.get("/zotero/collections", response_model=list[ZoteroCollection])
async def list_zotero_collections():
    """List Zotero collections for the configured library."""
    from science_ai.config import settings
    if not settings.zotero_library_id or not settings.zotero_api_key:
        raise HTTPException(status_code=400, detail="Zotero not configured")

    from science_ai.services.zotero_client import ZoteroClient
    zot = ZoteroClient(
        library_id=settings.zotero_library_id,
        api_key=settings.zotero_api_key,
        library_type=settings.zotero_library_type,
    )
    collections = zot.list_collections()
    return [
        ZoteroCollection(key=c["key"], name=c["name"], num_items=c["num_items"])
        for c in collections
    ]


async def _run_pipeline(
    session_id: str,
    question: str,
    max_papers: int,
    phase: int,
    user_background: str = "",
    source: str = "web",
) -> None:
    """Background task that runs the research pipeline."""
    tracker = _cost_trackers.get(session_id, CostTracker())

    # Use InMemoryGraphStore for Phase 3 (no Neo4j dependency required)
    graph_store = None
    if phase >= 3:
        from science_ai.storage.graph_store import InMemoryGraphStore
        graph_store = InMemoryGraphStore()

    # Set up Zotero client if source includes zotero
    zotero_client = None
    if source in ("zotero", "both"):
        from science_ai.config import settings as cfg
        if cfg.zotero_library_id and cfg.zotero_api_key:
            from science_ai.services.zotero_client import ZoteroClient
            zotero_client = ZoteroClient(
                library_id=cfg.zotero_library_id,
                api_key=cfg.zotero_api_key,
                library_type=cfg.zotero_library_type,
            )

    orchestrator = ResearchOrchestrator(
        cost_tracker=tracker,
        graph_store=graph_store,
        zotero_client=zotero_client,
    )

    try:
        if phase >= 3:
            result = await orchestrator.run_phase3(
                question=question,
                session_id=session_id,
                max_papers_to_read=max_papers,
                user_background=user_background,
                source=source,
            )
        elif phase >= 2:
            result = await orchestrator.run_phase2(
                question=question,
                session_id=session_id,
                max_papers_to_read=max_papers,
                source=source,
            )
        else:
            result = await orchestrator.run_phase1(
                question=question,
                session_id=session_id,
                max_papers_to_read=max_papers,
                source=source,
            )
        _sessions[session_id]["result"] = result
        _sessions[session_id]["status"] = "completed"
    except Exception:
        logger.exception("Pipeline failed for session %s", session_id)
        _sessions[session_id]["status"] = "failed"
        _sessions[session_id]["result"] = {"status": "failed"}
