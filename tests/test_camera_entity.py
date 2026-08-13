from __future__ import annotations

from types import SimpleNamespace

from custom_components.survng.camera import SurvNGCamera


def test_camera_initializes_home_assistant_camera_state() -> None:
    camera_status = SimpleNamespace(id="gate", name="Gate", running=True)
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={"gate": camera_status}),
        config_entry=SimpleNamespace(unique_id="server", options={}),
    )

    entity = SurvNGCamera(coordinator, "gate")

    assert entity.access_tokens
    assert entity.unique_id == "gate"
    assert entity.name == "Gate"
