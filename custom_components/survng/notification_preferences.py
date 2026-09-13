"""Server-owned zone notification controls with legacy HA preference migration."""
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
        self.coordinator = None

    def bind(self, coordinator) -> None:
        self.coordinator = coordinator

    def _server_value(self, camera_id: str, zone: str) -> bool | None:
        if self.coordinator is None:
            return None
        return getattr(self.coordinator.data, "zone_notifications", {}).get(camera_id, {}).get(zone)

    async def async_migrate(self) -> None:
        """Transfer existing local mutes once the server supports zone settings."""
        async with self._lock:
            migrated = False
            for camera_id, zone in tuple(self._disabled):
                if self._server_value(camera_id, zone) is None:
                    continue
                await self.coordinator.client.set_zone_notifications(camera_id, zone, False)
                updated = self._disabled - {(camera_id, zone)}
                await self._store.async_save({"disabled_zones": [list(key) for key in sorted(updated)]})
                self._disabled = updated
                migrated = True
            if migrated:
                await self.coordinator.async_request_refresh()

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
        if (camera_id, zone) in self._disabled:
            return False
        value = self._server_value(camera_id, zone)
        return value if value is not None else True

    def allows(self, camera_id: str, zones: Iterable[str]) -> bool:
        matched = tuple(zones)
        return not matched or any(self.enabled(camera_id, zone) for zone in matched)

    async def async_set(self, camera_id: str, zone: str, enabled: bool) -> None:
        async with self._lock:
            if self._server_value(camera_id, zone) is not None:
                await self.coordinator.client.set_zone_notifications(camera_id, zone, enabled)
                if (camera_id, zone) in self._disabled:
                    updated = self._disabled - {(camera_id, zone)}
                    await self._store.async_save({"disabled_zones": [list(key) for key in sorted(updated)]})
                    self._disabled = updated
                await self.coordinator.async_request_refresh()
                return
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
