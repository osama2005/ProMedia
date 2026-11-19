"""Persistent store for failed downloads (the Failed Downloads Center).

Failures are kept separately from the completed-download history so the
library and statistics are never polluted by attempts that never produced a
file.  The store is small, thread-safe and written atomically like history.
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from app.paths import FAILURES_FILE
from app.utils.helpers import now_iso
from app.utils.logger import log

# Errors worth retrying on their own: transient network/service conditions.
TRANSIENT_ERROR_KEYS = frozenset({"err_network", "err_rate_limit", "err_generic"})


class FailureStore:
    """Thread-safe, newest-first list of download failures."""

    def __init__(self, path: str | Path | None = None, limit: int = 200) -> None:
        self.path = Path(path) if path else FAILURES_FILE
        self.limit = max(20, int(limit))
        self._lock = threading.RLock()
        self._items: list[dict[str, Any]] = []
        self._load()

    # -- internal ---------------------------------------------------------
    def _load(self) -> None:
        with self._lock:
            try:
                if self.path.exists():
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        self._items = [item for item in data if isinstance(item, dict)]
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Could not read failures: %s", exc)
                self._items = []

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._items, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except OSError as exc:
            log.error("Could not save failures: %s", exc)

    # -- public API -------------------------------------------------------
    def add(
        self,
        *,
        title: str,
        url: str,
        error_key: str,
        error_detail: str = "",
        request: dict[str, Any] | None = None,
        attempt: int = 1,
        platform: str = "",
        priority: int = 0,
    ) -> dict[str, Any]:
        """Record a failure, updating an existing entry for the same URL."""
        if not url:
            return {}
        entry = {
            "title": title or url,
            "url": url,
            "error_key": error_key or "err_generic",
            "error_detail": error_detail[:500],
            "request": request or {},
            "attempt": max(1, int(attempt or 1)),
            "platform": platform or "",
            "priority": int(priority or 0),
            "timestamp": now_iso(),
        }
        with self._lock:
            for item in self._items:
                if item.get("url") == url:
                    item.update(entry)
                    item["id"] = item.get("id") or uuid.uuid4().hex
                    result = dict(item)
                    break
            else:
                result = {"id": uuid.uuid4().hex, **entry}
                self._items.insert(0, result)
            if len(self._items) > self.limit:
                self._items = self._items[: self.limit]
            self._save()
        return result

    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._items]

    def find_by_url(self, url: str) -> dict[str, Any] | None:
        if not url:
            return None
        with self._lock:
            for item in self._items:
                if item.get("url") == url:
                    return dict(item)
        return None

    def remove(self, entry_id: str) -> None:
        with self._lock:
            before = len(self._items)
            self._items = [item for item in self._items if item.get("id") != entry_id]
            if len(self._items) != before:
                self._save()

    def remove_by_url(self, url: str) -> None:
        if not url:
            return
        with self._lock:
            before = len(self._items)
            self._items = [item for item in self._items if item.get("url") != url]
            if len(self._items) != before:
                self._save()

    def clear(self) -> None:
        with self._lock:
            self._items = []
            self._save()

    def stats(self) -> dict[str, int]:
        with self._lock:
            items = [dict(item) for item in self._items]
        transient = sum(
            1 for item in items if item.get("error_key") in TRANSIENT_ERROR_KEYS
        )
        return {"total": len(items), "transient": transient}
