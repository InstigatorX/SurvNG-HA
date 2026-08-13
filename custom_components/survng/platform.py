"""Dynamic platform helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def setup_dynamic_camera_entities(coordinator, async_add_entities, factory: Callable[[str], list[Any]]):
    """Add entities for newly discovered cameras exactly once."""
    known: set[str] = set()

    def reconcile() -> None:
        additions = []
        for camera_id in coordinator.data.cameras:
            if camera_id not in known:
                known.add(camera_id)
                additions.extend(factory(camera_id))
        if additions:
            async_add_entities(additions)

    reconcile()
    return coordinator.async_add_listener(reconcile)
