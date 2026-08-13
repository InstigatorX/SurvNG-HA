"""Diagnostics support with credential-safe output."""

from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_API_TOKEN


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = entry.runtime_data
    return {
        "config": async_redact_data(dict(entry.data), {CONF_API_TOKEN}),
        "options": dict(entry.options),
        "server": runtime.coordinator.data.server,
        "cameras": list(runtime.coordinator.data.cameras.values()),
    }

