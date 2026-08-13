import importlib.util
import sys
from pathlib import Path


def load_models():
    path = Path(__file__).parents[1] / "custom_components" / "survng" / "models.py"
    spec = importlib.util.spec_from_file_location("survng_test_stream_models", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_stream_descriptor_accepts_rtsp_without_exposing_extra_fields() -> None:
    descriptor = load_models().StreamSource.from_payload({
        "version": 1,
        "transport": "rtsp",
        "url": "rtsp://192.168.86.244:8554/gate_ext",
        "source": "live",
        "camera_credentials": "must be ignored",
    })
    assert descriptor.url == "rtsp://192.168.86.244:8554/gate_ext"
    assert not hasattr(descriptor, "camera_credentials")


def test_stream_descriptor_rejects_non_rtsp_transport() -> None:
    try:
        load_models().StreamSource.from_payload({"url": "http://example/live.m3u8"})
    except ValueError:
        return
    raise AssertionError("unsupported stream URL accepted")
