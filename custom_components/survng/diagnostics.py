"""Diagnostics support with credential-safe output."""

from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_API_TOKEN


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = entry.runtime_data
    data = runtime.coordinator.data
    return {
        "config": async_redact_data(dict(entry.data), {CONF_API_TOKEN}),
        "options": dict(entry.options),
        "server": {
            "cpu_percent": data.server.cpu_percent,
            "memory_bytes": data.server.memory_bytes,
            "storage_free_bytes": data.server.storage_free_bytes,
            "cameras_total": data.server.cameras_total,
            "cameras_online": data.server.cameras_online,
            "cameras_recording": data.server.cameras_recording,
        },
        "cameras": [{
            "id": camera.id,
            "name": camera.name,
            "running": camera.running,
            "connected": camera.connected,
            "frame_fresh": camera.frame_fresh,
            "recording": camera.recording,
            "detection_enabled": camera.detection_enabled,
            "onvif_connected": camera.onvif_connected,
        } for camera in data.cameras.values()],
    }
