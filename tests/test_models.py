import importlib.util
import sys
from pathlib import Path


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
Incident = models.Incident
normalize_base_url = urls.normalize_base_url
require_secure_transport = urls.require_secure_transport


def test_normalize_base_url_preserves_subpath() -> None:
    assert normalize_base_url("https://ha.example/survng/") == "https://ha.example/survng"


def test_http_requires_explicit_insecure_transport_opt_in() -> None:
    try:
        require_secure_transport("http://survng.local:8088/survng", False)
    except ValueError as error:
        assert "HTTPS is required" in str(error)
    else:
        raise AssertionError("HTTP was accepted without an explicit opt-in")
    assert require_secure_transport("http://survng.local:8088/survng", True) == "http://survng.local:8088/survng"


def test_typed_contracts() -> None:
    camera = CameraStatus.from_payload({"id": "gate", "name": "Gate", "running": True, "frame_fresh": True})
    server = ServerStatus.from_payload({"instance_id": "abc", "lifecycle": "running", "uptime_seconds": 12.5, "resources": {"cpu_load_percent": 4.2, "application_memory_bytes": 9}, "storage": {"free_bytes": 10}, "cameras": {"total": 1, "online": 1, "recording": 1}})
    stream = StreamSource.from_payload({"url": "rtsp://go2rtc:8554/gate", "source": "live"})
    assert camera.id == "gate" and server.cameras_online == 1 and stream.transport == "rtsp"
    assert server.lifecycle == "running" and server.uptime_seconds == 12.5


def test_server_status_fallback_preserves_camera_counts() -> None:
    cameras = {
        "gate": CameraStatus.from_payload({
            "id": "gate", "name": "Gate", "running": True, "recording": True,
        }),
        "yard": CameraStatus.from_payload({
            "id": "yard", "name": "Yard", "running": False, "recording": False,
        }),
    }

    status = ServerStatus.unavailable(cameras)

    assert status.instance_id == "unavailable"
    assert status.cameras_total == 2
    assert status.cameras_online == 1
    assert status.cameras_recording == 1


def test_credentials_in_url_are_rejected() -> None:
    try:
        normalize_base_url("https://user:secret@example/survng")
    except ValueError:
        return
    raise AssertionError("embedded credentials accepted")


def test_incident_feed_item_maps_to_updated_lifecycle() -> None:
    incident = Incident.from_feed_item({
        "incident_id": "gate-1", "camera_id": "gate", "representative_event_id": 9,
        "events": [{"id": 8}, {"id": 9}], "labels": ["car"], "zones": ["Driveway"],
    })
    assert incident.state == "updated" and incident.event_ids == (8, 9)


def test_incident_feed_prefers_mqtt_compatible_identity_and_start_time() -> None:
    incident = Incident.from_feed_item({
        "id": "incident-gate-8", "incident_id": "gate-8", "camera_id": "gate",
        "start_at": "2026-09-12T12:00:00Z", "created_at": "2026-09-12T12:00:10Z",
    })
    assert incident.incident_id == "incident-gate-8"
    assert incident.created_at == "2026-09-12T12:00:00Z"


def test_legacy_recording_status_fallback() -> None:
    assert CameraStatus.from_payload({"id": "gate", "recording": True}).recording_enabled


def test_incident_notification_link_uses_public_url_with_private_api_fallback():
    item = Incident.from_payload({
        "incident_id": "incident-gate-41", "camera_id": "gate", "state": "updated",
        "representative_event_id": 41,
        "event_url": "https://ha.loebees.com/survng/incidents?event_ids=41",
    })
    assert item.event_data("http://192.168.1.2:8088")["event_url"] == (
        "https://ha.loebees.com/survng/incidents?event_ids=41"
    )
    legacy = Incident.from_payload({
        "incident_id": "incident-gate-41", "camera_id": "gate", "state": "new",
        "representative_event_id": 41,
    })
    assert legacy.event_data("http://192.168.1.2:8088")["event_url"] == (
        "http://192.168.1.2:8088/incidents?event_ids=41"
    )


def test_stable_incident_path_uses_configured_api_prefix_without_public_override():
    item = Incident.from_payload({
        "incident_id": "incident-gate-41", "camera_id": "gate", "state": "complete",
        "representative_event_id": 99, "incident_path": "/incidents/incident-gate-41",
        "event_url": "/survng/incidents/incident-gate-41",
    })
    assert item.event_data("https://ha.example/survng")["event_url"] == (
        "https://ha.example/survng/incidents/incident-gate-41"
    )
