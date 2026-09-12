from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.camera import CameraEntityFeature

from custom_components.survng.api import SurvNGAuthError, SurvNGConnectionError, SurvNGUnavailableError
from custom_components.survng.camera import SurvNGCamera
from custom_components.survng.models import SurvNGPayloadError


def test_camera_initializes_home_assistant_camera_state() -> None:
    camera_status = SimpleNamespace(id="gate", name="Gate", running=True)
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={"gate": camera_status}),
        config_entry=SimpleNamespace(unique_id="server", options={}),
    )

    entity = SurvNGCamera(coordinator, "gate")

    assert entity.access_tokens
    assert entity.unique_id == "gate"
    assert entity.has_entity_name
    assert entity.name is None
    assert entity.device_info["name"] == "Gate"
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


@pytest.mark.parametrize("error_type", [
    SurvNGUnavailableError, SurvNGConnectionError, SurvNGAuthError, SurvNGPayloadError,
])
def test_camera_registration_survives_stream_outage_and_playback_recovers(caplog, error_type) -> None:
    import asyncio
    from unittest.mock import Mock, patch

    from homeassistant.components.camera.webrtc import DATA_WEBRTC_PROVIDERS
    from homeassistant.helpers.entity import Entity

    async def run():
        camera_id = "back-left"
        client = SimpleNamespace(
            stream_source=AsyncMock(side_effect=error_type("stream unavailable")),
            snapshot=AsyncMock(return_value=b"jpeg-image"),
        )
        coordinator = SimpleNamespace(
            last_update_success=True,
            data=SimpleNamespace(cameras={
                camera_id: SimpleNamespace(id=camera_id, name="Back-Left", running=True),
            }),
            config_entry=SimpleNamespace(unique_id="server", options={}),
            client=client,
        )
        entity = SurvNGCamera(coordinator, camera_id)
        provider = Mock()
        entity.hass = SimpleNamespace(data={DATA_WEBRTC_PROVIDERS: [provider]})
        # Exercise Camera's real registration hook and WebRTC source discovery.
        with patch.object(Entity, "async_internal_added_to_hass", new=AsyncMock()):
            await entity.async_internal_added_to_hass()
        assert entity.available
        assert await entity.async_camera_image() == b"jpeg-image"
        assert await entity.stream_source() is None
        assert sum("back-left" in record.message for record in caplog.records) == 1

        client.stream_source.side_effect = None
        client.stream_source.return_value = SimpleNamespace(url="rtsp://restream:8554/back_left")
        assert await entity.stream_source() == "rtsp://restream:8554/back_left"
        await entity.async_refresh_providers(write_state=False)
        provider.async_is_supported.assert_called_once_with("rtsp://restream:8554/back_left")

    asyncio.run(run())
