"""Config flow for SurvNG."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_URL, CONF_VERIFY_SSL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SurvNGApiClient, SurvNGAuthError, SurvNGError
from .const import (
    CONF_API_TOKEN, CONF_MQTT_PREFIX, CONF_SCAN_INTERVAL, CONF_STREAM_SOURCE,
    DEFAULT_MQTT_PREFIX, DEFAULT_SCAN_INTERVAL, DEFAULT_STREAM_SOURCE,
    MAX_SCAN_INTERVAL, MIN_SCAN_INTERVAL, DOMAIN,
)
from .urls import normalize_base_url


class SurvNGConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return SurvNGOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input:
            try:
                url = normalize_base_url(user_input[CONF_URL])
                client = SurvNGApiClient(
                    async_get_clientsession(self.hass, verify_ssl=user_input[CONF_VERIFY_SSL]),
                    url, user_input.get(CONF_API_TOKEN, ""),
                )
                await client.server_status()
                cameras = await client.cameras()
                await self.async_set_unique_id(url.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="SurvNG", data={**user_input, CONF_URL: url},
                )
            except SurvNGAuthError:
                errors["base"] = "invalid_auth"
            except (SurvNGError, ValueError):
                errors["base"] = "cannot_connect"
        schema = vol.Schema({
            vol.Required(CONF_URL, default="http://survng.local:8088/survng"): str,
            vol.Required(CONF_API_TOKEN): str,
            vol.Required(CONF_VERIFY_SSL, default=True): bool,
            vol.Required(CONF_MQTT_PREFIX, default=DEFAULT_MQTT_PREFIX): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input:
            try:
                client = SurvNGApiClient(
                    async_get_clientsession(self.hass, verify_ssl=self._reauth_entry.data.get(CONF_VERIFY_SSL, True)),
                    self._reauth_entry.data[CONF_URL], user_input[CONF_API_TOKEN],
                )
                await client.server_status()
                return self.async_update_reload_and_abort(
                    self._reauth_entry, data_updates={CONF_API_TOKEN: user_input[CONF_API_TOKEN]},
                )
            except SurvNGAuthError:
                errors["base"] = "invalid_auth"
            except SurvNGError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): str}), errors=errors,
        )


class SurvNGOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL, default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            vol.Required(CONF_STREAM_SOURCE, default=self.config_entry.options.get(CONF_STREAM_SOURCE, DEFAULT_STREAM_SOURCE)): vol.In(["live", "main"]),
        }))
