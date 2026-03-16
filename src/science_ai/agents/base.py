"""Base agent class providing shared LLM calling and cost tracking."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from science_ai.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base for all Science AI agents.

    Subclasses implement `run()` with their specific logic.
    The base class provides the LLM client, session tracking, and common helpers.
    """

    agent_name: str = "base"
    default_task_type: str = ""

    def __init__(self, llm_client: LLMClient, session_id: str = "") -> None:
        self.llm = llm_client
        self.session_id = session_id

    async def call_llm(
        self,
        messages: list[dict[str, str]],
        *,
        task_type: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Convenience wrapper that injects agent_name and session_id."""
        return await self.llm.complete(
            messages=messages,
            task_type=task_type or self.default_task_type,
            model=model,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            agent_name=self.agent_name,
            session_id=self.session_id,
        )

    async def call_llm_json(
        self,
        messages: list[dict[str, str]],
        *,
        task_type: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Call LLM expecting JSON response."""
        return await self.llm.complete_json(
            messages=messages,
            task_type=task_type or self.default_task_type,
            model=model,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            agent_name=self.agent_name,
            session_id=self.session_id,
        )

    def build_system_message(self, content: str) -> dict[str, str]:
        return {"role": "system", "content": content}

    def build_user_message(self, content: str) -> dict[str, str]:
        return {"role": "user", "content": content}

    @abstractmethod
    async def run(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the agent's main task. Subclasses must implement."""
        ...
