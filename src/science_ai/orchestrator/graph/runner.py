"""High-level runner that wires up Deps and invokes the compiled graph.

The runner is designed to be a long-lived singleton: the LLM client, search
service, and checkpointer are shared across sessions; per-session resources
(cost tracker, graph store, zotero client) are passed to ``run()``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from science_ai.cost.tracker import CostTracker
from science_ai.orchestrator.feedback import FeedbackController
from science_ai.orchestrator.graph.builder import build_graph
from science_ai.orchestrator.graph.deps import Deps
from science_ai.services.paper_search import PaperSearchService

logger = logging.getLogger(__name__)


class GraphRunner:
    """Manages graph compilation, dependency wiring, and invocation.

    Shared across sessions — create once at app startup, use for every run.
    """

    def __init__(
        self,
        *,
        checkpointer: Any = None,
        search_service: PaperSearchService | None = None,
        llm_backend: str | None = None,
        fanout_concurrency: int | None = None,
    ) -> None:
        from science_ai.config import settings

        backend = llm_backend or settings.llm_backend
        self._fanout_concurrency = (
            fanout_concurrency if fanout_concurrency is not None
            else settings.fanout_concurrency
        )
        # One tracker shared by the LLM client (which records every call into
        # it) and the per-session summaries. CostTracker keys records by
        # session_id, so a single instance safely serves all sessions; giving
        # the client a different tracker than the one summaries are read from
        # would silently report $0 for every run.
        self.cost_tracker = CostTracker()
        if backend == "cli":
            from science_ai.services.cli_llm_client import CLILLMClient
            self.llm = CLILLMClient(
                cost_tracker=self.cost_tracker,
                codex_cmd=settings.cli_codex_command,
                antigravity_cmd=settings.cli_antigravity_command,
                claude_cmd=settings.cli_claude_command,
                timeout=settings.cli_timeout_seconds,
            )
            logger.info("GraphRunner: CLI backend")
        else:
            from science_ai.services.llm_client import LLMClient
            self.llm = LLMClient(cost_tracker=self.cost_tracker)
            logger.info("GraphRunner: API backend")

        self.search = search_service or PaperSearchService()
        self._checkpointer = checkpointer or MemorySaver()
        self._graph = build_graph(checkpointer=self._checkpointer)

    def _build_deps(
        self,
        cost_tracker: CostTracker,
        graph_store: Any = None,
        embedding_fn: Any = None,
        vector_store: Any = None,
        zotero_client: Any = None,
    ) -> Deps:
        return Deps(
            llm=self.llm,
            search=self.search,
            cost_tracker=cost_tracker,
            feedback=FeedbackController(),
            vector_store=vector_store,
            graph_store=graph_store,
            embedding_fn=embedding_fn,
            zotero_client=zotero_client,
            fanout_semaphore=asyncio.Semaphore(self._fanout_concurrency),
        )

    async def run(
        self,
        question: str,
        *,
        session_id: str | None = None,
        phase: int = 3,
        max_papers: int = 15,
        user_background: str = "",
        source: str = "web",
        cost_tracker: CostTracker | None = None,
        graph_store: Any = None,
        vector_store: Any = None,
        embedding_fn: Any = None,
        zotero_client: Any = None,
        hitl_gates: list[str] | None = None,
    ) -> dict[str, Any]:
        """Kick off the graph and return the final state as a result dict."""
        session_id = session_id or str(uuid.uuid4())
        tracker = cost_tracker or self.cost_tracker

        initial_state = self._make_initial_state(
            question, session_id, phase, max_papers, user_background, source,
            hitl_gates,
        )
        config = self._make_config(
            session_id, tracker,
            graph_store=graph_store, vector_store=vector_store,
            embedding_fn=embedding_fn, zotero_client=zotero_client,
        )

        logger.info("GraphRunner: starting session %s (phase=%d)", session_id, phase)

        final_state = await self._graph.ainvoke(initial_state, config)

        final_state["cost_summary"] = tracker.session_summary(session_id)
        final_state["session_id"] = session_id

        logger.info(
            "GraphRunner: session %s complete, status=%s",
            session_id, final_state.get("status"),
        )
        return dict(final_state)

    async def stream(
        self,
        question: str,
        *,
        session_id: str,
        phase: int = 3,
        max_papers: int = 15,
        user_background: str = "",
        source: str = "web",
        cost_tracker: CostTracker | None = None,
        graph_store: Any = None,
        vector_store: Any = None,
        embedding_fn: Any = None,
        zotero_client: Any = None,
        hitl_gates: list[str] | None = None,
    ):
        """Drive the graph and yield ``(stream_mode, chunk)`` tuples live.

        Uses ``stream_mode=["updates", "custom"]`` so callers receive both
        node-completion updates and human-readable progress emitted by nodes
        via ``get_stream_writer()``.
        """
        tracker = cost_tracker or self.cost_tracker

        initial_state = self._make_initial_state(
            question, session_id, phase, max_papers, user_background, source,
            hitl_gates,
        )
        config = self._make_config(
            session_id, tracker,
            graph_store=graph_store, vector_store=vector_store,
            embedding_fn=embedding_fn, zotero_client=zotero_client,
        )

        logger.info("GraphRunner: streaming session %s (phase=%d)", session_id, phase)

        async for mode, chunk in self._graph.astream(
            initial_state, config, stream_mode=["updates", "custom"],
        ):
            yield mode, chunk

    async def resume(
        self,
        session_id: str,
        decision: dict[str, Any],
        *,
        cost_tracker: CostTracker | None = None,
        graph_store: Any = None,
        vector_store: Any = None,
        embedding_fn: Any = None,
        zotero_client: Any = None,
    ):
        """Resume an interrupted session and stream the continuation.

        Yields ``(stream_mode, chunk)`` tuples just like ``stream()``.
        """
        from langgraph.types import Command

        tracker = cost_tracker or self.cost_tracker
        config = self._make_config(
            session_id, tracker,
            graph_store=graph_store, vector_store=vector_store,
            embedding_fn=embedding_fn, zotero_client=zotero_client,
        )

        logger.info("GraphRunner: resuming session %s", session_id)

        async for mode, chunk in self._graph.astream(
            Command(resume=decision), config, stream_mode=["updates", "custom"],
        ):
            yield mode, chunk

    def _make_initial_state(
        self,
        question: str,
        session_id: str,
        phase: int,
        max_papers: int,
        user_background: str,
        source: str,
        hitl_gates: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "question": question,
            "max_papers": max_papers,
            "phase": phase,
            "user_background": user_background,
            "source": source,
            "hitl_gates": hitl_gates or [],
            "all_papers": [],
            "triage_results": [],
            "knowledge_objects": [],
            "critiques": [],
            "search_refine_count": 0,
            "gap_retry_count": 0,
            "idea_regen_count": 0,
            "refine_keywords": [],
            "previous_failures": [],
            "regen_constraint": "",
            "gap_retry_pending": False,
            "idea_regen_pending": False,
            "status": "starting",
            "papers_found": 0,
        }

    def _make_config(
        self,
        session_id: str,
        cost_tracker: CostTracker,
        *,
        graph_store: Any = None,
        vector_store: Any = None,
        embedding_fn: Any = None,
        zotero_client: Any = None,
    ) -> dict[str, Any]:
        return {
            "recursion_limit": 100,
            "configurable": {
                "thread_id": session_id,
                "deps": self._build_deps(
                    cost_tracker=cost_tracker,
                    graph_store=graph_store,
                    vector_store=vector_store,
                    embedding_fn=embedding_fn,
                    zotero_client=zotero_client,
                ),
            },
        }

    async def get_state(self, session_id: str) -> dict[str, Any] | None:
        """Read the current checkpointed state for a session."""
        config = {"configurable": {"thread_id": session_id}}
        snapshot = await self._graph.aget_state(config)
        if snapshot and snapshot.values:
            return dict(snapshot.values)
        return None

    async def get_snapshot(self, session_id: str):
        """Return the raw StateSnapshot (values + next pending nodes)."""
        config = {"configurable": {"thread_id": session_id}}
        return await self._graph.aget_state(config)

    async def get_pending_interrupt(self, session_id: str) -> dict[str, Any] | None:
        """Return the payload of a pending HITL interrupt, or None if not paused."""
        snapshot = await self.get_snapshot(session_id)
        if not snapshot:
            return None
        # langgraph surfaces interrupts on the snapshot and/or its pending tasks.
        interrupts = getattr(snapshot, "interrupts", None)
        if interrupts:
            return getattr(interrupts[0], "value", None)
        for task in getattr(snapshot, "tasks", None) or []:
            t_int = getattr(task, "interrupts", None)
            if t_int:
                return getattr(t_int[0], "value", None)
        return None
