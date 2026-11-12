"""Camera and server state from the native stream instead of polling."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.survng.const import STREAMED_SCAN_INTERVAL
from custom_components.survng.coordinator import SurvNGCoordinator
from custom_components.survng.models import (
    CameraStatus,
    ServerStatus,
    SurvNGData,
    SurvNGPayloadError,
)


def camera(**changes):
    return {"id": "gate", "name": "Gate", "running": True, "connected": True,
            "frame_fresh": True, "detection_enabled": True, "recording": True,
            "onvif_connected": True, "last_motion_at": "", "recording_enabled": True,
            "incident_notifications_enabled": True, **changes}


def system(**changes):
    return {"instance_id": "server-1", "lifecycle": "running", "uptime_seconds": 60,
            "resources": {"cpu_load_percent": 10, "application_memory_bytes": 100},
            "storage": {"free_bytes": 1000},
            "cameras": {"total": 1, "online": 1, "recording": 1},
            "mqtt": {"enabled": False}, **changes}


def coordinator(client=None) -> SurvNGCoordinator:
    """A coordinator without a running Home Assistant instance."""
    item = object.__new__(SurvNGCoordinator)
    item.hass = SimpleNamespace(async_create_task=Mock(side_effect=lambda coro: coro.close()))
    item.client = client or SimpleNamespace()
    item.config_entry = SimpleNamespace(async_start_reauth=Mock())
    item._polled_interval = timedelta(seconds=30)
    item.update_interval = item._polled_interval
    item.state_streamed = False
    item.async_update_listeners = Mock()
    item.async_request_refresh = AsyncMock()
    item.data = SurvNGData(
        server=ServerStatus.from_payload({**system(), "detector": {"ready": True}}),
        cameras={"gate": CameraStatus.from_payload(camera())},
        zones={"gate": ("Driveway",)},
    )
    return item


def test_streamed_camera_change_updates_entities_only_for_displayed_fields():
    item = coordinator()

    item.apply_camera(camera(onvif_notifications_received=41))  # counter churn
    item.async_update_listeners.assert_not_called()
    assert item.data.cameras["gate"].raw["onvif_notifications_received"] == 41

    item.apply_camera(camera(recording=False))
    item.async_update_listeners.assert_called_once()
    assert item.data.cameras["gate"].recording is False
    assert item.data.zones == {"gate": ("Driveway",)}  # settings untouched


def test_camera_snapshot_replaces_inventory_and_skips_malformed_items():
    item = coordinator()

    item.apply_cameras([camera(id="drive", name="Drive"), {"name": "no id"}])

    assert list(item.data.cameras) == ["drive"]
    item.async_update_listeners.assert_called_once()
    with pytest.raises(SurvNGPayloadError):
        item.apply_cameras({"not": "a list"})


def test_streamed_system_state_keeps_detector_and_switches_polling():
    item = coordinator()

    item.apply_system(system(uptime_seconds=90))
    item.set_state_streamed(True)

    assert item.data.server.uptime_seconds == 90
    assert item.data.server.detector == {"ready": True}
    item.async_update_listeners.assert_called_once()
    assert item.update_interval == STREAMED_SCAN_INTERVAL

    item.set_state_streamed(False)
    assert item.update_interval == timedelta(seconds=30)
    item.hass.async_create_task.assert_called_once()  # catch-up refresh


def test_streamed_poll_refreshes_only_settings_and_incidents():
    client = SimpleNamespace(
        cameras=AsyncMock(side_effect=AssertionError("cameras are streamed")),
        server_status=AsyncMock(side_effect=AssertionError("server is streamed")),
        notification_settings=AsyncMock(return_value=({"gate": {"Road": True}}, False)),
        recent_incidents=AsyncMock(return_value=()),
    )
    item = coordinator(client)
    item.set_state_streamed(True)

    data = asyncio.run(item._async_update_data())

    assert data.zones == {"gate": ("Road",)}
    assert data.incident_notifications_enabled is False
    assert list(data.cameras) == ["gate"]  # kept from the stream, not refetched
    assert data.server == item.data.server
