"""Incident reconciliation using the v1.2/v1.3 HTTP and MQTT contracts."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

from custom_components.survng import event
from custom_components.survng.models import Incident
from custom_components.survng.mqtt import SurvNGMqttState


def test_native_incidents_publish_rich_events_and_suppress_baseline() -> None:
    native = SimpleNamespace(incidents={}, subscribe=Mock(return_value=lambda: None))
    coordinator = SimpleNamespace()
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(coordinator=coordinator, incidents=native,
                                     notification_preferences=SimpleNamespace(allows=lambda _camera, _zones: True)),
        data={"url": "https://survng.example/survng"}, entry_id="server", async_on_unload=Mock(),
    )
    hass = SimpleNamespace(bus=SimpleNamespace(async_fire=Mock()))
    with patch.object(event, "setup_dynamic_camera_entities", return_value=lambda: None):
        asyncio.run(event.async_setup_entry(hass, entry, Mock()))
    receive = native.subscribe.call_args.args[0]
    incident = Incident.from_payload({
        "incident_id": "incident-gate-8", "camera_id": "gate", "state": "new",
        "representative_event_id": 8, "event_ids": [8], "classes": ["person"],
        "revision": 1, "people": ["Alex"], "summary": "Alex detected at Gate.",
        "objects": [{"label": "person", "confidence": 0.9}],
    })
    receive(incident, False)
    hass.bus.async_fire.assert_not_called()
    receive(incident, True)
    payload = hass.bus.async_fire.call_args.args[1]
    assert payload["summary"] == "Alex detected at Gate."
    assert payload["objects"][0]["confidence"] == 0.9
    assert payload["people"] == ["Alex"]
    assert payload["notification_tag"] == "survng-server-incident-gate-8"
    assert payload["event_url"] == "https://survng.example/survng/incidents?event_ids=8"
    assert payload["reconciled"] is False


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
