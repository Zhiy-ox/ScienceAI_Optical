"""Cost tracking for every LLM API call."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from science_ai.config import MODEL_PRICING

logger = logging.getLogger(__name__)


@dataclass
class CallRecord:
    call_id: str
    session_id: str
    agent: str
    model: str
    reasoning_effort: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: float
    timestamp: float


@dataclass
class CostTracker:
    """Records per-call costs and produces session summaries."""

    records: list[CallRecord] = field(default_factory=list)

    def _compute_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
    ) -> float:
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            logger.warning("No pricing info for model %s, estimating $0", model)
            return 0.0

        regular_input = input_tokens - cached_tokens
        cost = (
            (regular_input / 1_000_000) * pricing["input_per_m"]
            + (cached_tokens / 1_000_000) * pricing["cached_input_per_m"]
            + (output_tokens / 1_000_000) * pricing["output_per_m"]
        )
        return round(cost, 6)

    def record_call(
        self,
        session_id: str,
        agent: str,
        model: str,
        reasoning_effort: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
    ) -> float:
        """Record a single API call. Returns the computed cost in USD."""
        cost = self._compute_cost(model, input_tokens, output_tokens, cached_tokens)
        record = CallRecord(
            call_id=str(uuid.uuid4()),
            session_id=session_id,
            agent=agent,
            model=model,
            reasoning_effort=reasoning_effort,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost,
            timestamp=time.time(),
        )
        self.records.append(record)
        logger.info(
            "LLM call: agent=%s model=%s tokens=%d/%d cost=$%.4f",
            agent, model, input_tokens, output_tokens, cost,
        )
        return cost

    def session_total(self, session_id: str) -> float:
        """Total cost for a session."""
        return sum(r.cost_usd for r in self.records if r.session_id == session_id)

    def session_summary(self, session_id: str) -> dict:
        """Generate a cost summary grouped by model."""
        session_records = [r for r in self.records if r.session_id == session_id]
        by_model: dict[str, float] = {}
        for r in session_records:
            by_model[r.model] = by_model.get(r.model, 0.0) + r.cost_usd

        total = sum(by_model.values())
        return {
            "session_id": session_id,
            "total_usd": round(total, 4),
            "by_model": {k: round(v, 4) for k, v in by_model.items()},
            "call_count": len(session_records),
        }

    def all_records_for_session(self, session_id: str) -> list[dict]:
        """Return all call records as dicts for persistence."""
        return [
            {
                "call_id": r.call_id,
                "agent": r.agent,
                "model": r.model,
                "reasoning_effort": r.reasoning_effort,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cached_tokens": r.cached_tokens,
                "cost_usd": r.cost_usd,
                "timestamp": r.timestamp,
            }
            for r in self.records
            if r.session_id == session_id
        ]
