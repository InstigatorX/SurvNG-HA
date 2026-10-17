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


def test_zone_sensor_follows_native_zone_objects() -> None:
    state = SurvNGMqttState()
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={
            "lower-garage": SimpleNamespace(id="lower-garage", name="Lower garage", running=True),
        }),
        config_entry=SimpleNamespace(unique_id="server"),
    )
    entity = SurvNGZoneObjectSensor(coordinator, state, "lower-garage", "Driveway")
    assert entity.is_on is False
    assert state.note_zone_objects({
        "camera_id": "lower-garage",
        "zones": [{"zone": "Driveway", "classes": ["car"]}],
    })
    assert entity.is_on is True
