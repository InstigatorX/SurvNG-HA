"""Optional MQTT low-latency state overlay."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .models import Incident, SurvNGPayloadError

CONF_MQTT_PREFIX = "mqtt_prefix"
DEFAULT_MQTT_PREFIX = "survng"


@dataclass(slots=True)
class SurvNGMqttState:
    motion: dict[str, bool] = field(default_factory=dict)
    objects: dict[str, tuple[str, ...]] = field(default_factory=dict)
    zones: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)
    incidents: dict[str, Incident] = field(default_factory=dict)
    incident_sequence: int = 0

    def update(self, topic: str, raw_payload: str, prefix: str = "survng") -> bool:
        try:
            payload = json.loads(raw_payload)
        except (json.JSONDecodeError, TypeError):
            return False
        if not isinstance(payload, dict):
            return False
        parts = topic.split("/")
        root = prefix.strip("/").split("/")
        if parts[:len(root)] != root:
            return False
        rest = parts[len(root):]
        if rest == ["events", "incidents"]:
            try:
                incident = Incident.from_payload(payload)
            except SurvNGPayloadError:
                return False
            previous = self.incidents.get(incident.incident_id)
            if previous == incident:
                return False
            self.incidents[incident.incident_id] = incident
            self.incident_sequence += 1
            return True
        if len(rest) == 3 and rest[0] == "camera":
            camera_id, kind = rest[1], rest[2]
            if kind == "motion":
                self.motion[camera_id] = bool(payload.get("active", payload.get("camera_id")))
                return True
            if kind == "object":
                self.objects[camera_id] = tuple(str(item) for item in payload.get("classes", []) if item)
                return True
        if len(rest) >= 4 and rest[0] == "zone" and rest[3] == "object":
            self.zones[(rest[1], rest[2])] = tuple(str(item) for item in payload.get("classes", []) if item)
            return True
        return False


async def async_subscribe_state(hass, entry, state: SurvNGMqttState, coordinator) -> list:
    """Subscribe when Home Assistant MQTT is available; HTTP still works without it."""
    try:
        from homeassistant.components import mqtt
    except ImportError:
        return []
    prefix = entry.data.get(CONF_MQTT_PREFIX, DEFAULT_MQTT_PREFIX).strip("/")

    async def receive(message: Any) -> None:
        if state.update(message.topic, message.payload, prefix):
            coordinator.async_update_listeners()

    unsubscribers = []
    for topic in (f"{prefix}/camera/+/motion", f"{prefix}/camera/+/object", f"{prefix}/zone/+/+/object", f"{prefix}/events/incidents"):
        unsubscribers.append(await mqtt.async_subscribe(hass, topic, receive, qos=0, encoding="utf-8"))
    return unsubscribers
