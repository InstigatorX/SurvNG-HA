"""Base SurvNG entities."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SurvNGCoordinator


class SurvNGEntity(CoordinatorEntity[SurvNGCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SurvNGCoordinator, camera_id: str | None = None) -> None:
        super().__init__(coordinator)
        self.camera_id = camera_id
        if camera_id:
            camera = coordinator.data.cameras[camera_id]
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, camera_id)}, name=camera.name,
                via_device=(DOMAIN, coordinator.config_entry.unique_id),
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, coordinator.config_entry.unique_id)}, name="SurvNG",
                manufacturer="SurvNG", model="Network video recorder",
            )

    @property
    def available(self) -> bool:
        if self.camera_id is None:
            return super().available
        return super().available and self.camera_id in self.coordinator.data.cameras

    @property
    def camera(self):
        return self.coordinator.data.cameras.get(self.camera_id)
