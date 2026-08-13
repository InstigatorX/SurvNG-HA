from __future__ import annotations

from types import SimpleNamespace

from custom_components.survng.binary_sensor import SurvNGZoneObjectSensor


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
