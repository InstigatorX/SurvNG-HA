"""SurvNG Home Assistant integration."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SurvNGApiClient, SurvNGAuthError, SurvNGError
from .const import CONF_API_TOKEN, PLATFORMS
from .coordinator import SurvNGCoordinator
from .incident_images import IncidentImages
from .incidents import NativeIncidents
from .mqtt import SurvNGMqttState, async_subscribe_state
from .notification_preferences import ZoneNotificationPreferences
from .repairs import update_legacy_discovery_issue


@dataclass(slots=True)
class SurvNGRuntimeData:
    client: SurvNGApiClient
    coordinator: SurvNGCoordinator
    mqtt: SurvNGMqttState
    mqtt_unsubscribers: list
    incidents: NativeIncidents
    notification_preferences: ZoneNotificationPreferences


type SurvNGConfigEntry = ConfigEntry[SurvNGRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SurvNGConfigEntry) -> bool:
    client = SurvNGApiClient(
        async_get_clientsession(hass, verify_ssl=entry.data.get("verify_ssl", True)),
        entry.data[CONF_URL], entry.data.get(CONF_API_TOKEN, ""),
    )
    coordinator = SurvNGCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    mqtt_state = SurvNGMqttState()
    notification_preferences = ZoneNotificationPreferences(hass, entry.entry_id)
    await notification_preferences.async_load()
    notification_preferences.bind(coordinator)
    try:
        await notification_preferences.async_migrate()
    except SurvNGAuthError as error:
        raise ConfigEntryAuthFailed(str(error)) from error
    except SurvNGError as error:
        raise ConfigEntryNotReady("Unable to migrate zone notification preferences") from error
    entry.runtime_data = SurvNGRuntimeData(
        client, coordinator, mqtt_state, [], NativeIncidents(hass, entry, client), notification_preferences,
    )
    update_legacy_discovery_issue(hass, entry, coordinator.data.server.mqtt)
    entry.runtime_data.mqtt_unsubscribers.extend(
        await async_subscribe_state(hass, entry, mqtt_state, coordinator)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.runtime_data.incidents.start()
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: SurvNGConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SurvNGConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.incidents.stop()
        for unsubscribe in entry.runtime_data.mqtt_unsubscribers:
            unsubscribe()
        entry.runtime_data.mqtt_unsubscribers.clear()
    return unloaded


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Normalize early development entries without changing their identity."""
    if entry.version > 1:
        return False
    data = dict(entry.data)
    data.setdefault(CONF_API_TOKEN, "")
    data.setdefault("verify_ssl", True)
    data.setdefault("mqtt_prefix", "survng")
    hass.config_entries.async_update_entry(entry, data=data, version=1)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: SurvNGConfigEntry) -> None:
    """Stop writers even if platform unload failed, then purge attachments."""
    if (runtime := getattr(entry, "runtime_data", None)) is not None:
        await runtime.incidents.stop()
    images = IncidentImages(hass.config.media_dirs.get("local"), entry.entry_id)
    await hass.async_add_executor_job(images.purge)
