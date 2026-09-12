"""Bounded SSE decoding for SurvNG's authenticated application stream."""
from __future__ import annotations

import json

from .models import SurvNGPayloadError

MAX_EVENT_BYTES = 4 * 1024 * 1024


async def decode_events(content):
    buffer = b""
    size = 0
    event_type = "message"
    event_id = ""
    data: list[str] = []
    async for chunk in content.iter_any():
        buffer += chunk
        while b"\n" in buffer:
            raw, buffer = buffer.split(b"\n", 1)
            size += len(raw) + 1
            if size > MAX_EVENT_BYTES:
                raise SurvNGPayloadError("SurvNG stream event is too large")
            try:
                line = raw.rstrip(b"\r").decode("utf-8")
            except UnicodeDecodeError as error:
                raise SurvNGPayloadError("SurvNG stream is not UTF-8") from error
            if not line:
                if data:
                    try:
                        payload = json.loads("\n".join(data))
                    except ValueError as error:
                        raise SurvNGPayloadError("SurvNG stream contains malformed JSON") from error
                    yield event_id, event_type, payload
                size, event_type, event_id, data = 0, "message", "", []
            elif not line.startswith(":"):
                field, _, value = line.partition(":")
                value = value.removeprefix(" ")
                if field == "event":
                    event_type = value
                elif field == "id" and "\x00" not in value:
                    event_id = value
                elif field == "data":
                    data.append(value)
        if size + len(buffer) > MAX_EVENT_BYTES:
            raise SurvNGPayloadError("SurvNG stream event is too large")
