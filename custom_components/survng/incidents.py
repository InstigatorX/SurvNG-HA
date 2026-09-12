"""Native incident subscription, recovery, and notification image delivery."""
from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import replace

from .api import SurvNGAuthError, SurvNGError
from .incident_images import IncidentImages
from .models import Incident, SurvNGPayloadError

LOGGER = logging.getLogger(__name__)


class NativeIncidents:
    def __init__(self, hass, entry, client) -> None:
        self.hass, self.entry, self.client = hass, entry, client
        self.incidents: OrderedDict[str, Incident] = OrderedDict()
        self.connected = False
        self._cursor = ""
        self._initialized = False
        self._listeners = []
        self._task = None
        self._image_tasks: dict[str, asyncio.Task] = {}
        self._image_slots = asyncio.Semaphore(2)
        self._images = IncidentImages(hass.config.media_dirs.get("local"), entry.entry_id)
        self._image_error = False

    def subscribe(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def start(self) -> None:
        self._task = self.entry.async_create_background_task(
            self.hass, self._run(), "SurvNG incident stream", eager_start=False,
        )

    async def stop(self) -> None:
        tasks = [task for task in (self._task, *self._image_tasks.values()) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._image_tasks.clear()
        self.connected = False

    def _emit(self, incident: Incident, notify: bool) -> None:
        for listener in tuple(self._listeners):
            listener(incident, notify)

    def accept(self, payload: object, *, notify: bool = True) -> None:
        try:
            incident = Incident.from_payload(payload)
            if incident.revision <= 0:
                raise SurvNGPayloadError("native incident has no revision")
        except (TypeError, ValueError) as error:
            raise SurvNGPayloadError("native incident payload is invalid") from error
        previous = self.incidents.get(incident.incident_id)
        if previous is not None and previous.revision >= incident.revision:
            return
        details = {
            **incident.details,
            "image_url": previous.details.get("image_url") if previous else None,
            "initial_image_url": previous.details.get("initial_image_url") if previous else None,
            "final_image_url": previous.details.get("final_image_url") if previous else None,
            "image_pending": bool(incident.details.get("image_available")),
            "image_available": bool(previous and previous.details.get("image_url")),
            "delivery": "lifecycle",
        }
        incident = replace(incident, details=details)
        self.incidents[incident.incident_id] = incident
        self.incidents.move_to_end(incident.incident_id)
        while len(self.incidents) > 512:
            key, _ = self.incidents.popitem(last=False)
            task = self._image_tasks.pop(key, None)
            if task:
                task.cancel()
        self._emit(incident, notify)
        # At most one fetch per incident; catch up after each download.
        if (details["image_pending"] and incident.representative_event_id and notify
                and incident.incident_id not in self._image_tasks):
            self._image_tasks[incident.incident_id] = self.entry.async_create_background_task(
                self.hass, self._fetch_images(incident.incident_id), "SurvNG incident image", eager_start=False,
            )

    async def _download_image(self, event_id: int) -> bytes:
        for attempt in range(3):
            try:
                return await self.client.incident_snapshot(event_id)
            except SurvNGAuthError:
                raise
            except (SurvNGError, SurvNGPayloadError, OSError, TimeoutError):
                if attempt == 2:
                    raise
                await asyncio.sleep(2 if attempt == 0 else 5)
        raise AssertionError("unreachable")

    async def _fetch_images(self, key: str) -> None:
        try:
            async with self._image_slots:
                while (incident := self.incidents.get(key)) is not None:
                    if not incident.details.get("image_pending"):
                        return
                    body = await self._download_image(incident.representative_event_id)
                    url = await self.hass.async_add_executor_job(
                        self._images.save, key, incident.revision, body,
                    )
                    self._image_error = False
                    current = self.incidents.get(key)
                    if current is None:
                        return
                    details = dict(current.details)
                    # This is the first image actually delivered to HA; do not
                    # label a historical startup snapshot as the initial frame.
                    details["initial_image_url"] = details.get("initial_image_url") or url
                    if current.revision != incident.revision:
                        self.incidents[key] = replace(current, details=details)
                        continue
                    details.update(image_url=url, image_available=True, image_pending=False,
                                   final_image_url=url if current.state == "complete" else None,
                                   changed_fields=["image"], delivery="image")
                    enriched = replace(current, details=details)
                    self.incidents[key] = enriched
                    self._emit(enriched, True)
                    return
        except SurvNGAuthError:
            self.entry.async_start_reauth(self.hass)
        except (SurvNGError, SurvNGPayloadError, OSError, TimeoutError):
            if not self._image_error:
                LOGGER.warning("Incident image unavailable; text notifications remain active", exc_info=True)
                self._image_error = True
        finally:
            self._image_tasks.pop(key, None)

    async def _run(self) -> None:
        delay = 3
        reported = False
        while True:
            try:
                async for cursor, kind, payload in self.client.incident_events(self._cursor):
                    if kind == "incident_notifications_state":
                        if not isinstance(payload, dict) or payload.get("schema_version") != 2:
                            raise SurvNGPayloadError("incompatible native incident snapshot")
                        for item in payload.get("incidents", []):
                            self.accept(item, notify=self._initialized)
                        self._initialized = True
                    elif kind == "incident_lifecycle":
                        self.accept(payload)
                    elif kind == "connected":
                        if not self._initialized:
                            raise SurvNGPayloadError("SurvNG server needs native incident notification support")
                        self.connected = True
                        delay, reported = 3, False
                    # Advance only after processing, including unrelated events.
                    if cursor:
                        self._cursor = cursor
                raise SurvNGError("SurvNG event stream ended")
            except asyncio.CancelledError:
                raise
            except SurvNGAuthError:
                self.connected = False
                self.entry.async_start_reauth(self.hass)
                return
            except (SurvNGError, SurvNGPayloadError, OSError, TimeoutError):
                self.connected = False
                if not reported:
                    LOGGER.warning("Native incident stream unavailable; reconnecting", exc_info=True)
                    reported = True
                await asyncio.sleep(delay)
                delay = min(60, delay * 2)
