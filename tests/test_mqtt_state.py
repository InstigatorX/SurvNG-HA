import importlib.util
from pathlib import Path
import sys


def load_mqtt():
    path = Path(__file__).parents[1] / "custom_components" / "survng" / "mqtt.py"
    spec = importlib.util.spec_from_file_location("survng_test_mqtt", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mqtt_state_accepts_only_typed_topics() -> None:
    state = load_mqtt().SurvNGMqttState()
    assert state.update("survng/camera/gate/object", '{"classes":["person","car"]}')
    assert state.objects["gate"] == ("person", "car")
    assert not state.update("survng/camera/gate/object", "not json")
    assert not state.update("other/camera/gate/object", '{}')
