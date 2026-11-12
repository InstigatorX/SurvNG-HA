from __future__ import annotations

from types import SimpleNamespace

from custom_components.survng.binary_sensor import SurvNGZoneObjectSensor
from custom_components.survng.mqtt import SurvNGMqttState


def test_zone_entity_name_uses_zone_prefix() -> None:
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={
            "gate": SimpleNamespace(id="gate", name="Gate", running=True),
        }),
        config_entry=SimpleNamespace(unique_id="server"),
    )

    entity = SurvNGZoneObjectSensor(
        coordinator,
        SimpleNamespace(),
        "gate",
        "Front Drive",
    )

    assert entity.name == "Zone - Front Drive"
    assert entity.unique_id == "gate_zone_front-drive_object"


def test_zone_sensor_follows_native_zone_occupancy_snapshots() -> None:
    state = SurvNGMqttState()
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={
            "lower-garage": SimpleNamespace(id="lower-garage", name="Lower garage", running=True),
        }),
        config_entry=SimpleNamespace(unique_id="server"),
    )
    entity = SurvNGZoneObjectSensor(coordinator, state, "lower-garage", "Driveway")
    assert entity.is_on is False
    assert state.note_zone_occupancy({
        "camera_id": "lower-garage",
        "fail_safe_seconds": 240,
        "zones": [{"zone": "Driveway", "classes": ["car"]}],
    }, live=True)
    assert entity.is_on is True
    # A snapshot that omits the zone clears it.
    state.note_zone_occupancy({"camera_id": "lower-garage", "zones": []}, live=True)
    assert entity.is_on is False
