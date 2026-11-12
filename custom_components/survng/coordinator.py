"""SurvNG reconciliation coordinator.

Camera and server state arrive on the native event stream when the server
supports it (``state=1``). Polling then only refreshes what the stream does
not carry (zone and notification settings, the recent-incident list) on a
slow interval, and falls back to the configured interval whenever the
stream is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SurvNGApiClient, SurvNGAuthError, SurvNGError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, STREAMED_SCAN_INTERVAL
from .models import CameraStatus, ServerStatus, SurvNGData, SurvNGPayloadError

LOGGER = logging.getLogger(__name__)


def _camera_view(camera: CameraStatus) -> tuple:
    """Fields entities display; other status churn must not rewrite states."""
    return (
        camera.name, camera.running, camera.connected, camera.frame_fresh,
        camera.detection_enabled, camera.recording, camera.onvif_connected,
        camera.last_motion_at, camera.incident_notifications_enabled, camera.recording_enabled,
    )


def _server_view(server: ServerStatus) -> tuple:
    return (
        server.instance_id, server.lifecycle, round(server.uptime_seconds), server.cpu_percent,
        server.memory_bytes, server.storage_free_bytes, server.cameras_total,
        server.cameras_online, server.cameras_recording,
    )


class SurvNGCoordinator(DataUpdateCoordinator[SurvNGData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: SurvNGApiClient) -> None:
        polled = timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass, logger=LOGGER, name=DOMAIN, update_interval=polled,
        )
        self.config_entry = entry
        self.client = client
        self._polled_interval = polled
        self.state_streamed = False

    # ------------------------------------------------------- stream state
    def set_state_streamed(self, streamed: bool) -> None:
        """Switch between stream-fed state and polling camera/server status."""
        if streamed == self.state_streamed:
            return
        self.state_streamed = streamed
        self.update_interval = (
            max(self._polled_interval, STREAMED_SCAN_INTERVAL) if streamed else self._polled_interval
        )
        if not streamed:
            # Catch up on anything missed while the stream was down.
            self.hass.async_create_task(self.async_request_refresh())

    def apply_cameras(self, payload: object) -> None:
        if not isinstance(payload, list):
            raise SurvNGPayloadError("camera snapshot must be a list")
        cameras = {}
        for item in payload:
            try:
                camera = CameraStatus.from_payload(item)
            except SurvNGPayloadError:
                continue
            cameras[camera.id] = camera
        self._publish(cameras=cameras)

    def apply_camera(self, payload: object) -> None:
        camera = CameraStatus.from_payload(payload)
        cameras = dict(self.data.cameras) if self.data else {}
        cameras[camera.id] = camera
        self._publish(cameras=cameras)

    def apply_system(self, payload: object) -> None:
        server = ServerStatus.from_payload(payload)
        if self.data is not None and not server.detector:
            # The streamed summary omits detector internals; keep the last ones.
            server = replace(server, detector=self.data.server.detector)
        self._publish(server=server)

    def _publish(self, **changes) -> None:
        if self.data is None:
            return
        current = self.data
        updated = replace(current, **changes)
        changed = (
            _server_view(updated.server) != _server_view(current.server)
            or {key: _camera_view(value) for key, value in updated.cameras.items()}
            != {key: _camera_view(value) for key, value in current.cameras.items()}
        )
        # Not async_set_updated_data: that postpones the next poll, and pushes
        # every 30 seconds would then starve the settings refresh.
        self.data = updated
        if changed:
            self.async_update_listeners()

    # ---------------------------------------------------------- polling
    async def _async_update_data(self) -> SurvNGData:
        streamed = self.state_streamed and self.data is not None
        try:
            if streamed:
                cameras = list(self.data.cameras.values())
            else:
                cameras = await self.client.cameras()
            zone_notifications, incident_notifications_enabled = await self.client.notification_settings()
            zones = {camera: tuple(settings) for camera, settings in zone_notifications.items()}
            recent_incidents = await self.client.recent_incidents()
        except SurvNGAuthError:
            self.config_entry.async_start_reauth(self.hass)
            raise
        except SurvNGError as error:
            raise UpdateFailed(str(error)) from error
        camera_map = {camera.id: camera for camera in cameras}
        if streamed:
            server = self.data.server
        else:
            try:
                server = await self.client.server_status()
            except SurvNGAuthError:
                self.config_entry.async_start_reauth(self.hass)
                raise
            except SurvNGError:
                LOGGER.warning(
                    "SurvNG server metrics are unavailable; retaining camera entities"
                )
                server = ServerStatus.unavailable(camera_map)
        return SurvNGData(
            server=server,
            cameras=camera_map,
            zones=zones,
            zone_notifications=zone_notifications,
            incident_notifications_enabled=incident_notifications_enabled,
            recent_incidents=recent_incidents,
        )
