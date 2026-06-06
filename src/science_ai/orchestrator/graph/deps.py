"""Dependency-injection container passed via LangGraph config."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from science_ai.cost.tracker import CostTracker
from science_ai.orchestrator.feedback import FeedbackController
from science_ai.services.paper_search import PaperSearchService

DEFAULT_FANOUT_CONCURRENCY = 5


@dataclass
class Deps:
    llm: Any  # LLMClient | CLILLMClient
    search: PaperSearchService = field(default_factory=PaperSearchService)
    cost_tracker: CostTracker = field(default_factory=CostTracker)
    feedback: FeedbackController = field(default_factory=FeedbackController)
    vector_store: Any | None = None
    graph_store: Any | None = None
    embedding_fn: Any | None = None
    zotero_client: Any | None = None
    fanout_semaphore: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(DEFAULT_FANOUT_CONCURRENCY)
    )


def get_deps(config: dict) -> Deps:
    return config["configurable"]["deps"]
