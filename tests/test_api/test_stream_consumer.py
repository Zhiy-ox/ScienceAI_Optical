"""Regression test for the SSE stream consumer's interrupt handling.

``_consume_graph_stream`` must drain the underlying graph iterator past an
interrupt instead of returning immediately. With an async checkpointer
(Postgres in production), abandoning the generator early cancels the interrupt
checkpoint write and breaks the subsequent ``/resume``.
"""

import types
from unittest.mock import AsyncMock, patch

import pytest

import science_ai.api.routes as routes


@pytest.mark.asyncio
async def test_consume_drains_generator_past_interrupt():
    reached = {"after_interrupt": False}

    async def fake_stream():
        yield ("custom", {"stage": "plan", "msg": "planning"})
        yield ("updates", {"plan": {"status": "planned"}})
        yield ("updates", {"__interrupt__": [types.SimpleNamespace(value={"type": "approve_plan"})]})
        # Only reached if the consumer keeps iterating (does not abandon us here).
        reached["after_interrupt"] = True

    session: dict = {"status": "running", "interrupt": None, "result": None}
    events: list[str] = []

    # _persist_status would hit the DB; stub the repo so it's a no-op.
    with patch.object(routes, "_session_repo", AsyncMock()):
        async for frame in routes._consume_graph_stream(
            "sid", session, tracker=AsyncMock(), runner=AsyncMock(), stream_iter=fake_stream(),
        ):
            events.append(frame)

    # The generator was drained to its end (checkpoint write would have flushed).
    assert reached["after_interrupt"], "consumer abandoned the generator at the interrupt"
    # The interrupt was surfaced and the session marked awaiting input.
    assert session["status"] == "awaiting_input"
    assert session["interrupt"] == {"type": "approve_plan"}
    assert any("event: interrupt" in e for e in events)
    # No spurious completion event after an interrupt.
    assert not any("event: done" in e for e in events)
