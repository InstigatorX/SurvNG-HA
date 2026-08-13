"""Typed SurvNG API records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


class SurvNGPayloadError(ValueError):
    """Raised when SurvNG returns an incompatible payload."""


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SurvNGPayloadError(f"{field_name} must be an object")
    return value


@dataclass(frozen=True, slots=True)
class ServerStatus:
    instance_id: str
    lifecycle: str
    uptime_seconds: float
    cpu_percent: float
    memory_bytes: int
    storage_free_bytes: int
    cameras_total: int
    cameras_online: int
    cameras_recording: int
    detector: Mapping[str, Any] = field(default_factory=dict)
    mqtt: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def unavailable(cls, cameras: Mapping[str, CameraStatus]) -> ServerStatus:
        """Represent optional server metrics without hiding camera entities."""
        values = tuple(cameras.values())
        return cls(
            instance_id="unavailable",
            lifecycle="unavailable",
            uptime_seconds=0.0,
            cpu_percent=0.0,
            memory_bytes=0,
            storage_free_bytes=0,
            cameras_total=len(values),
            cameras_online=sum(1 for camera in values if camera.running),
            cameras_recording=sum(1 for camera in values if camera.recording),
        )

    @classmethod
    def from_payload(cls, payload: object) -> ServerStatus:
        data = _mapping(payload, "system status")
        resources = _mapping(data.get("resources", {}), "resources")
        storage = _mapping(data.get("storage", {}), "storage")
        cameras = _mapping(data.get("cameras", {}), "cameras")
        instance_id = str(data.get("instance_id") or "")
        if not instance_id:
            raise SurvNGPayloadError("system status is missing instance_id")
        return cls(
            instance_id=instance_id,
            lifecycle=str(data.get("lifecycle") or "running"),
            uptime_seconds=max(0.0, float(data.get("uptime_seconds") or 0.0)),
            cpu_percent=float(resources.get("cpu_load_percent") or 0),
            memory_bytes=int(resources.get("application_memory_bytes") or 0),
            storage_free_bytes=int(storage.get("free_bytes") or 0),
            cameras_total=int(cameras.get("total") or 0),
            cameras_online=int(cameras.get("online") or 0),
            cameras_recording=int(cameras.get("recording") or 0),
            detector=_mapping(data.get("detector", {}), "detector"),
            mqtt=_mapping(data.get("mqtt", {}), "mqtt"),
        )


@dataclass(frozen=True, slots=True)
class CameraStatus:
    id: str
    name: str
    running: bool
    connected: bool
    frame_fresh: bool
    detection_enabled: bool
    recording: bool
    onvif_connected: bool
    last_motion_at: str
    raw: Mapping[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, payload: object) -> CameraStatus:
        data = _mapping(payload, "camera")
        camera_id = str(data.get("id") or "")
        if not camera_id:
            raise SurvNGPayloadError("camera is missing id")
        return cls(
            id=camera_id,
            name=str(data.get("name") or camera_id),
            running=bool(data.get("running")),
            connected=bool(data.get("connected")),
            frame_fresh=bool(data.get("frame_fresh")),
            detection_enabled=bool(data.get("detection_enabled")),
            recording=bool(data.get("recording")),
            onvif_connected=bool(data.get("onvif_connected")),
            last_motion_at=str(data.get("last_motion_at") or ""),
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class SurvNGData:
    server: ServerStatus
    cameras: Mapping[str, CameraStatus]
    zones: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    recent_incidents: tuple[Incident, ...] = ()


@dataclass(frozen=True, slots=True)
class StreamSource:
    url: str
    transport: str
    source: str

    @classmethod
    def from_payload(cls, payload: object) -> StreamSource:
        data = _mapping(payload, "stream source")
        url = str(data.get("url") or data.get("stream_url") or "")
        if not url.startswith(("rtsp://", "rtsps://")):
            raise SurvNGPayloadError("stream source has no supported RTSP URL")
        return cls(
            url=url,
            transport=str(data.get("transport") or "rtsp"),
            source=str(data.get("source") or "live"),
        )


@dataclass(frozen=True, slots=True)
class Incident:
    incident_id: str
    camera_id: str
    state: str
    event_ids: tuple[int, ...]
    representative_event_id: int | None
    classes: tuple[str, ...]
    zones: tuple[str, ...]
    created_at: str
    trigger_source: str

    @classmethod
    def from_payload(cls, payload: object) -> Incident:
        data = _mapping(payload, "incident")
        incident_id = str(data.get("incident_id") or "")
        camera_id = str(data.get("camera_id") or "")
        state = str(data.get("state") or "")
        if not incident_id or not camera_id or state not in {"new", "updated", "complete"}:
            raise SurvNGPayloadError("incident identity or lifecycle state is invalid")
        representative = data.get("representative_event_id")
        return cls(
            incident_id=incident_id,
            camera_id=camera_id,
            state=state,
            event_ids=tuple(int(value) for value in data.get("event_ids", []) if str(value).isdigit()),
            representative_event_id=int(representative) if representative is not None else None,
            classes=tuple(str(value) for value in data.get("classes", []) if value),
            zones=tuple(str(value) for value in data.get("zones", []) if value),
            created_at=str(data.get("created_at") or ""),
            trigger_source=str(data.get("trigger_source") or ""),
        )

    @classmethod
    def from_feed_item(cls, payload: object) -> Incident:
        data = _mapping(payload, "incident feed item")
        incident_id = str(data.get("incident_id") or data.get("id") or "")
        camera_id = str(data.get("camera_id") or "")
        if not incident_id or not camera_id:
            raise SurvNGPayloadError("incident feed item is missing identity")
        representative = data.get("representative_event_id")
        return cls(
            incident_id=incident_id,
            camera_id=camera_id,
            state="complete",
            event_ids=tuple(int(item.get("id")) for item in data.get("events", []) if isinstance(item, Mapping) and item.get("id")),
            representative_event_id=int(representative) if representative is not None else None,
            classes=tuple(str(value) for value in data.get("labels", []) if value),
            zones=tuple(str(value) for value in data.get("zones", []) if value),
            created_at=str(data.get("created_at") or data.get("start_at") or ""),
            trigger_source=str(data.get("trigger_source") or ""),
        )
