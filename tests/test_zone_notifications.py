"""Zone mute persistence, switch discovery, and notification delivery gates."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.survng import event, switch
from custom_components.survng.models import Incident
from custom_components.survng.notification_preferences import ZoneNotificationPreferences
from custom_components.survng.switch import SurvNGZoneNotificationSwitch


def coordinator():
    return SimpleNamespace(
        data=SimpleNamespace(cameras={"gate": SimpleNamespace(name="Gate")}, zones={"gate": ("Porch",)}),
        config_entry=SimpleNamespace(entry_id="server", unique_id="server"),
        async_add_listener=Mock(return_value=lambda: None), client=Mock(),
    )


def test_preferences_survive_reload_and_scope_same_named_zones_to_camera(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        preferences = ZoneNotificationPreferences(hass, "server")
        await preferences.async_load()
        assert preferences.enabled("gate", "Porch")
        await asyncio.gather(preferences.async_set("gate", "Porch", False),
                             preferences.async_set("garage", "Driveway", False))
        reloaded = ZoneNotificationPreferences(hass, "server")
        await reloaded.async_load()
        assert not reloaded.enabled("gate", "Porch")
        assert not reloaded.enabled("garage", "Driveway")
        assert reloaded.enabled("garage", "Porch")
        assert reloaded.allows("gate", [])  # No zone is independently allowed.
        assert not reloaded.allows("gate", ["Porch"])
        assert reloaded.allows("gate", ["Porch", "Driveway"])
        await reloaded.async_set("gate", "Porch", True)
        assert reloaded.allows("gate", ["Porch"])
        other_server = ZoneNotificationPreferences(hass, "another-server")
        await other_server.async_load()
        assert other_server.enabled("garage", "Driveway")
        await hass.async_block_till_done()
    asyncio.run(run())


def test_zone_switch_changes_only_local_preference_and_keeps_distinct_names(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        preferences = ZoneNotificationPreferences(hass, "server")
        coord = coordinator()
        entity = SurvNGZoneNotificationSwitch(coord, preferences, "gate", "Porch")
        assert entity.name == "Zone - Porch notifications"
        assert entity.is_on and entity.available
        assert entity.extra_state_attributes == {"camera_id": "gate", "zone": "Porch"}
        with patch.object(entity, "async_write_ha_state") as write:
            await entity.async_turn_off()
            assert not entity.is_on
            await entity.async_turn_on()
            assert entity.is_on
            assert write.call_count == 2
        assert not coord.client.mock_calls
        coord.data.zones = {"gate": ()}
        assert not entity.available
        coord.data.zones = {"gate": ("Porch",)}
        assert entity.available
        first = SurvNGZoneNotificationSwitch(coord, preferences, "gate", "Front Drive")
        second = SurvNGZoneNotificationSwitch(coord, preferences, "gate", "Front-Drive")
        assert first.unique_id != second.unique_id
        await hass.async_block_till_done()
    asyncio.run(run())


def test_zone_switch_adds_new_zones_once():
    async def run():
        coord = coordinator()
        callbacks = []
        coord.async_add_listener = lambda cb: callbacks.append(cb) or (lambda: None)
        preferences = SimpleNamespace(enabled=lambda _camera, _zone: True)
        entry = SimpleNamespace(runtime_data=SimpleNamespace(coordinator=coord, notification_preferences=preferences),
                                async_on_unload=Mock())
        added = []
        await switch.async_setup_entry(None, entry, added.extend)
        assert len([entity for entity in added if isinstance(entity, SurvNGZoneNotificationSwitch)]) == 1
        coord.data.zones["gate"] = ("Porch", "Driveway")
        for _ in range(2):
            for cb in callbacks:
                cb()
        zones = [entity.zone for entity in added if isinstance(entity, SurvNGZoneNotificationSwitch)]
        assert zones == ["Porch", "Driveway"]
    asyncio.run(run())


def test_disabled_zone_suppresses_bus_but_preserves_entity_and_rechecks_image(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        preferences = ZoneNotificationPreferences(hass, "server")
        native = SimpleNamespace(incidents={}, subscribe=Mock(return_value=lambda: None))
        entry = SimpleNamespace(
            runtime_data=SimpleNamespace(coordinator=coordinator(), incidents=native,
                                         notification_preferences=preferences),
            data={"url": "https://survng.example/survng"}, entry_id="server", async_on_unload=Mock(),
        )
        fake_hass = SimpleNamespace(bus=SimpleNamespace(async_fire=Mock()))
        entity = Mock()
        def setup(_coordinator, _add, factory):
            factory("gate")
            return lambda: None
        with patch.object(event, "setup_dynamic_camera_entities", side_effect=setup), patch.object(
            event, "SurvNGIncidentEvent", return_value=entity,
        ):
            await event.async_setup_entry(fake_hass, entry, Mock())
        receive = native.subscribe.call_args.args[0]
        def incident(state="new", zones=("Porch",), delivery="lifecycle"):
            item = Incident.from_payload({"incident_id": "incident-gate-41", "camera_id": "gate", "state": state,
                                          "zones": list(zones), "revision": 1, "classes": ["person"]})
            return replace(item, details={"delivery": delivery})
        receive(incident(), True)
        assert fake_hass.bus.async_fire.call_count == 1
        await preferences.async_set("gate", "Porch", False)
        for stage in ("new", "updated", "complete"):
            for delivery in ("lifecycle", "image"):
                receive(incident(stage, delivery=delivery), True)
        assert fake_hass.bus.async_fire.call_count == 1
        assert entity.emit.call_count == 7
        assert entity.emit.call_args.args[1]["notifications_enabled"] is False
        receive(incident(zones=("Porch", "Driveway")), True)
        assert fake_hass.bus.async_fire.call_count == 2
        receive(incident(zones=()), True)
        assert fake_hass.bus.async_fire.call_count == 3
        await preferences.async_set("gate", "Porch", True)
        # Switching on does not replay historical notifications by itself.
        assert fake_hass.bus.async_fire.call_count == 3
        receive(incident("complete"), True)
        assert fake_hass.bus.async_fire.call_count == 4
        await hass.async_block_till_done()
    asyncio.run(run())


def test_failed_save_does_not_change_in_memory_preference(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        preferences = ZoneNotificationPreferences(hass, "server")
        entity = SurvNGZoneNotificationSwitch(coordinator(), preferences, "gate", "Porch")
        with patch.object(preferences._store, "async_save", new=AsyncMock(side_effect=OSError("disk full"))), \
             patch.object(entity, "async_write_ha_state") as write:
            with pytest.raises(HomeAssistantError):
                await entity.async_turn_off()
            assert entity.is_on
            write.assert_not_called()
        await hass.async_block_till_done()
    asyncio.run(run())
