"""High-level runner that wires up Deps and invokes the compiled graph."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from science_ai.cost.tracker import CostTracker
from science_ai.orchestrator.feedback import FeedbackController
from science_ai.orchestrator.graph.builder import build_graph
from science_ai.orchestrator.graph.deps import Deps
from science_ai.orchestrator.graph.state import ResearchState
from science_ai.services.paper_search import PaperSearchService

logger = logging.getLogger(__name__)


class GraphRunner:
    """Manages graph compilation, dependency wiring, and invocation."""

    def __init__(
        self,
        cost_tracker: CostTracker | None = None,
        search_service: PaperSearchService | None = None,
        vector_store: Any | None = None,
        graph_store: Any | None = None,
        embedding_fn: Any | None = None,
        zotero_client: Any | None = None,
        llm_backend: str | None = None,
    ) -> None:
        from science_ai.config import settings

        self.cost_tracker = cost_tracker or CostTracker()

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
            logger.info("GraphRunner: CLI backend")
        else:
            from science_ai.services.llm_client import LLMClient
            self.llm = LLMClient(cost_tracker=self.cost_tracker)
            logger.info("GraphRunner: API backend")

        self.search = search_service or PaperSearchService()
        self.feedback = FeedbackController()
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.embedding_fn = embedding_fn
        self.zotero_client = zotero_client

        self._checkpointer = MemorySaver()
        self._graph = build_graph(checkpointer=self._checkpointer)

    def _build_deps(self) -> Deps:
        return Deps(
            llm=self.llm,
            search=self.search,
            cost_tracker=self.cost_tracker,
            feedback=self.feedback,
            vector_store=self.vector_store,
            graph_store=self.graph_store,
            embedding_fn=self.embedding_fn,
            zotero_client=self.zotero_client,
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
    ) -> dict[str, Any]:
        """Kick off the graph and return the final state as a result dict."""
        session_id = session_id or str(uuid.uuid4())

        initial_state: dict[str, Any] = {
            "session_id": session_id,
            "question": question,
            "max_papers": max_papers,
            "phase": phase,
            "user_background": user_background,
            "source": source,
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

        config = {
            # Loops can push past LangGraph's default 25-step recursion limit.
            "recursion_limit": 100,
            "configurable": {
                "thread_id": session_id,
                "deps": self._build_deps(),
            },
        }

        logger.info("GraphRunner: starting session %s (phase=%d)", session_id, phase)

        final_state = await self._graph.ainvoke(initial_state, config)

        cost_summary = self.cost_tracker.session_summary(session_id)
        final_state["cost_summary"] = cost_summary
        final_state["session_id"] = session_id

        logger.info(
            "GraphRunner: session %s complete, status=%s",
            session_id, final_state.get("status"),
        )
        return dict(final_state)

    async def get_state(self, session_id: str) -> dict[str, Any] | None:
        """Read the current checkpointed state for a session."""
        config = {"configurable": {"thread_id": session_id}}
        snapshot = await self._graph.aget_state(config)
        if snapshot and snapshot.values:
            return dict(snapshot.values)
        return None
