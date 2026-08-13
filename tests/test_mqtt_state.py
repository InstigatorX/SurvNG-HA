import importlib.util
import sys
from pathlib import Path


def load_mqtt():
    package = "custom_components.survng"
    if package not in sys.modules:
        import types
        module = types.ModuleType(package)
        module.__path__ = [str(Path(__file__).parents[1] / "custom_components" / "survng")]
        sys.modules[package] = module
    path = Path(__file__).parents[1] / "custom_components" / "survng" / "mqtt.py"
    spec = importlib.util.spec_from_file_location(f"{package}.mqtt_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mqtt_state_accepts_only_typed_topics() -> None:
    state = load_mqtt().SurvNGMqttState()
    assert state.update("survng/camera/gate/object", '{"classes":["person","car"]}')
    assert state.objects["gate"] == ("person", "car")
    assert state.object_active("gate")
    assert not state.object_active("gate", now=state.object_until["gate"] + 1)
    assert not state.update("survng/camera/gate/object", "not json")
    assert not state.update("other/camera/gate/object", '{}')


def test_incident_updates_are_deduplicated() -> None:
    state = load_mqtt().SurvNGMqttState()
    payload = '{"incident_id":"incident-gate-1","camera_id":"gate","state":"new","event_ids":[1],"representative_event_id":1,"classes":["car"]}'
    assert state.update("survng/events/incidents", payload)
    assert not state.update("survng/events/incidents", payload)
    assert state.incident_sequence == 1
    assert state.incidents["incident-gate-1"].classes == ("car",)


def test_zone_activity_expires() -> None:
    state = load_mqtt().SurvNGMqttState()
    assert state.update("survng/zone/gate/front-drive/object", '{"classes":["car"]}')
    assert state.zone_active("gate", "front-drive")
    assert not state.zone_active("gate", "front-drive", now=state.zone_until[("gate", "front-drive")] + 1)
