from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.components.camera import CameraEntityFeature

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
    assert entity.supported_features & CameraEntityFeature.STREAM


def test_camera_exposes_home_assistant_stream_hook() -> None:
    camera_status = SimpleNamespace(id="gate", name="Gate", running=True)
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={"gate": camera_status}),
        config_entry=SimpleNamespace(unique_id="server", options={}),
        client=SimpleNamespace(stream_source=AsyncMock(return_value=SimpleNamespace(
            url="rtsp://192.168.86.243:8554/gate_ext",
        ))),
    )
    entity = SurvNGCamera(coordinator, "gate")

    import asyncio
    assert asyncio.run(entity.stream_source()) == "rtsp://192.168.86.243:8554/gate_ext"
