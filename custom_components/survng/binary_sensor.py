"""SurvNG camera activity sensors."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from . import SurvNGConfigEntry
from .entity import SurvNGEntity
from .platform import setup_dynamic_camera_entities


async def async_setup_entry(hass, entry: SurvNGConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    mqtt = entry.runtime_data.mqtt
    unsubscribe = setup_dynamic_camera_entities(
        coordinator, async_add_entities,
        lambda camera_id: [SurvNGActivitySensor(coordinator, mqtt, camera_id, "motion"), SurvNGActivitySensor(coordinator, mqtt, camera_id, "object")],
    )
    entry.async_on_unload(unsubscribe)


class SurvNGActivitySensor(SurvNGEntity, BinarySensorEntity):
    def __init__(self, coordinator, mqtt, camera_id: str, kind: str) -> None:
        super().__init__(coordinator, camera_id)
        self.mqtt = mqtt
        self.kind = kind
        self._attr_name = kind.title()
        self._attr_unique_id = f"{camera_id}_{kind}"
        self._attr_device_class = BinarySensorDeviceClass.MOTION if kind == "motion" else BinarySensorDeviceClass.OCCUPANCY

    @property
    def is_on(self) -> bool:
        return self.mqtt.motion_active(self.camera_id) if self.kind == "motion" else self.mqtt.object_active(self.camera_id)
