"""SurvNG reconciliation coordinator."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SurvNGApiClient, SurvNGAuthError, SurvNGError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import SurvNGData


class SurvNGCoordinator(DataUpdateCoordinator[SurvNGData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: SurvNGApiClient) -> None:
        super().__init__(
            hass, logger=__import__("logging").getLogger(__name__), name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.config_entry = entry
        self.client = client

    async def _async_update_data(self) -> SurvNGData:
        try:
            server = await self.client.server_status()
            cameras = await self.client.cameras()
        except SurvNGAuthError:
            self.config_entry.async_start_reauth(self.hass)
            raise
        except SurvNGError as error:
            raise UpdateFailed(str(error)) from error
        return SurvNGData(server=server, cameras={camera.id: camera for camera in cameras})

