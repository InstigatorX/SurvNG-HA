"""SurvNG camera activity sensors."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from . import SurvNGConfigEntry
from .entity import SurvNGEntity
from .platform import setup_dynamic_camera_entities


def _zone_slug(value: str) -> str:
    return "-".join("".join(character if character.isalnum() else " " for character in value.lower()).split()) or "zone"


async def async_setup_entry(hass, entry: SurvNGConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    mqtt = entry.runtime_data.mqtt
    unsubscribe = setup_dynamic_camera_entities(
        coordinator, async_add_entities,
        lambda camera_id: [SurvNGActivitySensor(coordinator, mqtt, camera_id, "motion"), SurvNGActivitySensor(coordinator, mqtt, camera_id, "object")],
    )
    entry.async_on_unload(unsubscribe)
    known_zones: set[tuple[str, str]] = set()

    def reconcile_zones() -> None:
        additions = []
        for camera_id, zones in coordinator.data.zones.items():
            for zone in zones:
                key = (camera_id, zone)
                if key not in known_zones:
                    known_zones.add(key)
                    additions.append(SurvNGZoneObjectSensor(coordinator, mqtt, camera_id, zone))
        if additions:
            async_add_entities(additions)

    reconcile_zones()
    entry.async_on_unload(coordinator.async_add_listener(reconcile_zones))


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


class SurvNGZoneObjectSensor(SurvNGEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator, mqtt, camera_id: str, zone: str) -> None:
        super().__init__(coordinator, camera_id)
        self.mqtt = mqtt
        self.zone = zone
        self._attr_name = f"{zone} object"
        self._attr_unique_id = f"{camera_id}_zone_{_zone_slug(zone)}_object"

    @property
    def is_on(self) -> bool:
        return self.mqtt.zone_active(self.camera_id, _zone_slug(self.zone))
