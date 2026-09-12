"""Revision-specific notification attachments in authenticated HA media storage."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path

MAX_FILES = 512
MAX_BYTES = 128 * 1024 * 1024
MAX_AGE = 7 * 24 * 60 * 60


class IncidentImages:
    def __init__(self, media_dir: str | None, entry_id: str) -> None:
        self._lock = threading.Lock()
        self._namespace = hashlib.sha256(entry_id.encode()).hexdigest()[:16]
        self._root = Path(media_dir) / "survng" / self._namespace if media_dir else None

    def save(self, incident_id: str, revision: int, body: bytes) -> str:
        with self._lock:
            return self._save(incident_id, revision, body)

    def _save(self, incident_id: str, revision: int, body: bytes) -> str:
        if self._root is None:
            raise OSError("Home Assistant local media directory is not configured")
        self._root.mkdir(parents=True, exist_ok=True)
        extension = "png" if body.startswith(b"\x89PNG\r\n\x1a\n") else "jpg"
        name = f"{hashlib.sha256(incident_id.encode()).hexdigest()[:24]}-{revision}.{extension}"
        target = self._root / name
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(body)
        os.replace(temporary, target)
        files = sorted((*self._root.glob("*.jpg"), *self._root.glob("*.png")), key=lambda path: path.stat().st_mtime, reverse=True)
        total = 0
        for index, path in enumerate(files):
            stat = path.stat()
            total += stat.st_size
            if index >= MAX_FILES or total > MAX_BYTES or time.time() - stat.st_mtime > MAX_AGE:
                path.unlink(missing_ok=True)
        return f"/media/local/survng/{self._namespace}/{name}"
