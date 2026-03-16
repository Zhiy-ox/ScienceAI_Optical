"""Redis-backed session memory for intermediate results and state."""

from __future__ import annotations

import json
import logging

import redis.asyncio as redis

from science_ai.config import settings

logger = logging.getLogger(__name__)

# TTL for session keys: 7 days
SESSION_TTL = 7 * 24 * 3600


class SessionMemory:
    """Redis session store for research pipeline state."""

    def __init__(self) -> None:
        self.redis: redis.Redis | None = None

    async def connect(self) -> None:
        self.redis = redis.from_url(settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        if self.redis:
            await self.redis.aclose()

    def _key(self, session_id: str, field: str) -> str:
        return f"session:{session_id}:{field}"

    async def set_plan(self, session_id: str, plan: dict) -> None:
        await self.redis.set(
            self._key(session_id, "plan"), json.dumps(plan), ex=SESSION_TTL
        )

    async def get_plan(self, session_id: str) -> dict | None:
        val = await self.redis.get(self._key(session_id, "plan"))
        return json.loads(val) if val else None

    async def set_status(self, session_id: str, status: str) -> None:
        await self.redis.set(
            self._key(session_id, "status"), status, ex=SESSION_TTL
        )

    async def get_status(self, session_id: str) -> str | None:
        return await self.redis.get(self._key(session_id, "status"))

    async def push_to_queue(self, session_id: str, items: list[dict]) -> None:
        """Add papers to the processing queue."""
        key = self._key(session_id, "queue")
        for item in items:
            await self.redis.rpush(key, json.dumps(item))
        await self.redis.expire(key, SESSION_TTL)

    async def pop_from_queue(self, session_id: str, count: int = 1) -> list[dict]:
        """Pop papers from the processing queue."""
        key = self._key(session_id, "queue")
        results = []
        for _ in range(count):
            val = await self.redis.lpop(key)
            if val is None:
                break
            results.append(json.loads(val))
        return results

    async def store_result(self, session_id: str, key: str, data: dict) -> None:
        """Store an intermediate result (e.g., triage output, knowledge object)."""
        full_key = self._key(session_id, f"results:{key}")
        await self.redis.set(full_key, json.dumps(data), ex=SESSION_TTL)

    async def get_result(self, session_id: str, key: str) -> dict | None:
        full_key = self._key(session_id, f"results:{key}")
        val = await self.redis.get(full_key)
        return json.loads(val) if val else None

    async def update_cost(self, session_id: str, cost_record: dict) -> None:
        """Append a cost record to the session's cost log."""
        key = self._key(session_id, "cost")
        await self.redis.rpush(key, json.dumps(cost_record))
        await self.redis.expire(key, SESSION_TTL)

    async def get_total_cost(self, session_id: str) -> float:
        """Sum up all cost records for a session."""
        key = self._key(session_id, "cost")
        records = await self.redis.lrange(key, 0, -1)
        total = 0.0
        for r in records:
            total += json.loads(r).get("cost_usd", 0.0)
        return total
