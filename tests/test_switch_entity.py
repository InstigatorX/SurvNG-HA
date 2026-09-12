from types import SimpleNamespace

import pytest

from custom_components.survng.models import CameraStatus
from custom_components.survng.switch import SurvNGCameraSwitch


@pytest.mark.parametrize("enabled,recording", [(True, False), (False, True)])
def test_recording_switch_shows_desired_state(enabled, recording) -> None:
    camera = CameraStatus.from_payload({
        "id": "gate", "recording_enabled": enabled, "recording": recording,
    })
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={"gate": camera}),
        config_entry=SimpleNamespace(unique_id="server"),
    )
    assert SurvNGCameraSwitch(coordinator, "gate", "recording").is_on is enabled
