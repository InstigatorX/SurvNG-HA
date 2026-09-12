"""SurvNG clean camera images."""

from __future__ import annotations

import logging

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.exceptions import HomeAssistantError

from . import SurvNGConfigEntry
from .api import SurvNGError
from .const import CONF_STREAM_SOURCE, DEFAULT_STREAM_SOURCE
from .entity import SurvNGEntity
from .models import SurvNGPayloadError
from .platform import setup_dynamic_camera_entities

PARALLEL_UPDATES = 0
LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry: SurvNGConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    unsubscribe = setup_dynamic_camera_entities(
        coordinator, async_add_entities,
        lambda camera_id: [SurvNGCamera(coordinator, camera_id)],
    )
    entry.async_on_unload(unsubscribe)


class SurvNGCamera(SurvNGEntity, Camera):
    _attr_name = None
    _attr_is_streaming = True
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator, camera_id: str) -> None:
        Camera.__init__(self)
        SurvNGEntity.__init__(self, coordinator, camera_id)
        self._attr_unique_id = camera_id
        self._stream_source_failed = False

    @property
    def available(self) -> bool:
        camera = self.camera
        return super().available and bool(camera and camera.running)

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        del width, height  # SurvNG supplies the clean native snapshot.
        source = self.coordinator.config_entry.options.get(CONF_STREAM_SOURCE, DEFAULT_STREAM_SOURCE)
        try:
            return await self.coordinator.client.snapshot(self.camera_id, source)
        except SurvNGError as error:
            raise HomeAssistantError("Unable to retrieve the SurvNG snapshot") from error

    async def stream_source(self) -> str | None:
        """Return a fresh internal stream descriptor for each playback request."""
        source = self.coordinator.config_entry.options.get(CONF_STREAM_SOURCE, DEFAULT_STREAM_SOURCE)
        try:
            descriptor = await self.coordinator.client.stream_source(self.camera_id, source)
        except (SurvNGError, SurvNGPayloadError) as error:
            # HA also calls this during registration to discover WebRTC providers.
            # A temporary RTSP failure must not abort registration (and snapshots).
            if not self._stream_source_failed:
                LOGGER.warning(
                    "Stream source unavailable for camera %s (%s); "
                    "camera remains registered and playback will retry",
                    self.camera_id, type(error).__name__,
                )
                self._stream_source_failed = True
            return None
        self._stream_source_failed = False
        return descriptor.url
