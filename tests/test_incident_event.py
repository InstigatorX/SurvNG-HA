"""Incident reconciliation using the v1.2/v1.3 HTTP and MQTT contracts."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

from custom_components.survng import event
from custom_components.survng.models import Incident
from custom_components.survng.mqtt import SurvNGMqttState


def test_http_reconciliation_preserves_mqtt_lifecycle_and_links() -> None:
    feed = Incident.from_feed_item({
        "id": "incident-gate-8", "incident_id": "gate-8", "camera_id": "gate",
        "representative_event_id": 9, "events": [{"id": 8}, {"id": 9}],
        "labels": ["car"], "start_at": "2026-09-12T12:00:00Z",
    })
    mqtt = SurvNGMqttState()
    current = Incident.from_payload({
        "incident_id": "incident-gate-8", "camera_id": "gate", "state": "new",
        "representative_event_id": 8, "event_ids": [8], "classes": ["car"],
        "started_at": "2026-09-12T12:00:00Z",
    })
    mqtt.incidents[current.incident_id] = current
    coordinator = SimpleNamespace(
        data=SimpleNamespace(recent_incidents=(feed,)),
        async_add_listener=Mock(return_value=lambda: None),
    )
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(coordinator=coordinator, mqtt=mqtt),
        data={"url": "https://survng.example/survng"}, async_on_unload=Mock(),
    )
    hass = SimpleNamespace(bus=SimpleNamespace(async_fire=Mock()))
    with patch.object(event, "setup_dynamic_camera_entities", return_value=lambda: None):
        asyncio.run(event.async_setup_entry(hass, entry, Mock()))
    payload = hass.bus.async_fire.call_args.args[1]
    assert hass.bus.async_fire.call_count == 1
    assert payload["state"] == "new"
    assert payload["incident_id"] == feed.incident_id
    assert payload["created_at"] == "2026-09-12T12:00:00Z"
    assert payload["representative_event_id"] == 8
    assert payload["event_url"] == "https://survng.example/survng/incidents?event_ids=8"

    refresh = coordinator.async_add_listener.call_args.args[0]
    refresh()
    assert hass.bus.async_fire.call_count == 1
    mqtt.incidents[current.incident_id] = Incident.from_payload({
        "incident_id": current.incident_id, "camera_id": "gate", "state": "complete",
        "representative_event_id": 9, "event_ids": [8, 9], "classes": ["car"],
    })
    refresh()
    assert hass.bus.async_fire.call_args.args[1]["state"] == "complete"
    assert hass.bus.async_fire.call_count == 2


def test_http_only_reconciliation_does_not_claim_completion() -> None:
    feed = Incident.from_feed_item({
        "id": "incident-gate-8", "incident_id": "gate-8", "camera_id": "gate",
        "representative_event_id": 8, "events": [{"id": 8}],
    })
    assert feed.state == "updated"


def test_initial_incident_before_entity_registration_does_not_write_state() -> None:
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={"gate": SimpleNamespace(name="Gate")}),
        config_entry=SimpleNamespace(unique_id="server"),
    )
    entity = event.SurvNGIncidentEvent(coordinator, SurvNGMqttState(), "gate")
    with patch.object(entity, "async_write_ha_state") as write:
        entity.emit("updated", {"incident_id": "incident-gate-8"})
    write.assert_not_called()
