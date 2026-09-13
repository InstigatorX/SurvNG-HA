"""Attachment expiry without new incidents and entry-scoped removal."""
import asyncio
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from test_native_incidents import native

from custom_components.survng import async_remove_entry
from custom_components.survng.incident_images import MAX_AGE, IncidentImages


def expire(path):
    old = time.time() - MAX_AGE - 1
    os.utime(path, (old, old))


def test_startup_and_periodic_expiry_without_notifications(tmp_path, monkeypatch):
    async def run():
        stream = native(tmp_path)
        stream._images.save("old", 1, b"old")
        old = next(tmp_path.rglob("*.jpg"))
        expire(old)
        monkeypatch.setattr("custom_components.survng.incidents.IMAGE_CLEANUP_INTERVAL", 0.01)
        stream._run = AsyncMock(side_effect=lambda: None)
        stream.start()
        try:
            for _ in range(100):
                if not old.exists():
                    break
                await asyncio.sleep(0.01)
            assert not old.exists()
            stream._images.save("recent", 1, b"recent")
            recent = next(tmp_path.rglob("*.jpg"))
            expire(recent)
            for _ in range(100):
                if not recent.exists():
                    break
                await asyncio.sleep(0.01)
            assert not recent.exists()
        finally:
            await stream.stop()
        assert stream._cleanup_task.done()
    asyncio.run(run())


def test_remove_entry_purges_only_its_attachments(tmp_path):
    async def run():
        first = IncidentImages(str(tmp_path), "first")
        second = IncidentImages(str(tmp_path), "second")
        first.save("incident", 1, b"first")
        second.save("incident", 1, b"second")
        unrelated = tmp_path / "personal.jpg"
        unrelated.write_bytes(b"personal")
        hass = SimpleNamespace(config=SimpleNamespace(media_dirs={"local": str(tmp_path)}),
                               async_add_executor_job=AsyncMock(side_effect=lambda fn: fn()))
        await async_remove_entry(hass, SimpleNamespace(entry_id="first"))
        assert not first._root.exists()
        assert len(list(second._root.glob("*.jpg"))) == 1
        assert unrelated.read_bytes() == b"personal"
        await async_remove_entry(hass, SimpleNamespace(entry_id="first"))
    asyncio.run(run())


def test_stop_drains_pending_save_before_removal(tmp_path):
    from test_native_incidents import payload

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        client = SimpleNamespace(incident_snapshot=AsyncMock(return_value=b"\xff\xd8image"))
        stream = native(tmp_path, client)

        async def executor(fn, *args):
            entered.set()
            await release.wait()
            return fn(*args)

        stream.hass.async_add_executor_job = executor
        stream.accept(payload(image_available=True))
        await asyncio.wait_for(entered.wait(), 1)
        stop = asyncio.create_task(stream.stop())
        await asyncio.sleep(0)
        assert not stop.done()
        release.set()
        await asyncio.wait_for(stop, 1)
        assert list(tmp_path.rglob("*.jpg"))
        stream.entry.runtime_data = SimpleNamespace(incidents=stream)
        await async_remove_entry(stream.hass, stream.entry)
        assert not list(tmp_path.rglob("*.jpg"))
    asyncio.run(run())
