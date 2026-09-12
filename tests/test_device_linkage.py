"""Device registration must not pass the removed identifier-based via_device."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.survng.entity import SurvNGEntity


def test_camera_registration_links_by_registry_id_after_device_creation() -> None:
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={
            "back-left": SimpleNamespace(name="Back-Left"),
        }),
        config_entry=SimpleNamespace(unique_id="https://survng.example", entry_id="entry"),
    )
    entity = SurvNGEntity(coordinator, "back-left")
    assert "via_device" not in entity.device_info
    assert entity.device_info["identifiers"] == {("survng", "back-left")}
    entity.hass = SimpleNamespace()
    entity.device_entry = SimpleNamespace(id="camera-registry-id", via_device_id=None)
    registry = Mock()
    # An explicit signature rejects any deprecated via_device argument.
    def register_server(*, config_entry_id, identifiers, name, manufacturer, model):
        assert config_entry_id == "entry"
        assert identifiers == {("survng", "https://survng.example")}
        return SimpleNamespace(id="server-registry-id")
    registry.async_get_or_create.side_effect = register_server

    with patch.object(CoordinatorEntity, "async_added_to_hass", new=AsyncMock()), patch(
        "custom_components.survng.entity.dr.async_get", return_value=registry
    ):
        asyncio.run(entity.async_added_to_hass())
    registry.async_update_device.assert_called_once_with(
        "camera-registry-id", via_device_id="server-registry-id",
    )


def test_real_registry_registers_multiple_camera_devices_without_deprecated_fields(tmp_path) -> None:
    from types import MappingProxyType

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry as dr

    async def run():
        hass = HomeAssistant(str(tmp_path))
        entry = ConfigEntry(
            domain="survng", title="SurvNG", version=1, minor_version=1,
            data={}, options={}, source="user", unique_id="server",
            discovery_keys=MappingProxyType({}), subentries_data=[],
        )
        hass.config_entries = SimpleNamespace(async_get_entry=lambda entry_id: entry)
        registry = dr.DeviceRegistry(hass)
        await registry.async_load()
        coordinator = SimpleNamespace(
            data=SimpleNamespace(cameras={
                camera_id: SimpleNamespace(name=camera_id)
                for camera_id in ("gate", "back-left", "back-middle")
            }),
            config_entry=entry,
        )
        with patch.object(CoordinatorEntity, "async_added_to_hass", new=AsyncMock()), patch(
            "custom_components.survng.entity.dr.async_get", return_value=registry
        ), patch.object(dr, "report_usage", side_effect=AssertionError("deprecated device field")):
            for camera_id in coordinator.data.cameras:
                entity = SurvNGEntity(coordinator, camera_id)
                entity.hass = hass
                # This is the same device creation call EntityPlatform makes.
                device = registry.async_get_or_create(
                    config_entry_id=entry.entry_id, **entity.device_info,
                )
                entity.device_entry = device
                await entity.async_added_to_hass()
                linked = registry.async_get(device.id)
                server = registry.async_get(linked.via_device_id)
                assert server.identifiers == {("survng", "server")}
                assert linked.identifiers == {("survng", camera_id)}
        await hass.async_block_till_done()

    asyncio.run(run())
