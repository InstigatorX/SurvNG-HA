"""SurvNG server and camera sensors."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import UnitOfInformation

from . import SurvNGConfigEntry
from .entity import SurvNGEntity


@dataclass(frozen=True, kw_only=True)
class SurvNGServerSensorDescription(SensorEntityDescription):
    value_fn: Callable[[object], object]


SERVER_SENSORS = (
    SurvNGServerSensorDescription(key="cpu", name="CPU", native_unit_of_measurement="%", value_fn=lambda s: s.cpu_percent),
    SurvNGServerSensorDescription(key="memory", name="Memory", native_unit_of_measurement=UnitOfInformation.BYTES, value_fn=lambda s: s.memory_bytes),
    SurvNGServerSensorDescription(key="storage_free", name="Storage free", native_unit_of_measurement=UnitOfInformation.BYTES, value_fn=lambda s: s.storage_free_bytes),
    SurvNGServerSensorDescription(key="cameras_online", name="Cameras online", value_fn=lambda s: s.cameras_online),
)


async def async_setup_entry(hass, entry: SurvNGConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([SurvNGServerSensor(coordinator, item) for item in SERVER_SENSORS])
    from .platform import setup_dynamic_camera_entities
    unsubscribe = setup_dynamic_camera_entities(
        coordinator, async_add_entities,
        lambda camera_id: [SurvNGLastObjects(coordinator, entry.runtime_data.mqtt, camera_id)],
    )
    entry.async_on_unload(unsubscribe)


class SurvNGServerSensor(SurvNGEntity, SensorEntity):
    def __init__(self, coordinator, description) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{description.key}"

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data.server)


class SurvNGLastObjects(SurvNGEntity, SensorEntity):
    _attr_name = "Last objects"

    def __init__(self, coordinator, mqtt, camera_id: str) -> None:
        super().__init__(coordinator, camera_id)
        self.mqtt = mqtt
        self._attr_unique_id = f"{camera_id}_last_objects"

    @property
    def native_value(self):
        return ", ".join(self.mqtt.objects.get(self.camera_id, ())) or None
