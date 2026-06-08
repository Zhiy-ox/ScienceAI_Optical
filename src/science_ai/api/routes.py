"""FastAPI routes for the Science AI research API."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from science_ai.api.schemas import (
    CostDetail,
    DetailedCostReport,
    HealthResponse,
    ProviderTestResult,
    ResearchResult,
    ResumeRequest,
    SessionCreated,
    SessionListItem,
    SessionStatus,
    SettingsResponse,
    SettingsTestResponse,
    SettingsUpdate,
    StartResearchRequest,
    ZoteroCollection,
)
from science_ai.config import MODEL_PRICING
from science_ai.cost.tracker import CostTracker
from science_ai.storage.database import async_session_factory
from science_ai.storage.session_repo import SessionRepository

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory session store — lightweight registry. Only tracks question/phase/
# running status (and live HITL/stream overlay) for active sessions; completed
# session data is read from the checkpointer / durable registry.
_sessions: dict[str, dict] = {}
_cost_trackers: dict[str, CostTracker] = {}

# Shared GraphRunner singleton (lazy-initialized, long-lived).
_graph_runner: Any = None

# Shared, lazily-connected semantic-search resources (Qdrant + embeddings).
_vector_store: Any = None
_embedding_service: Any = None
_vector_lock = asyncio.Lock()

# Durable session registry (Postgres). Source of truth for session metadata and
# final results; survives restarts and is queryable for the /sessions list. The
# in-memory _sessions dict above is a live overlay for active-run liveness
# (HITL interrupt payloads, streaming status) that the registry does not track.
_session_repo = SessionRepository(async_session_factory)


async def _get_graph_runner():
    """Return or create the shared GraphRunner with its checkpointer."""
    global _graph_runner
    if _graph_runner is not None:
        return _graph_runner

    from science_ai.orchestrator.graph.checkpointer import get_checkpointer
    from science_ai.orchestrator.graph.runner import GraphRunner

    checkpointer = await get_checkpointer()
    _graph_runner = GraphRunner(checkpointer=checkpointer)
    return _graph_runner


async def _get_vector_resources(cfg):
    """Lazily build a shared, connected Qdrant store + async embedding fn.

    Returns ``(vector_store, embedding_fn)`` when both Qdrant and an OpenAI key
    are configured and the connection succeeds; otherwise ``(None, None)`` — the
    graph then runs without semantic indexing (the index_node and gap detector
    treat these as optional). Built once and reused across sessions.
    """
    global _vector_store, _embedding_service
    if not (cfg.qdrant_url and cfg.openai_api_key):
        return None, None
    if _vector_store is not None:
        return _vector_store, _embedding_service.embed_single

    async with _vector_lock:
        if _vector_store is None:
            try:
                from science_ai.services.embedding import EmbeddingService
                from science_ai.storage.vector_store import VectorStore

                vs = VectorStore()
                await vs.connect()
                _vector_store = vs
                _embedding_service = EmbeddingService()
                logger.info("Connected Qdrant vector store for semantic indexing")
            except Exception:
                logger.warning(
                    "Vector store unavailable; continuing without semantic indexing",
                    exc_info=True,
                )
                return None, None
    return _vector_store, _embedding_service.embed_single


async def close_vector_resources() -> None:
    """Dispose the shared vector store connection (called on shutdown)."""
    global _vector_store, _embedding_service
    if _vector_store is not None:
        try:
            await _vector_store.close()
        except Exception:
            logger.warning("Error closing vector store", exc_info=True)
    _vector_store = None
    _embedding_service = None


async def _persist_status(session_id: str, status: str) -> None:
    """Best-effort status write to the durable registry (never raises)."""
    try:
        await _session_repo.update_status(session_id, status)
    except Exception:
        logger.warning("Could not persist status=%s for %s", status, session_id, exc_info=True)


async def _persist_result(session_id: str, result: dict, tracker: CostTracker | None) -> None:
    """Best-effort final-result write to the durable registry (never raises)."""
    records = tracker.all_records_for_session(session_id) if tracker else []
    try:
        await _session_repo.update_result(session_id, result, records)
    except Exception:
        logger.warning("Could not persist result for %s", session_id, exc_info=True)


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

    # Defer execution to the SSE endpoint when streaming is requested.
    deferred = request.stream

    _sessions[session_id] = {
        "status": "created" if deferred else "running",
        "question": request.question,
        "phase": request.phase,
        "max_papers": request.max_papers,
        "user_background": request.user_background,
        "source": request.source,
        "hitl_gates": request.hitl_gates,
        "interrupt": None,
        "result": None,
    }
    _cost_trackers[session_id] = CostTracker()

    # Persist to the durable registry so the session is queryable across
    # restarts. Best-effort: a missing/unreachable DB must not block a run.
    try:
        await _session_repo.create_session(session_id, request.question, request.phase)
    except Exception:
        logger.warning("Could not persist session %s to registry", session_id, exc_info=True)

    if not deferred:
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
    """Check the status of a research session.

    Prefers the checkpointer (survives restart), falling back to the in-memory
    overlay and then the durable registry.
    """
    return await _graph_session_status(session_id)


async def _graph_session_status(session_id: str) -> SessionStatus:
    """Derive session status from checkpointer state."""
    in_memory = _sessions.get(session_id)

    # Paused at a HITL gate — surface the interrupt payload for the approval card.
    if in_memory and in_memory.get("status") == "awaiting_input":
        tracker = _cost_trackers.get(session_id)
        cost = tracker.session_total(session_id) if tracker else 0.0
        return SessionStatus(
            session_id=session_id, status="awaiting_input",
            cost_so_far=round(cost, 4), interrupt=in_memory.get("interrupt"),
        )

    # If the session is still tracked in _sessions as "running", trust that.
    if in_memory and in_memory["status"] == "running":
        tracker = _cost_trackers.get(session_id)
        cost = tracker.session_total(session_id) if tracker else 0.0
        return SessionStatus(
            session_id=session_id, status="running", cost_so_far=round(cost, 4),
        )

    # Read from checkpointer (works even after server restart).
    runner = await _get_graph_runner()
    state = await runner.get_state(session_id)
    if not state:
        # Durable fallback: the persisted registry survives even after the
        # checkpoint is pruned, and is the source of truth when no live graph
        # state exists.
        persisted = await _session_repo.get_session(session_id)
        if persisted:
            tracker = _cost_trackers.get(session_id)
            cost = tracker.session_total(session_id) if tracker else 0.0
            return SessionStatus(
                session_id=session_id, status=persisted.status,
                cost_so_far=round(cost, 4),
            )
        if in_memory:
            return SessionStatus(
                session_id=session_id, status=in_memory.get("status", "unknown"),
            )
        raise HTTPException(status_code=404, detail="Session not found")

    cost = state.get("cost_summary", {}).get("total_usd", 0.0)
    status = state.get("status", "unknown")

    return SessionStatus(
        session_id=session_id, status=status, cost_so_far=round(cost, 4),
    )


@router.get("/research/{session_id}/results", response_model=ResearchResult)
async def get_session_results(session_id: str):
    """Get the results of a completed research session (read from checkpointer)."""
    return await _graph_session_results(session_id)


async def _graph_session_results(session_id: str) -> ResearchResult:
    """Read results from the checkpointer (graph mode)."""
    in_memory = _sessions.get(session_id)
    if in_memory and in_memory["status"] == "running":
        raise HTTPException(status_code=202, detail="Pipeline still running")

    runner = await _get_graph_runner()
    state = await runner.get_state(session_id)
    if not state:
        # Durable fallback to the persisted registry (survives restarts / pruned
        # checkpoints).
        persisted = await _session_repo.get_session(session_id)
        if persisted:
            if persisted.status == "running":
                raise HTTPException(status_code=202, detail="Pipeline still running")
            result = persisted.result or {}
            if not result:
                raise HTTPException(status_code=500, detail="Pipeline failed with no result")
            return _result_from_dict(session_id, result)
        if in_memory and in_memory.get("result"):
            return _result_from_dict(session_id, in_memory["result"])
        raise HTTPException(status_code=404, detail="Session not found")

    return _result_from_dict(session_id, state)


def _result_from_dict(session_id: str, result: dict) -> ResearchResult:
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


@router.get("/research/{session_id}/trace")
async def get_session_trace(session_id: str):
    """Per-node execution trace (timing) for a research session.

    Reads the checkpointed ``node_metrics`` written by the timing wrapper around
    each graph node. Returns one record per node execution plus a roll-up of
    total/aggregate durations — useful for spotting slow stages and verifying
    fan-out parallelism.
    """
    runner = await _get_graph_runner()
    state = await runner.get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    metrics: list[dict] = state.get("node_metrics", []) or []

    by_node: dict[str, dict] = {}
    for m in metrics:
        name = m.get("node", "?")
        agg = by_node.setdefault(name, {"node": name, "calls": 0, "total_s": 0.0})
        agg["calls"] += 1
        agg["total_s"] = round(agg["total_s"] + m.get("duration_s", 0.0), 4)

    return {
        "session_id": session_id,
        "status": state.get("status", "unknown"),
        "node_count": len(metrics),
        "total_duration_s": round(sum(m.get("duration_s", 0.0) for m in metrics), 4),
        "by_node": sorted(by_node.values(), key=lambda a: a["total_s"], reverse=True),
        "trace": metrics,
    }


@router.get("/research/{session_id}/cost", response_model=DetailedCostReport)
async def get_session_cost(session_id: str):
    """Get detailed cost report for a research session."""
    session = await _session_repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    tracker = _cost_trackers.get(session_id)

    # Fall back to stored cost records when the in-memory tracker is gone (e.g. after restart)
    if tracker:
        records = tracker.all_records_for_session(session_id)
        summary = tracker.session_summary(session_id)
    elif session.cost_records:
        records = session.cost_records
        by_model: dict[str, float] = {}
        for r in records:
            by_model[r["model"]] = by_model.get(r["model"], 0.0) + r.get("cost_usd", 0.0)
        summary = {
            "total_usd": round(sum(by_model.values()), 4),
            "by_model": {k: round(v, 4) for k, v in by_model.items()},
            "call_count": len(records),
        }
    else:
        raise HTTPException(status_code=404, detail="No cost data for session")

    by_agent: dict[str, float] = {}
    cache_savings = 0.0
    calls = []
    for r in records:
        by_agent[r["agent"]] = by_agent.get(r["agent"], 0.0) + r["cost_usd"]
        cached = r.get("cached_tokens", 0)
        if cached:
            pricing = MODEL_PRICING.get(r["model"], {})
            if pricing:
                # Cached tokens are billed at a lower rate; savings = difference * tokens
                cache_savings += (cached / 1_000_000) * (
                    pricing.get("input_per_m", 0) - pricing.get("cached_input_per_m", 0)
                )
        calls.append(CostDetail(
            call_id=r["call_id"],
            agent=r["agent"],
            model=r["model"],
            reasoning_effort=r["reasoning_effort"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            cached_tokens=cached,
            cost_usd=r["cost_usd"],
            timestamp=r["timestamp"],
        ))

    return DetailedCostReport(
        session_id=session_id,
        total_usd=summary["total_usd"],
        by_model=summary["by_model"],
        by_agent={k: round(v, 4) for k, v in by_agent.items()},
        call_count=summary["call_count"],
        cache_savings_estimate_usd=round(cache_savings, 4),
        calls=calls,
    )


async def _build_session_resources(
    phase: int, source: str, cfg
) -> tuple[Any, Any, Any, Any]:
    """Build per-session resources shared by run + stream + resume.

    Returns ``(graph_store, zotero_client, vector_store, embedding_fn)``. The
    graph store (Phase 3) and semantic-search resources (Phase 2+, when Qdrant +
    an OpenAI key are configured) are optional; absent ones are ``None`` and the
    pipeline degrades gracefully.
    """
    graph_store = None
    if phase >= 3:
        from science_ai.storage.graph_store import InMemoryGraphStore
        graph_store = InMemoryGraphStore()

    # Semantic indexing + embedding-based gap similarity kick in from Phase 2.
    vector_store, embedding_fn = (None, None)
    if phase >= 2:
        vector_store, embedding_fn = await _get_vector_resources(cfg)

    zotero_client = None
    if source in ("zotero", "both") and cfg.zotero_library_id and cfg.zotero_api_key:
        from science_ai.services.zotero_client import ZoteroClient
        zotero_client = ZoteroClient(
            library_id=cfg.zotero_library_id,
            api_key=cfg.zotero_api_key,
            library_type=cfg.zotero_library_type,
        )
    return graph_store, zotero_client, vector_store, embedding_fn


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Events frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


async def _consume_graph_stream(session_id, session, tracker, runner, stream_iter):
    """Consume a runner stream/resume iterator and yield SSE frames.

    Detects HITL interrupts: when the graph pauses, emits an ``interrupt``
    event carrying the gate payload. The underlying graph iterator is then
    drained to its natural end rather than abandoned — with an async
    checkpointer (Postgres), abandoning the generator early cancels the
    interrupt checkpoint write, which would break the subsequent ``/resume``.
    """
    interrupted = False
    try:
        async for mode, chunk in stream_iter:
            if mode == "custom":
                if not interrupted:
                    yield _sse("progress", chunk)
            elif mode == "updates":
                if isinstance(chunk, dict) and "__interrupt__" in chunk:
                    intr = chunk["__interrupt__"]
                    try:
                        payload = intr[0].value
                    except Exception:
                        payload = {}
                    session["status"] = "awaiting_input"
                    session["interrupt"] = payload
                    interrupted = True
                    yield _sse("interrupt", payload)
                    # Keep draining so the checkpoint flushes; do not return.
                    continue
                if not interrupted:
                    for node, upd in chunk.items():
                        status = upd.get("status") if isinstance(upd, dict) else None
                        yield _sse("node", {"node": node, "status": status})

        if interrupted:
            await _persist_status(session_id, "awaiting_input")
            return

        # No interrupt — the graph ran to completion.
        state = await runner.get_state(session_id)
        if state is not None:
            state["cost_summary"] = tracker.session_summary(session_id)
            session["result"] = state
        session["status"] = "completed"
        session["interrupt"] = None
        await _persist_result(session_id, session.get("result") or {}, tracker)
        cost = tracker.session_total(session_id)
        yield _sse("done", {"status": "completed", "cost_so_far": round(cost, 4)})
    except Exception as e:
        logger.exception("Stream failed for session %s", session_id)
        session["status"] = "failed"
        session["result"] = {"status": "failed"}
        await _persist_status(session_id, "failed")
        yield _sse("error", {"message": str(e)})


@router.get("/research/{session_id}/stream")
async def stream_research(session_id: str):
    """Stream live pipeline progress via Server-Sent Events (graph mode).

    Drives the graph for sessions created with ``stream=true`` and emits:
      - ``progress`` events: human-readable stage updates from nodes
      - ``node`` events: a graph node finished (with its status)
      - ``interrupt`` events: a HITL gate is awaiting approval
      - ``done`` / ``error``: terminal events
    """
    from science_ai.config import settings as cfg

    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_gen():
        # Only deferred sessions (created via stream=true) are executed here.
        # Anything else (already running in the background, or finished) just
        # reports its status so the client can fall back to polling — this
        # prevents double-executing a session.
        if session["status"] != "created":
            yield _sse("done", {"status": session["status"], "owned": False})
            return

        runner = await _get_graph_runner()
        tracker = _cost_trackers.setdefault(session_id, CostTracker())
        graph_store, zotero_client, vector_store, embedding_fn = (
            await _build_session_resources(
                session["phase"], session.get("source", "web"), cfg,
            )
        )
        session["status"] = "running"

        yield _sse("progress", {"stage": "start", "msg": "Pipeline starting…"})
        stream_iter = runner.stream(
            session["question"],
            session_id=session_id,
            phase=session["phase"],
            max_papers=session.get("max_papers", 15),
            user_background=session.get("user_background", ""),
            source=session.get("source", "web"),
            cost_tracker=tracker,
            graph_store=graph_store,
            vector_store=vector_store,
            embedding_fn=embedding_fn,
            zotero_client=zotero_client,
            hitl_gates=session.get("hitl_gates", []),
        )
        async for frame in _consume_graph_stream(
            session_id, session, tracker, runner, stream_iter,
        ):
            yield frame

    return StreamingResponse(
        event_gen(), media_type="text/event-stream", headers=_SSE_HEADERS,
    )


@router.post("/research/{session_id}/resume")
async def resume_research(session_id: str, body: ResumeRequest):
    """Resume an interrupted session at a HITL gate, streaming the continuation."""
    from science_ai.config import settings as cfg

    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("status") != "awaiting_input":
        raise HTTPException(status_code=409, detail="Session is not awaiting input")

    decision = {"action": body.action}
    if body.plan is not None:
        decision["plan"] = body.plan
    if body.verified_gaps is not None:
        decision["verified_gaps"] = body.verified_gaps

    async def event_gen():
        runner = await _get_graph_runner()
        tracker = _cost_trackers.setdefault(session_id, CostTracker())
        graph_store, zotero_client, vector_store, embedding_fn = (
            await _build_session_resources(
                session["phase"], session.get("source", "web"), cfg,
            )
        )
        session["status"] = "running"
        session["interrupt"] = None

        yield _sse("progress", {"stage": "resume", "msg": f"Resuming ({body.action})…"})
        stream_iter = runner.resume(
            session_id, decision,
            cost_tracker=tracker,
            graph_store=graph_store,
            vector_store=vector_store,
            embedding_fn=embedding_fn,
            zotero_client=zotero_client,
        )
        async for frame in _consume_graph_stream(
            session_id, session, tracker, runner, stream_iter,
        ):
            yield frame

    return StreamingResponse(
        event_gen(), media_type="text/event-stream", headers=_SSE_HEADERS,
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
        for tool_name, cmd in [("codex", settings.cli_codex_command), ("antigravity", settings.cli_antigravity_command), ("claude", settings.cli_claude_command)]:
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
    """List all research sessions from the durable registry."""
    sessions = await _session_repo.list_sessions()
    items = []
    for sess in sessions:
        tracker = _cost_trackers.get(sess.session_id)
        cost = tracker.session_total(sess.session_id) if tracker else 0.0
        items.append(SessionListItem(
            session_id=sess.session_id,
            status=sess.status,
            question=sess.question,
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
    """Background task that runs the (non-streaming) research pipeline."""
    from science_ai.config import settings as cfg

    tracker = _cost_trackers.get(session_id, CostTracker())

    try:
        runner = await _get_graph_runner()
        graph_store, zotero_client, vector_store, embedding_fn = (
            await _build_session_resources(phase, source, cfg)
        )
        hitl_gates = _sessions.get(session_id, {}).get("hitl_gates", [])

        result = await runner.run(
            question=question,
            session_id=session_id,
            phase=phase,
            max_papers=max_papers,
            user_background=user_background,
            source=source,
            cost_tracker=tracker,
            graph_store=graph_store,
            vector_store=vector_store,
            embedding_fn=embedding_fn,
            zotero_client=zotero_client,
            hitl_gates=hitl_gates,
        )

        # If a HITL gate paused the run, surface it for /resume.
        pending = await runner.get_pending_interrupt(session_id)
        if pending is not None:
            _sessions[session_id]["status"] = "awaiting_input"
            _sessions[session_id]["interrupt"] = pending
            await _persist_status(session_id, "awaiting_input")
        else:
            _sessions[session_id]["result"] = result
            _sessions[session_id]["status"] = "completed"
            await _persist_result(session_id, result, tracker)
    except Exception:
        logger.exception("Graph pipeline failed for session %s", session_id)
        _sessions[session_id]["status"] = "failed"
        _sessions[session_id]["result"] = {"status": "failed"}
        await _persist_status(session_id, "failed")
