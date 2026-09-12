"""Validate the shipped blueprint and real HA notification templates."""
import asyncio
from pathlib import Path

from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA, PLATFORM_SCHEMA
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.util.yaml import load_yaml

PATH = Path(__file__).parents[1] / "blueprints/automation/survng/incident_notifications.yaml"


def test_blueprint_schema_and_attachment_updates(tmp_path):
    async def run():
        hass = HomeAssistant(str(tmp_path))
        blueprint = Blueprint(load_yaml(str(PATH)), schema=AUTOMATION_BLUEPRINT_SCHEMA, expected_domain="automation")
        inputs = BlueprintInputs(blueprint, {"use_blueprint": {
            "path": str(PATH), "input": {"notify_action": "notify.mobile_app_test"},
        }})
        inputs.validate()
        PLATFORM_SCHEMA(inputs.async_substitute())
        raw = load_yaml(str(PATH))
        template = Template(raw["actions"][0]["variables"]["notification_data"], hass)
        base = {"state": "new", "delivery": "lifecycle", "notification_tag": "incident-41"}
        first = template.async_render({"incident": base, "destination": "/lovelace"})
        assert first["tag"] == "incident-41"
        assert "image" not in first
        assert first["push"]["sound"] == "default"
        image = template.async_render({
            "incident": {**base, "delivery": "image", "image_url": "/media/local/41-1.jpg"},
            "destination": "/lovelace",
        })
        assert image["tag"] == first["tag"]
        assert image["image"] == "/media/local/41-1.jpg"
        assert image["push"]["sound"] == "none"
        assert image["alert_once"] is True
        condition = Template(raw["conditions"][0]["value_template"], hass)
        variables = {"selected_cameras": "gate", "selected_classes": "person,car",
                     "selected_states": ["new", "updated", "complete"]}
        trigger = {"event": {"data": {**base, "camera_id": "gate", "classes": ["person"]}}}
        assert condition.async_render({**variables, "trigger": trigger}) is True
        trigger["event"]["data"]["reconciled"] = True
        assert condition.async_render({**variables, "trigger": trigger}) is False
        await hass.async_block_till_done()
    asyncio.run(run())
