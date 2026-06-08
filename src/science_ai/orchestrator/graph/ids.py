"""Canonical ID assignment for graph artifacts.

LLM agents emit placeholder IDs (e.g. ``"GAP-XXX"`` / ``"IDEA-XXX"``) straight
from their prompt templates, so they are unreliable for cross-referencing.
These helpers stamp deterministic, sequential IDs onto gaps, ideas, and
experiment plans, and keep the downstream linkage (verification ``gap_id``,
idea ``source_gap``, experiment ``idea_id``) stable regardless of what the
model returns.
"""

from __future__ import annotations

from typing import Any


def assign_sequential_ids(
    items: list[dict[str, Any]], prefix: str, key: str | None = None
) -> list[dict[str, Any]]:
    """Stamp ``{prefix}-001`, `{prefix}-002`, … onto ``items`` in place.

    Args:
        items: The artifact dicts to label (mutated in place).
        prefix: ID prefix, e.g. ``"GAP"`` or ``"IDEA"``.
        key: The dict key to write. Defaults to ``"{prefix.lower()}_id"``.

    Returns:
        The same list, for convenient chaining.
    """
    id_key = key or f"{prefix.lower()}_id"
    for i, item in enumerate(items, start=1):
        if isinstance(item, dict):
            item[id_key] = f"{prefix}-{i:03d}"
    return items


def stamp_linked_id(
    target: dict[str, Any], source: dict[str, Any], key: str
) -> dict[str, Any]:
    """Copy ``source[key]`` onto ``target[key]`` to preserve a cross-reference.

    Used when a downstream artifact (a verification result, an experiment plan)
    is produced per-input in order, but the agent may not echo the canonical ID
    of the input it was derived from. No-op when the source lacks ``key``.
    """
    if isinstance(target, dict) and key in source:
        target[key] = source[key]
    return target
