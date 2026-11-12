"""Optional MQTT low-latency state overlay."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any

from .models import Incident, SurvNGPayloadError

CONF_MQTT_PREFIX = "mqtt_prefix"
DEFAULT_MQTT_PREFIX = "survng"


def zone_slug(value: str) -> str:
    return "-".join(
        "".join(character if character.isalnum() else " " for character in value.lower()).split()
    ) or "zone"


def _zone_observed_at(payload: dict) -> datetime | None:
    raw = payload.get("timestamp") or payload.get("created_at")
    if not raw:
        return None
    try:
        observed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    return observed.astimezone(UTC)


@dataclass(slots=True)
class SurvNGMqttState:
    motion: dict[str, bool] = field(default_factory=dict)
    objects: dict[str, tuple[str, ...]] = field(default_factory=dict)
    zones: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)
    zone_until: dict[tuple[str, str], float] = field(default_factory=dict)
    occupancy_zones: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)
    occupancy_until: dict[tuple[str, str], float] = field(default_factory=dict)
    incidents: dict[str, Incident] = field(default_factory=dict)
    incident_sequence: int = 0
    motion_until: dict[str, float] = field(default_factory=dict)
    object_until: dict[str, float] = field(default_factory=dict)

    def motion_active(self, camera_id: str, now: float | None = None) -> bool:
        return self.motion.get(camera_id, False) and self.motion_until.get(camera_id, 0) > (now or time.monotonic())

    def object_active(self, camera_id: str, now: float | None = None) -> bool:
        return bool(self.objects.get(camera_id)) and self.object_until.get(camera_id, 0) > (now or time.monotonic())

    def zone_active(self, camera_id: str, zone_slug: str, now: float | None = None) -> bool:
        key = (camera_id, zone_slug)
        moment = now or time.monotonic()
        if key in self.occupancy_zones and self.occupancy_until.get(key, 0) > moment:
            return True
        return bool(self.zones.get(key)) and self.zone_until.get(key, 0) > moment

    def note_zone_occupancy(self, payload: object, now: float | None = None, *, live: bool = False) -> bool:
        """Replace one camera's occupied zones from a snapshot.

        Listed zones are on. Omitted zones are off. Every snapshot refreshes
        the fail-safe, including one whose occupied set did not change.
        MQTT topic holds are left untouched.
        """
        if not isinstance(payload, dict):
            return False
        camera_id = str(payload.get("camera_id") or "")
        zones = payload.get("zones")
        if not camera_id or not isinstance(zones, list):
            return False
        try:
            delay = float(payload.get("fail_safe_seconds") or 240)
        except (TypeError, ValueError):
            delay = 240.0
        if delay <= 0:
            delay = 240.0
        observed = _zone_observed_at(payload)
        if (
            not live
            and observed is not None
            and (datetime.now(UTC) - observed).total_seconds() > delay
        ):
            return False
        listed: dict[tuple[str, str], tuple[str, ...]] = {}
        for item in zones:
            if not isinstance(item, dict):
                continue
            name = str(item.get("zone") or "")
            classes = tuple(str(label) for label in item.get("classes", []) if label)
            if not name or not classes:
                continue
            listed[(camera_id, zone_slug(name))] = classes
        for key in [key for key in self.occupancy_zones if key[0] == camera_id]:
            if key not in listed:
                self.occupancy_zones.pop(key, None)
                self.occupancy_until.pop(key, None)
        expiry = (now or time.monotonic()) + delay
        for key, classes in listed.items():
            self.occupancy_zones[key] = classes
            self.occupancy_until[key] = expiry
        return True

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
                self.motion_until[camera_id] = time.monotonic() + 10
                return True
            if kind == "object":
                self.objects[camera_id] = tuple(str(item) for item in payload.get("classes", []) if item)
                self.object_until[camera_id] = time.monotonic() + 15
                return True
        if len(rest) >= 4 and rest[0] == "zone" and rest[3] == "object":
            key = (rest[1], rest[2])
            self.zones[key] = tuple(str(item) for item in payload.get("classes", []) if item)
            self.zone_until[key] = time.monotonic() + 15
            return True
        return False


async def async_subscribe_state(hass, entry, state: SurvNGMqttState, coordinator) -> list:
    """Subscribe when Home Assistant MQTT is available; HTTP still works without it."""
    if "mqtt" not in hass.config.components:
        return []
    try:
        from homeassistant.components import mqtt
    except ImportError:
        return []
    prefix = entry.data.get(CONF_MQTT_PREFIX, DEFAULT_MQTT_PREFIX).strip("/")

    from homeassistant.core import callback
    from homeassistant.helpers.event import async_call_later
    expiry_cancellers: dict[str, Any] = {}

    @callback
    def expire(_now, topic: str) -> None:
        expiry_cancellers.pop(topic, None)
        coordinator.async_update_listeners()

    @callback
    def receive(message: Any) -> None:
        if state.update(message.topic, message.payload, prefix):
            coordinator.async_update_listeners()
            if message.topic.endswith("/motion") or message.topic.endswith("/object"):
                existing = expiry_cancellers.pop(message.topic, None)
                if existing:
                    existing()
                delay = 10 if message.topic.endswith("/motion") else 15
                expiry_cancellers[message.topic] = async_call_later(
                    hass, delay, partial(expire, topic=message.topic),
                )

    unsubscribers = []
    for topic in (f"{prefix}/camera/+/motion", f"{prefix}/camera/+/object", f"{prefix}/zone/+/+/object"):
        unsubscribers.append(await mqtt.async_subscribe(hass, topic, receive, qos=0, encoding="utf-8"))
    unsubscribers.append(lambda: [cancel() for cancel in tuple(expiry_cancellers.values())])
    return unsubscribers
