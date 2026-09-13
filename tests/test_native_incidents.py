"""Native delivery without MQTT, including replay, images, and cancellation."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.survng.api import SurvNGAuthError, SurvNGConnectionError
from custom_components.survng.event_stream import decode_events
from custom_components.survng.incidents import NativeIncidents
from custom_components.survng.models import SurvNGPayloadError


def payload(revision=1, state="new", **changes):
    return {"incident_id": "incident-gate-41", "camera_id": "gate", "state": state,
            "revision": revision, "representative_event_id": 41, "event_ids": [41],
            "summary": "Person detected at Gate.", **changes}


def native(tmp_path, client=None):
    hass = SimpleNamespace(config=SimpleNamespace(media_dirs={"local": str(tmp_path)}),
                           async_add_executor_job=AsyncMock(side_effect=lambda fn, *args: fn(*args)))
    entry = SimpleNamespace(entry_id="server", async_start_reauth=Mock(),
                            async_create_background_task=lambda _hass, coro, _name, **_kwargs: asyncio.create_task(coro))
    return NativeIncidents(hass, entry, client or SimpleNamespace())


def test_images_revisions_and_duplicate_suppression(tmp_path):
    async def run():
        client = SimpleNamespace(incident_snapshot=AsyncMock(return_value=b"\xff\xd8first"))
        stream = native(tmp_path, client)
        received = []
        stream.subscribe(lambda item, notify: received.append((item, notify)))
        stream.accept(payload(image_available=True))
        assert received[0][0].details["image_pending"]
        assert received[0][0].details["image_url"] is None
        await asyncio.gather(*stream._image_tasks.values())
        initial = received[-1][0].details["image_url"]
        assert initial.startswith("/media/local/survng/")
        assert received[-1][0].details["initial_image_url"] == initial
        stream.accept(payload(image_available=True))  # duplicate replay
        assert len(received) == 2
        client.incident_snapshot.return_value = b"\xff\xd8final"
        stream.accept(payload(2, "complete", image_available=True, people=["Alex"]))
        await asyncio.gather(*stream._image_tasks.values())
        final = received[-1][0]
        assert final.details["initial_image_url"] == initial
        assert final.details["final_image_url"] != initial
        assert final.details["people"] == ["Alex"]
        assert final.state == "complete"
        assert len(list(tmp_path.rglob("*.jpg"))) == 2
        await stream.stop()
    asyncio.run(run())


def test_reconnect_uses_cursor_and_does_not_realert_replayed_revision(tmp_path):
    async def run():
        calls, received = [], []
        done = asyncio.Event()
        async def events(cursor):
            calls.append(cursor)
            if len(calls) == 1:
                yield "", "incident_notifications_state", {"schema_version": 2, "incidents": [payload()]}
                yield "boot:10", "connected", {}
                yield "boot:11", "incident_lifecycle", payload(2, "updated", people=["Alex"])
                raise SurvNGConnectionError("disconnected")
            yield "boot:11", "incident_lifecycle", payload(2, "updated", people=["Alex"])
            yield "boot:12", "incident_lifecycle", payload(3, "complete")
            done.set()
            await asyncio.Future()
        stream = native(tmp_path, SimpleNamespace(incident_events=events))
        stream.subscribe(lambda item, notify: received.append((item.revision, notify)))
        with patch("custom_components.survng.incidents.asyncio.sleep", new=AsyncMock()):
            stream.start()
            await asyncio.wait_for(done.wait(), 1)
            await stream.stop()
        assert calls == ["", "boot:11"]
        assert received == [(1, False), (2, True), (3, True)]
        assert not stream.connected
    asyncio.run(run())


def test_server_restart_snapshot_recovers_missed_completion(tmp_path):
    async def run():
        calls, received = [], []
        done = asyncio.Event()
        async def events(cursor):
            calls.append(cursor)
            yield "", "incident_notifications_state", {
                "schema_version": 2, "incidents": [payload(len(calls), "new" if len(calls) == 1 else "complete")],
            }
            yield f"boot{len(calls)}:1", "connected", {}
            if len(calls) == 1:
                raise SurvNGConnectionError("restart")
            done.set()
            await asyncio.Future()
        stream = native(tmp_path, SimpleNamespace(incident_events=events))
        stream.subscribe(lambda item, notify: received.append((item.state, notify)))
        with patch("custom_components.survng.incidents.asyncio.sleep", new=AsyncMock()):
            stream.start()
            await asyncio.wait_for(done.wait(), 1)
            await stream.stop()
        assert received == [("new", False), ("complete", True)]
    asyncio.run(run())


def test_auth_failure_requests_reauth_and_stops(tmp_path):
    async def run():
        async def events(_cursor):
            raise SurvNGAuthError("expired")
            yield  # make this an async generator
        stream = native(tmp_path, SimpleNamespace(incident_events=events))
        await stream._run()
        stream.entry.async_start_reauth.assert_called_once_with(stream.hass)
        assert not stream.connected
    asyncio.run(run())


def test_malformed_revision_is_a_payload_error(tmp_path):
    with pytest.raises(SurvNGPayloadError):
        native(tmp_path).accept(payload("bad"))


def test_sse_chunk_boundaries_comments_and_multiline():
    async def run():
        async def chunks():
            for chunk in (b": heartbeat\n\nid: boot:1\nevent: incident_life", b'cycle\ndata: {"name":\r\n',
                          b'data: "Al', 'éx"}\n\n'.encode()):
                yield chunk
        result = [event async for event in decode_events(SimpleNamespace(iter_any=chunks))]
        assert result == [("boot:1", "incident_lifecycle", {"name": "Aléx"})]
    asyncio.run(run())


def test_sse_rejects_oversized_and_invalid_data():
    async def run(body):
        async def chunks():
            yield body
        return [item async for item in decode_events(SimpleNamespace(iter_any=chunks))]
    with pytest.raises(SurvNGPayloadError):
        asyncio.run(run(b"data: not json\n\n"))
    with patch("custom_components.survng.event_stream.MAX_EVENT_BYTES", 10), pytest.raises(SurvNGPayloadError):
        asyncio.run(run(b"data: " + b"x" * 11))


def test_image_transient_failure_retries_without_losing_text(tmp_path):
    async def run():
        client = SimpleNamespace(incident_snapshot=AsyncMock(side_effect=[
            SurvNGConnectionError("not ready"), b"\xff\xd8ready",
        ]))
        stream = native(tmp_path, client)
        received = []
        stream.subscribe(lambda item, _notify: received.append(item))
        with patch("custom_components.survng.incidents.asyncio.sleep", new=AsyncMock()):
            stream.accept(payload(image_available=True))
            assert received[0].details["summary"] == "Person detected at Gate."
            await asyncio.gather(*stream._image_tasks.values())
        assert client.incident_snapshot.await_count == 2
        assert received[-1].details["image_available"]
        await stream.stop()
    asyncio.run(run())


def test_image_diagnostics_track_download_save_and_delivery(tmp_path):
    async def run():
        release = asyncio.Event()
        async def download(_event_id):
            await release.wait()
            return b"\xff\xd8image"
        stream = native(tmp_path, SimpleNamespace(incident_snapshot=download))
        stream.accept(payload(image_available=True))
        assert stream.image_diagnostics()["active_jobs"][0]["stage"] == "queued"
        await asyncio.sleep(0)
        assert stream.image_diagnostics()["active_jobs"][0]["stage"] == "downloading"
        release.set()
        await asyncio.gather(*stream._image_tasks.values())
        diagnostics = stream.image_diagnostics()
        assert diagnostics["counts"] == {"queued": 1, "downloaded": 1, "saved": 1, "delivered": 1, "failed": 0}
        assert diagnostics["active_jobs"] == []
        assert diagnostics["pending_incidents"] == 0
    asyncio.run(run())


def test_image_diagnostics_record_auth_storage_and_unexpected_failures(tmp_path):
    async def run():
        for error, stage in ((SurvNGAuthError("secret token"), "downloading"),
                             (PermissionError(13, "private path"), "saving"),
                             (RuntimeError("sensitive response"), "downloading")):
            client = SimpleNamespace(incident_snapshot=AsyncMock(return_value=b"\xff\xd8image"))
            stream = native(tmp_path, client)
            if stage == "saving":
                stream._images.save = Mock(side_effect=error)
            else:
                client.incident_snapshot.side_effect = error
            stream.accept(payload(image_available=True))
            outcomes = await asyncio.gather(*stream._image_tasks.values(), return_exceptions=True)
            diagnostic = stream.image_diagnostics()
            assert diagnostic["last_failure"]["stage"] == stage
            assert diagnostic["last_failure"]["error_type"] == type(error).__name__
            assert diagnostic["counts"]["failed"] == 1
            assert diagnostic["active_jobs"] == []
            assert str(error) not in str(diagnostic)
            if isinstance(error, SurvNGAuthError):
                stream.entry.async_start_reauth.assert_called_once()
            if isinstance(error, RuntimeError):
                assert outcomes == [error]  # Unexpected bugs remain visible to HA.
    asyncio.run(run())


def test_webp_evidence_uses_jpeg_thumbnail_for_notification_delivery(tmp_path):
    """The original snapshot route preserves WebP; the thumbnail route converts it."""
    from custom_components.survng.api import SurvNGApiClient

    async def run():
        responses = []
        async def request(_method, url, **kwargs):
            body = b"RIFF\x00\x00\x00\x00WEBP" if url.endswith("/snapshot.jpg") else b"\xff\xd8converted"
            async def chunks(_size):
                yield body
            response = SimpleNamespace(status=200, content=SimpleNamespace(iter_chunked=chunks), release=Mock())
            responses.append(response)
            return response
        session = SimpleNamespace(request=AsyncMock(side_effect=request))
        client = SurvNGApiClient(session, "https://survng.example/prefix", "test-token")
        stream = native(tmp_path, client)
        received = []
        stream.subscribe(lambda item, _notify: received.append(item))
        stream.accept(payload(image_available=True))
        await asyncio.gather(*stream._image_tasks.values())
        session.request.assert_awaited_once()
        args, kwargs = session.request.call_args
        assert args == ("GET", "https://survng.example/prefix/api/events/41/thumbnail.jpg")
        assert kwargs["headers"] == {"Authorization": "Bearer test-token"}
        assert kwargs["params"] == {"width": 1280, "quality": 85}
        assert received[-1].details["delivery"] == "image"
        assert received[-1].details["image_url"].endswith(".jpg")
        assert next(tmp_path.rglob("*.jpg")).read_bytes() == b"\xff\xd8converted"
        responses[0].release.assert_called_once()
    asyncio.run(run())
