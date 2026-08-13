"""Constants for the SurvNG integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "survng"
PLATFORMS: Final = ["binary_sensor", "camera", "event", "sensor", "switch"]
CONF_API_TOKEN: Final = "api_token"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_MQTT_PREFIX: Final = "mqtt_prefix"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_STREAM_SOURCE: Final = "stream_source"
DEFAULT_MQTT_PREFIX: Final = "survng"
DEFAULT_SCAN_INTERVAL: Final = 30
DEFAULT_STREAM_SOURCE: Final = "live"
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 300
UPDATE_INTERVAL: Final = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

