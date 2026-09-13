"""SurvNG camera controls and zone notification switches."""

import hashlib

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from . import SurvNGConfigEntry
from .api import SurvNGError
from .entity import SurvNGEntity
from .platform import setup_dynamic_camera_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry: SurvNGConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    unsubscribe = setup_dynamic_camera_entities(
        coordinator, async_add_entities,
        lambda camera_id: [
            SurvNGCameraSwitch(coordinator, camera_id, "power"),
            SurvNGCameraSwitch(coordinator, camera_id, "recording"),
            SurvNGCameraSwitch(coordinator, camera_id, "detection"),
            SurvNGCameraSwitch(coordinator, camera_id, "incident_notifications"),
        ],
    )
    entry.async_on_unload(unsubscribe)
    known_zones: set[tuple[str, str]] = set()

    def reconcile_zones() -> None:
        additions = []
        for camera_id, zones in coordinator.data.zones.items():
            if camera_id not in coordinator.data.cameras:
                continue
            for zone in zones:
                key = (camera_id, zone)
                if key not in known_zones:
                    known_zones.add(key)
                    additions.append(SurvNGZoneNotificationSwitch(
                        coordinator, entry.runtime_data.notification_preferences, camera_id, zone,
                    ))
        if additions:
            async_add_entities(additions)

    reconcile_zones()
    entry.async_on_unload(coordinator.async_add_listener(reconcile_zones))


class SurvNGCameraSwitch(SurvNGEntity, SwitchEntity):
    def __init__(self, coordinator, camera_id: str, feature: str) -> None:
        super().__init__(coordinator, camera_id)
        self.feature = feature
        self._attr_name = "Incident notifications" if feature == "incident_notifications" else feature.title()
        if feature == "incident_notifications":
            self._attr_icon = "mdi:bell"
        self._attr_unique_id = f"{camera_id}_{feature}"

    @property
    def is_on(self) -> bool:
        camera = self.camera
        return bool(camera and {
            "power": camera.running,
            "recording": camera.recording_enabled,
            "detection": camera.detection_enabled,
            "incident_notifications": camera.incident_notifications_enabled,
        }[self.feature])

    async def _set(self, enabled: bool) -> None:
        try:
            if self.feature == "power":
                await self.coordinator.client.set_camera_power(self.camera_id, enabled)
            elif self.feature == "recording":
                await self.coordinator.client.set_recording(self.camera_id, enabled)
            elif self.feature == "incident_notifications":
                await self.coordinator.client.set_incident_notifications(self.camera_id, enabled)
            else:
                await self.coordinator.client.set_detection(self.camera_id, enabled)
            await self.coordinator.async_request_refresh()
        except SurvNGError as error:
            raise HomeAssistantError(f"Unable to change SurvNG {self.feature}") from error

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)


class SurvNGZoneNotificationSwitch(SurvNGEntity, SwitchEntity):
    _attr_icon = "mdi:bell"

    def __init__(self, coordinator, preferences, camera_id: str, zone: str) -> None:
        super().__init__(coordinator, camera_id)
        self.preferences = preferences
        self.zone = zone
        self._attr_name = f"Zone - {zone} notifications"
        # Zone names have no server ID. Hash the exact name so punctuation and
        # spacing differences do not collide, and scope to this HA config entry.
        zone_key = hashlib.sha256(zone.encode()).hexdigest()[:16]
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{camera_id}_zone_{zone_key}_notifications"

    @property
    def available(self) -> bool:
        # Removed cameras/zones become unavailable. A server-owned toggle
        # reports an API error if the server cannot accept the change.
        return (self.camera_id in self.coordinator.data.cameras
                and self.zone in self.coordinator.data.zones.get(self.camera_id, ()))

    @property
    def is_on(self) -> bool:
        return self.preferences.enabled(self.camera_id, self.zone)

    @property
    def extra_state_attributes(self) -> dict:
        return {"camera_id": self.camera_id, "zone": self.zone}

    async def _set(self, enabled: bool) -> None:
        try:
            await self.preferences.async_set(self.camera_id, self.zone, enabled)
        except (OSError, SurvNGError) as error:
            raise HomeAssistantError("Unable to save zone notification preference") from error
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
