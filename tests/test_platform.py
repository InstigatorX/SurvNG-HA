import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


def load_platform():
    path = Path(__file__).parents[1] / "custom_components" / "survng" / "platform.py"
    spec = importlib.util.spec_from_file_location("survng_test_platform", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dynamic_camera_entities_add_once_and_preserve_removed() -> None:
    callbacks = []
    added = []
    coordinator = SimpleNamespace(
        data=SimpleNamespace(cameras={"gate": object()}),
        async_add_listener=lambda callback: callbacks.append(callback) or (lambda: None),
    )
    unsubscribe = load_platform().setup_dynamic_camera_entities(
        coordinator, added.extend, lambda camera_id: [camera_id],
    )
    assert added == ["gate"]
    coordinator.data = SimpleNamespace(cameras={"gate": object(), "yard": object()})
    callbacks[0]()
    assert added == ["gate", "yard"]
    coordinator.data = SimpleNamespace(cameras={"yard": object()})
    callbacks[0]()
    assert added == ["gate", "yard"]
    unsubscribe()
