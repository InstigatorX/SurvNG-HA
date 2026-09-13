from types import SimpleNamespace

import pytest

from custom_components.survng.models import CameraStatus
from custom_components.survng.switch import SurvNGCameraSwitch


@pytest.mark.parametrize("enabled,recording", [(True, False), (False, True)])
def test_recording_switch_shows_desired_state(enabled, recording) -> None:
    camera = CameraStatus.from_payload({
        "id": "gate", "recording_enabled": enabled, "recording": recording,
    })
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={"gate": camera}),
        config_entry=SimpleNamespace(unique_id="server"),
    )
    assert SurvNGCameraSwitch(coordinator, "gate", "recording").is_on is enabled


@pytest.mark.parametrize("enabled", [True, False])
def test_incident_notification_switch_reads_and_updates_server(enabled):
    import asyncio
    from unittest.mock import AsyncMock
    camera = CameraStatus.from_payload({"id": "gate", "incident_notifications_enabled": enabled})
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={"gate": camera}),
        config_entry=SimpleNamespace(unique_id="server"),
        client=SimpleNamespace(set_incident_notifications=AsyncMock()),
        async_request_refresh=AsyncMock(),
    )
    switch = SurvNGCameraSwitch(coordinator, "gate", "incident_notifications")
    assert switch.is_on is enabled
    asyncio.run(switch.async_turn_off() if enabled else switch.async_turn_on())
    coordinator.client.set_incident_notifications.assert_awaited_once_with("gate", not enabled)
    coordinator.async_request_refresh.assert_awaited_once()
