import importlib.util
from pathlib import Path
import sys


def load_module(name: str):
    path = Path(__file__).parents[1] / "custom_components" / "survng" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"survng_test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


models = load_module("models")
urls = load_module("urls")
CameraStatus = models.CameraStatus
ServerStatus = models.ServerStatus
StreamSource = models.StreamSource
normalize_base_url = urls.normalize_base_url


def test_normalize_base_url_preserves_subpath() -> None:
    assert normalize_base_url("https://ha.example/survng/") == "https://ha.example/survng"


def test_typed_contracts() -> None:
    camera = CameraStatus.from_payload({"id": "gate", "name": "Gate", "running": True, "frame_fresh": True})
    server = ServerStatus.from_payload({"instance_id": "abc", "resources": {"cpu_load_percent": 4.2, "application_memory_bytes": 9}, "storage": {"free_bytes": 10}, "cameras": {"total": 1, "online": 1, "recording": 1}})
    stream = StreamSource.from_payload({"url": "rtsp://go2rtc:8554/gate", "source": "live"})
    assert camera.id == "gate" and server.cameras_online == 1 and stream.transport == "rtsp"


def test_credentials_in_url_are_rejected() -> None:
    try:
        normalize_base_url("https://user:secret@example/survng")
    except ValueError:
        return
    raise AssertionError("embedded credentials accepted")
