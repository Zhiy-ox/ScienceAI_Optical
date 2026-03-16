"""Unified LLM client wrapping LiteLLM with cost tracking and retry logic."""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm

from science_ai.config import MODEL_PRICING, TASK_MODEL_MAP, settings
from science_ai.cost.tracker import CostTracker

logger = logging.getLogger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True


class LLMClient:
    """Unified interface for calling GPT-5.4 / Gemini 3.1 Pro / Claude Opus & Sonnet."""

    def __init__(self, cost_tracker: CostTracker | None = None) -> None:
        self.cost_tracker = cost_tracker or CostTracker()
        self._configure_keys()

    def _configure_keys(self) -> None:
        """Push API keys into litellm's env if set."""
        import os

        if settings.openai_api_key:
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        if settings.google_api_key:
            os.environ["GOOGLE_API_KEY"] = settings.google_api_key
        if settings.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    def resolve_model(self, task_type: str) -> tuple[str, str]:
        """Return (model_id, reasoning_effort) for a given task type."""
        mapping = TASK_MODEL_MAP.get(task_type)
        if not mapping:
            raise ValueError(f"Unknown task type: {task_type}")
        return mapping["model"], mapping["reasoning_effort"]

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        task_type: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format: dict | None = None,
        agent_name: str = "unknown",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Call an LLM and return the parsed response with cost info.

        Either provide `task_type` (auto-resolves model) or explicit `model`.
        """
        if task_type and not model:
            model, reasoning_effort = self.resolve_model(task_type)
        if not model:
            raise ValueError("Must provide task_type or model")

        # Build kwargs
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        # Reasoning effort (provider-specific)
        if reasoning_effort:
            pricing = MODEL_PRICING.get(model, {})
            if pricing.get("supports_reasoning_effort"):
                if pricing.get("provider") == "openai":
                    kwargs["reasoning_effort"] = reasoning_effort
                elif pricing.get("provider") == "anthropic":
                    # Claude uses thinking/budget via extended_thinking or metadata
                    kwargs["metadata"] = {"reasoning_effort": reasoning_effort}

        # Call with retries
        response = await litellm.acompletion(**kwargs, num_retries=3)

        # Extract usage
        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cached_tokens = getattr(usage, "prompt_tokens_details", None)
        cached_count = 0
        if cached_tokens and hasattr(cached_tokens, "cached_tokens"):
            cached_count = cached_tokens.cached_tokens or 0

        # Track cost
        cost = self.cost_tracker.record_call(
            session_id=session_id or "",
            agent=agent_name,
            model=model,
            reasoning_effort=reasoning_effort or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_count,
        )

        # Parse content
        content = response.choices[0].message.content or ""

        return {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_count,
            "cost_usd": cost,
            "model": model,
        }

    async def complete_json(
        self,
        *,
        messages: list[dict[str, str]],
        task_type: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_tokens: int = 4096,
        agent_name: str = "unknown",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Call LLM expecting JSON output. Parses the response into a dict."""
        result = await self.complete(
            messages=messages,
            task_type=task_type,
            model=model,
            reasoning_effort=reasoning_effort,
            temperature=0.0,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            agent_name=agent_name,
            session_id=session_id,
        )

        try:
            parsed = json.loads(result["content"])
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            content = result["content"]
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            parsed = json.loads(content.strip())

        result["parsed"] = parsed
        return result
