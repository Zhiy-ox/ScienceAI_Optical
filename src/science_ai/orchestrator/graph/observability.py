"""Per-node observability for the research graph.

``timed_node`` wraps a node coroutine so every execution records its wall-clock
duration and resulting status into the checkpointed ``node_metrics`` list (an
``operator.add`` reducer field). This gives a durable, per-session execution
trace — surfaced via ``GET /research/{id}/trace`` — without each node having to
opt in, and without disturbing LangGraph's ``(state, config)`` config injection.

Only true nodes are wrapped (registered via ``add_node``); the conditional-edge
dispatch functions that return ``Send`` lists are *not* nodes and are never
wrapped.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

NodeFn = Callable[..., Awaitable[dict[str, Any]]]

# Control-flow signals LangGraph raises through node bodies (interrupt / resume).
# These are not errors and must propagate untouched so the checkpoint flushes.
try:  # pragma: no cover - import shape varies across langgraph versions
    from langgraph.errors import GraphInterrupt

    _INTERRUPT_TYPES: tuple[type[BaseException], ...] = (GraphInterrupt,)
except Exception:  # pragma: no cover
    _INTERRUPT_TYPES = ()


def timed_node(name: str, fn: NodeFn) -> NodeFn:
    """Return ``fn`` wrapped to append a timing record to ``node_metrics``.

    The wrapper preserves the original ``(state, config)`` signature so
    LangGraph still injects the runnable config. A node that returns ``None``
    (a passthrough gate) still gets a metric recorded.
    """

    @functools.wraps(fn)
    async def wrapper(state: Any, config: Any) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            result = await fn(state, config)
        except _INTERRUPT_TYPES:
            # A HITL gate paused the graph — not a failure. Re-raise so
            # LangGraph can checkpoint the interrupt; no metric is recorded
            # for the (incomplete) node execution.
            raise
        except Exception as exc:  # record the failure, then re-raise
            elapsed = time.perf_counter() - start
            logger.info(
                "[graph] node %s FAILED in %.3fs (%s)", name, elapsed, type(exc).__name__,
            )
            raise
        elapsed = time.perf_counter() - start

        out = dict(result) if isinstance(result, dict) else {}
        metric = {
            "node": name,
            "duration_s": round(elapsed, 4),
            "status": out.get("status"),
        }
        logger.info("[graph] node %s done in %.3fs", name, elapsed)
        # operator.add reducer: contribute exactly one record (fan-out nodes
        # running in parallel each contribute their own).
        out["node_metrics"] = [metric]
        return out

    return wrapper
