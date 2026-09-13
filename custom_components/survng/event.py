"""SurvNG incident event entities and automation events."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.event import EventEntity

from . import SurvNGConfigEntry
from .entity import SurvNGEntity
from .platform import setup_dynamic_camera_entities

EVENT_TYPE = "survng_incident"


async def async_setup_entry(hass, entry: SurvNGConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    native = entry.runtime_data.incidents
    preferences = entry.runtime_data.notification_preferences
    entities: dict[str, SurvNGIncidentEvent] = {}

    def factory(camera_id: str):
        entity = SurvNGIncidentEvent(coordinator, native, camera_id)
        entities[camera_id] = entity
        latest = next((item for item in reversed(list(native.incidents.values())) if item.camera_id == camera_id), None)
        if latest is not None:
            entity.emit(latest.state, {
                **latest.event_data(entry.data["url"]), "reconciled": True,
                "notifications_enabled": latest.details.get("notifications_enabled", True)
                and preferences.allows(latest.camera_id, latest.zones),
            })
        return [entity]

    unsubscribe_entities = setup_dynamic_camera_entities(coordinator, async_add_entities, factory)

    def publish_incident(incident, notify: bool) -> None:
        payload = incident.event_data(entry.data["url"])
        payload["server_id"] = entry.entry_id
        payload["notification_tag"] = f"survng-{entry.entry_id}-{incident.incident_id}"
        payload["reconciled"] = not notify
        payload["notifications_enabled"] = incident.details.get("notifications_enabled", True) and preferences.allows(
            incident.camera_id, incident.zones,
        )
        entity = entities.get(incident.camera_id)
        if entity:
            entity.emit(incident.state, payload)
        if notify and payload["notifications_enabled"]:
            hass.bus.async_fire(EVENT_TYPE, payload)

    unsubscribe_incidents = native.subscribe(publish_incident)
    for incident in native.incidents.values():
        publish_incident(incident, False)
    entry.async_on_unload(unsubscribe_entities)
    entry.async_on_unload(unsubscribe_incidents)


class SurvNGIncidentEvent(SurvNGEntity, EventEntity):
    _attr_name = "Incident"
    _attr_translation_key = "incident"
    _attr_event_types: ClassVar[list[str]] = ["new", "updated", "complete"]

    def __init__(self, coordinator, native, camera_id: str) -> None:
        super().__init__(coordinator, camera_id)
        self._attr_unique_id = f"{camera_id}_incident"

    def emit(self, event_type: str, payload: dict) -> None:
        self._trigger_event(event_type, payload)
        # Initial reconciliation can run before async_add_entities registers us.
        if self.hass is not None and self.entity_id is not None:
            self.async_write_ha_state()
