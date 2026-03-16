"""Model Router — maps tasks to optimal model + reasoning effort."""

from __future__ import annotations

from science_ai.config import MODEL_PRICING, TASK_MODEL_MAP


class ModelRouter:
    """Rules engine for task → model routing with cost awareness."""

    def __init__(self, overrides: dict[str, dict] | None = None) -> None:
        self.routing_table = {**TASK_MODEL_MAP}
        if overrides:
            self.routing_table.update(overrides)

    def route(self, task_type: str) -> tuple[str, str]:
        """Return (model_id, reasoning_effort) for a task type.

        Raises ValueError if task_type is unknown.
        """
        mapping = self.routing_table.get(task_type)
        if not mapping:
            raise ValueError(f"Unknown task type: {task_type}")
        return mapping["model"], mapping["reasoning_effort"]

    def estimate_cost(
        self, task_type: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Estimate the cost of a task before execution."""
        model, _ = self.route(task_type)
        pricing = MODEL_PRICING.get(model, {})
        if not pricing:
            return 0.0

        cost = (
            (input_tokens / 1_000_000) * pricing.get("input_per_m", 0)
            + (output_tokens / 1_000_000) * pricing.get("output_per_m", 0)
        )
        return round(cost, 6)

    def available_models(self) -> list[dict]:
        """List all configured models with their capabilities."""
        return [
            {"model": model_id, **info}
            for model_id, info in MODEL_PRICING.items()
        ]
