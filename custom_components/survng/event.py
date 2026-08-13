"""SurvNG incident event entities and automation events."""

from __future__ import annotations

from homeassistant.components.event import EventEntity

from . import SurvNGConfigEntry
from .entity import SurvNGEntity
from .platform import setup_dynamic_camera_entities

EVENT_TYPE = "survng_incident"


async def async_setup_entry(hass, entry: SurvNGConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    mqtt = entry.runtime_data.mqtt
    entities: dict[str, SurvNGIncidentEvent] = {}

    def factory(camera_id: str):
        entity = SurvNGIncidentEvent(coordinator, mqtt, camera_id)
        entities[camera_id] = entity
        return [entity]

    unsubscribe_entities = setup_dynamic_camera_entities(coordinator, async_add_entities, factory)
    seen: dict[str, str] = {}

    def publish_incidents() -> None:
        for incident in mqtt.incidents.values():
            identity = f"{incident.incident_id}:{incident.state}:{incident.representative_event_id}"
            if seen.get(incident.incident_id) == identity:
                continue
            seen[incident.incident_id] = identity
            event_id = incident.representative_event_id
            payload = {
                "incident_id": incident.incident_id,
                "camera_id": incident.camera_id,
                "state": incident.state,
                "event_ids": list(incident.event_ids),
                "classes": list(incident.classes),
                "zones": list(incident.zones),
                "created_at": incident.created_at,
                "trigger_source": incident.trigger_source,
                "event_url": f"{entry.data['url']}/incidents?event={event_id}" if event_id else entry.data["url"] + "/incidents",
                "snapshot_url": f"{entry.data['url']}/api/events/{event_id}/snapshot.jpg" if event_id else None,
            }
            entity = entities.get(incident.camera_id)
            if entity:
                entity.emit(incident.state, payload)
            hass.bus.async_fire(EVENT_TYPE, payload)

    unsubscribe_incidents = coordinator.async_add_listener(publish_incidents)
    entry.async_on_unload(unsubscribe_entities)
    entry.async_on_unload(unsubscribe_incidents)


class SurvNGIncidentEvent(SurvNGEntity, EventEntity):
    _attr_name = "Incident"
    _attr_event_types = ["new", "updated", "complete"]

    def __init__(self, coordinator, mqtt, camera_id: str) -> None:
        super().__init__(coordinator, camera_id)
        self.mqtt = mqtt
        self._attr_unique_id = f"{camera_id}_incident"

    def emit(self, event_type: str, payload: dict) -> None:
        self._trigger_event(event_type, payload)
        self.async_write_ha_state()
