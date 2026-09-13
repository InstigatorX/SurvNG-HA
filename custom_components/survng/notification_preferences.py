"""Persistent HA-local notification preferences, scoped by camera and zone."""
from __future__ import annotations

import asyncio
from collections.abc import Iterable

from homeassistant.helpers.storage import Store

from .const import DOMAIN


class ZoneNotificationPreferences:
    def __init__(self, hass, entry_id: str) -> None:
        self._store = Store(hass, 1, f"{DOMAIN}.{entry_id}.zone_notifications", atomic_writes=True)
        self._disabled: set[tuple[str, str]] = set()
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data is None:
            return
        rows = data.get("disabled_zones") if isinstance(data, dict) else None
        if not isinstance(rows, list) or any(
            not isinstance(row, list) or len(row) != 2
            or not all(isinstance(value, str) for value in row)
            for row in rows
        ):
            raise ValueError("Invalid stored SurvNG zone notification preferences")
        self._disabled = {tuple(row) for row in rows}

    def enabled(self, camera_id: str, zone: str) -> bool:
        return (camera_id, zone) not in self._disabled

    def allows(self, camera_id: str, zones: Iterable[str]) -> bool:
        matched = tuple(zones)
        return not matched or any(self.enabled(camera_id, zone) for zone in matched)

    async def async_set(self, camera_id: str, zone: str, enabled: bool) -> None:
        async with self._lock:
            updated = self._disabled.copy()
            key = (camera_id, zone)
            if enabled:
                updated.discard(key)
            else:
                updated.add(key)
            if updated == self._disabled:
                return
            # Save through HA storage before publishing the new preference.
            await self._store.async_save({"disabled_zones": [list(key) for key in sorted(updated)]})
            self._disabled = updated
