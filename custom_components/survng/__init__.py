"""SurvNG Home Assistant integration."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SurvNGApiClient
from .const import CONF_API_TOKEN, DOMAIN, PLATFORMS
from .coordinator import SurvNGCoordinator


@dataclass(slots=True)
class SurvNGRuntimeData:
    client: SurvNGApiClient
    coordinator: SurvNGCoordinator
    mqtt_unsubscribers: list


type SurvNGConfigEntry = ConfigEntry[SurvNGRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SurvNGConfigEntry) -> bool:
    client = SurvNGApiClient(
        async_get_clientsession(hass, verify_ssl=entry.data.get("verify_ssl", True)),
        entry.data[CONF_URL], entry.data.get(CONF_API_TOKEN, ""),
    )
    coordinator = SurvNGCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = SurvNGRuntimeData(client, coordinator, [])
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SurvNGConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        for unsubscribe in entry.runtime_data.mqtt_unsubscribers:
            unsubscribe()
        entry.runtime_data.mqtt_unsubscribers.clear()
    return unloaded

