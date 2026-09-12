"""Base SurvNG entities."""

from homeassistant.helpers import device_registry as dr
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
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, coordinator.config_entry.unique_id)}, name="SurvNG",
                manufacturer="SurvNG", model="Network video recorder",
            )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.camera_id is None:
            return
        registry = dr.async_get(self.hass)
        server = registry.async_get_or_create(
            config_entry_id=self.coordinator.config_entry.entry_id,
            identifiers={(DOMAIN, self.coordinator.config_entry.unique_id)},
            name="SurvNG", manufacturer="SurvNG", model="Network video recorder",
        )
        # Entity registration has already resolved this camera's device.
        # async_update_device accepts registry IDs on both old and new HA versions.
        if self.device_entry is not None and self.device_entry.via_device_id != server.id:
            registry.async_update_device(self.device_entry.id, via_device_id=server.id)

    @property
    def available(self) -> bool:
        if self.camera_id is None:
            return super().available
        return super().available and self.camera_id in self.coordinator.data.cameras

    @property
    def camera(self):
        return self.coordinator.data.cameras.get(self.camera_id)
