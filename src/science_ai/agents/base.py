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

    @staticmethod
    def extract_list(parsed: Any, *keys: str) -> list[dict[str, Any]]:
        """Pull a list out of an LLM JSON response regardless of envelope shape.

        Models — especially the CLI tools — don't reliably wrap arrays in the
        requested key. This accepts any of:
          - ``{"ideas": [...]}``           (the requested key)
          - ``{"results": [...]}``         (CLI client wraps a bare array here)
          - ``[...]``                      (a bare top-level array)
        Returns ``[]`` only when no list can be found, so a stray response shape
        never silently drops a whole stage's output.
        """
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in (*keys, "results"):
                value = parsed.get(key)
                if isinstance(value, list):
                    return value
            # Last resort: if exactly one value is a list, use it.
            list_values = [v for v in parsed.values() if isinstance(v, list)]
            if len(list_values) == 1:
                return list_values[0]
        return []

    @abstractmethod
    async def run(self, **kwargs: Any) -> dict[str, Any]:
        """Execute the agent's main task. Subclasses must implement."""
        ...
