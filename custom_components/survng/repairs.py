"""Actionable SurvNG repair issues."""

from collections.abc import Mapping
from typing import Any

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

ISSUE_LEGACY_DISCOVERY = "legacy_mqtt_discovery"


def update_legacy_discovery_issue(hass, entry, mqtt_status: Mapping[str, Any]) -> None:
    if mqtt_status.get("enabled") and mqtt_status.get("discovery_enabled"):
        ir.async_create_issue(
            hass, DOMAIN, ISSUE_LEGACY_DISCOVERY,
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_LEGACY_DISCOVERY,
            translation_placeholders={"entry_title": entry.title},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_LEGACY_DISCOVERY)
