"""Pipeline monitor — tracks which step the research pipeline is currently executing."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class StepRecord:
    step_number: int
    step_name: str
    started_at: float
    finished_at: float | None = None
    status: str = "running"  # "running" | "done" | "skipped" | "failed"


@dataclass
class PipelineMonitor:
    """Tracks the current step and step history for a pipeline session.

    Usage in the orchestrator::

        monitor.start_step(session_id, 1, "Query Planning")
        # ... do work ...
        monitor.finish_step(session_id, 1)

    The current progress can be retrieved at any time via :meth:`snapshot`.
    """

    _sessions: dict[str, list[StepRecord]] = field(default_factory=dict)

    def start_step(self, session_id: str, step_number: int, step_name: str) -> None:
        """Mark a step as started."""
        records = self._sessions.setdefault(session_id, [])
        records.append(
            StepRecord(
                step_number=step_number,
                step_name=step_name,
                started_at=time.time(),
            )
        )

    def finish_step(
        self,
        session_id: str,
        step_number: int,
        *,
        status: str = "done",
    ) -> None:
        """Mark a step as finished."""
        for record in reversed(self._sessions.get(session_id, [])):
            if record.step_number == step_number and record.finished_at is None:
                record.finished_at = time.time()
                record.status = status
                return

    def skip_step(self, session_id: str, step_number: int, step_name: str) -> None:
        """Record a step that was skipped (e.g. no verified gaps)."""
        records = self._sessions.setdefault(session_id, [])
        now = time.time()
        records.append(
            StepRecord(
                step_number=step_number,
                step_name=step_name,
                started_at=now,
                finished_at=now,
                status="skipped",
            )
        )

    def snapshot(self, session_id: str) -> dict:
        """Return the current progress snapshot for a session.

        Returns a dict with:
        - ``current_step``: name of the currently running step, or ``None``
        - ``current_step_number``: its step number, or ``None``
        - ``elapsed_seconds``: seconds since the current step started
        - ``steps``: ordered list of all step records so far
        """
        records = self._sessions.get(session_id, [])

        current: StepRecord | None = None
        for record in reversed(records):
            if record.status == "running":
                current = record
                break

        steps = [
            {
                "step_number": r.step_number,
                "step_name": r.step_name,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "duration_seconds": (
                    round((r.finished_at - r.started_at), 2)
                    if r.finished_at is not None
                    else round(time.time() - r.started_at, 2)
                ),
            }
            for r in records
        ]

        return {
            "current_step": current.step_name if current else None,
            "current_step_number": current.step_number if current else None,
            "elapsed_seconds": (
                round(time.time() - current.started_at, 2) if current else None
            ),
            "steps": steps,
        }

    def clear(self, session_id: str) -> None:
        """Remove all records for a session (call after session is persisted)."""
        self._sessions.pop(session_id, None)
