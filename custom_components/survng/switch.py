"""SurvNG camera controls."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from . import SurvNGConfigEntry
from .api import SurvNGError
from .entity import SurvNGEntity
from .platform import setup_dynamic_camera_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry: SurvNGConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    unsubscribe = setup_dynamic_camera_entities(
        coordinator, async_add_entities,
        lambda camera_id: [
            SurvNGCameraSwitch(coordinator, camera_id, "power"),
            SurvNGCameraSwitch(coordinator, camera_id, "recording"),
            SurvNGCameraSwitch(coordinator, camera_id, "detection"),
        ],
    )
    entry.async_on_unload(unsubscribe)


class SurvNGCameraSwitch(SurvNGEntity, SwitchEntity):
    def __init__(self, coordinator, camera_id: str, feature: str) -> None:
        super().__init__(coordinator, camera_id)
        self.feature = feature
        self._attr_name = feature.title()
        self._attr_unique_id = f"{camera_id}_{feature}"

    @property
    def is_on(self) -> bool:
        camera = self.camera
        return bool(camera and {
            "power": camera.running,
            "recording": camera.recording,
            "detection": camera.detection_enabled,
        }[self.feature])

    async def _set(self, enabled: bool) -> None:
        try:
            if self.feature == "power":
                await self.coordinator.client.set_camera_power(self.camera_id, enabled)
            elif self.feature == "recording":
                await self.coordinator.client.set_recording(self.camera_id, enabled)
            else:
                await self.coordinator.client.set_detection(self.camera_id, enabled)
            await self.coordinator.async_request_refresh()
        except SurvNGError as error:
            raise HomeAssistantError(f"Unable to change SurvNG {self.feature}") from error

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
