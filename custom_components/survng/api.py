"""Asynchronous client for the SurvNG HTTP API."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .models import CameraStatus, Incident, ServerStatus, StreamSource, SurvNGPayloadError
from .urls import normalize_base_url

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 24 * 1024 * 1024


class SurvNGError(Exception):
    """Base API client error."""


class SurvNGAuthError(SurvNGError):
    """Authentication or authorization failed."""


class SurvNGConnectionError(SurvNGError):
    """The server could not be reached."""


class SurvNGUnavailableError(SurvNGError):
    """The requested camera resource is temporarily unavailable."""


class SurvNGApiClient:
    """Small, state-free API boundary using Home Assistant's shared session."""

    def __init__(self, session: ClientSession, base_url: str, token: str = "") -> None:
        self._session = session
        self.base_url = normalize_base_url(base_url)
        self._token = token.strip()
        self._timeout = ClientTimeout(total=15, connect=5)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @staticmethod
    async def _read_bounded(response: ClientResponse, limit: int) -> bytes:
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.content.iter_chunked(64 * 1024):
            size += len(chunk)
            if size > limit:
                raise SurvNGPayloadError("SurvNG response is too large")
            chunks.append(chunk)
        return b"".join(chunks)

    async def _response(self, method: str, path: str, **kwargs: Any) -> ClientResponse:
        try:
            response = await self._session.request(
                method, self.url(path), headers=self.headers,
                timeout=self._timeout, **kwargs,
            )
        except (ClientError, asyncio.TimeoutError) as error:
            raise SurvNGConnectionError("Unable to connect to SurvNG") from error
        if response.status in {401, 403}:
            response.release()
            raise SurvNGAuthError("SurvNG rejected the API token or its scopes")
        if response.status == 503:
            response.release()
            raise SurvNGUnavailableError("SurvNG resource is temporarily unavailable")
        if response.status >= 400:
            status = response.status
            response.release()
            raise SurvNGError(f"SurvNG returned HTTP {status}")
        return response

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._response(method, path, **kwargs)
        try:
            body = await self._read_bounded(response, MAX_JSON_BYTES)
            return json.loads(body)
        except (ValueError, UnicodeDecodeError) as error:
            raise SurvNGPayloadError("SurvNG returned malformed JSON") from error
        finally:
            response.release()

    async def server_status(self) -> ServerStatus:
        return ServerStatus.from_payload(await self._json("GET", "/api/system/status"))

    async def cameras(self) -> list[CameraStatus]:
        payload = await self._json("GET", "/api/cameras")
        if not isinstance(payload, list):
            raise SurvNGPayloadError("camera inventory must be a list")
        return [CameraStatus.from_payload(item) for item in payload]

    async def camera_zones(self) -> dict[str, tuple[str, ...]]:
        payload = await self._json("GET", "/api/integrations/home-assistant")
        if not isinstance(payload, dict) or not isinstance(payload.get("cameras"), list):
            raise SurvNGPayloadError("integration metadata has no camera inventory")
        return {
            str(camera["id"]): tuple(
                str(zone["name"]) for zone in camera.get("zones", [])
                if isinstance(zone, dict) and zone.get("enabled", True) and zone.get("name")
            )
            for camera in payload["cameras"]
            if isinstance(camera, dict) and camera.get("id")
        }

    async def recent_incidents(self, limit: int = 20) -> tuple[Incident, ...]:
        payload = await self._json(
            "GET", "/api/incidents/feed",
            params={"event_type": "object", "limit": max(1, min(limit, 100)), "offset": 0},
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise SurvNGPayloadError("incident feed has no items")
        return tuple(Incident.from_feed_item(item) for item in payload["items"])

    async def snapshot(self, camera_id: str, source: str = "live") -> bytes:
        response = await self._response(
            "GET", f"/api/cameras/{quote(camera_id, safe='')}/snapshot.jpg",
            params={"source": source},
        )
        try:
            body = await self._read_bounded(response, MAX_IMAGE_BYTES)
            if not body:
                raise SurvNGPayloadError("SurvNG returned an empty snapshot")
            return body
        finally:
            response.release()

    async def stream_source(self, camera_id: str, source: str = "live") -> StreamSource:
        payload = await self._json(
            "GET", f"/api/cameras/{quote(camera_id, safe='')}/stream-source",
            params={"source": source},
        )
        return StreamSource.from_payload(payload)

    async def set_camera_power(self, camera_id: str, enabled: bool) -> None:
        action = "start" if enabled else "stop"
        await self._json("POST", f"/api/cameras/{quote(camera_id, safe='')}/camera/{action}")

    async def set_recording(self, camera_id: str, enabled: bool) -> None:
        await self._json("PUT", f"/api/cameras/{quote(camera_id, safe='')}/recording", json={"enabled": enabled})

    async def set_detection(self, camera_id: str, enabled: bool) -> None:
        await self._json("PUT", f"/api/cameras/{quote(camera_id, safe='')}/detection", json={"enabled": enabled})
