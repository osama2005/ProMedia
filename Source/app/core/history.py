"""Download history persisted as a JSON list."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.paths import HISTORY_FILE
from app.utils.hash import normalize_sha256
from app.utils.helpers import now_iso
from app.utils.logger import log

# Integrity states stored per history entry.  Older files default to
# ``unchecked`` so no existing download is silently marked as verified.
HASH_STATUSES = ("unchecked", "pending", "verified", "match", "mismatch", "missing", "error")


def _entry_date(value: object) -> date | None:
    """Parse a history timestamp into a local date; None when unusable."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value)).date()
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


class HistoryStore:
    """Thread-safe, newest-first download history."""

    def __init__(self, path: str | Path | None = None, limit: int = 500) -> None:
        self.path = Path(path) if path else HISTORY_FILE
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
                        # Older history files predate favorites/tags and SHA-256:
                        # fill in defaults so every consumer can rely on them.
                        for item in self._items:
                            item["favorite"] = bool(item.get("favorite"))
                            raw_tags = item.get("tags") or []
                            item["tags"] = (
                                [str(tag) for tag in raw_tags]
                                if isinstance(raw_tags, list) else []
                            )
                            item["sha256"] = normalize_sha256(item.get("sha256") or "")
                            item["hash_expected"] = normalize_sha256(
                                item.get("hash_expected") or ""
                            )
                            status = str(item.get("hash_status") or "unchecked")
                            item["hash_status"] = (
                                status if status in HASH_STATUSES else "unchecked"
                            )
                            item["hash_checked_at"] = str(item.get("hash_checked_at") or "")
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Could not read history: %s", exc)
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
            log.error("Could not save history: %s", exc)

    # -- public API -------------------------------------------------------
    def add(
        self,
        title: str,
        url: str,
        filepath: str,
        size: int | None,
        platform: str,
        thumbnail: str | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": uuid.uuid4().hex,
            "title": title or filepath,
            "url": url,
            "filepath": filepath,
            "size": int(size) if size else 0,
            "platform": platform or "",
            "thumbnail": thumbnail or "",
            "favorite": False,
            "tags": [],
            "sha256": "",
            "hash_expected": "",
            "hash_status": "unchecked",
            "hash_checked_at": "",
            "timestamp": now_iso(),
        }
        with self._lock:
            self._items.insert(0, entry)
            if len(self._items) > self.limit:
                self._items = self._items[: self.limit]
            self._save()
        return entry

    @staticmethod
    def _copy(item: dict[str, Any]) -> dict[str, Any]:
        """Return a copy whose mutable tag list is never shared with callers."""
        result = dict(item)
        result["tags"] = list(item.get("tags") or [])
        return result

    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._copy(item) for item in self._items]

    def find_by_url(self, url: str) -> dict[str, Any] | None:
        """Return the newest history item for *url*, if any."""
        if not url:
            return None
        with self._lock:
            for item in self._items:
                if item.get("url") == url:
                    return self._copy(item)
        return None

    def toggle_favorite(self, entry_id: str) -> bool | None:
        """Flip the favorite flag; return the new state, or None if not found."""
        if not entry_id:
            return None
        with self._lock:
            for item in self._items:
                if item.get("id") == entry_id:
                    item["favorite"] = not bool(item.get("favorite"))
                    self._save()
                    return bool(item["favorite"])
        return None

    def set_favorite(self, entry_id: str, value: bool) -> bool:
        with self._lock:
            for item in self._items:
                if item.get("id") == entry_id:
                    item["favorite"] = bool(value)
                    self._save()
                    return True
        return False

    def set_tags(self, entry_id: str, tags: list[str]) -> bool:
        """Replace the tag list of one entry (max 12 tags, 40 chars each)."""
        clean: list[str] = []
        for tag in tags or []:
            text = str(tag).strip().lstrip("#")[:40]
            if text and text not in clean:
                clean.append(text)
            if len(clean) == 12:
                break
        with self._lock:
            for item in self._items:
                if item.get("id") == entry_id:
                    item["tags"] = clean
                    self._save()
                    return True
        return False

    @staticmethod
    def _derived_hash_status(digest: str, expected: str) -> str:
        if not digest:
            return "unchecked"
        if expected:
            return "match" if digest == expected else "mismatch"
        return "verified"

    def update_hash(
        self,
        entry_id: str,
        *,
        digest: str | None = None,
        expected: str | None = None,
        status: str | None = None,
    ) -> bool:
        """Store a computed digest / expected digest / explicit status.

        When only a digest or an expected digest is supplied the match state is
        derived automatically.  ``status`` is used for non-computation states
        such as ``pending``, ``missing`` and ``error``.
        """
        with self._lock:
            for item in self._items:
                if item.get("id") != entry_id:
                    continue
                if digest is not None:
                    item["sha256"] = normalize_sha256(digest)
                if expected is not None:
                    item["hash_expected"] = normalize_sha256(expected)
                if status in HASH_STATUSES:
                    item["hash_status"] = status
                else:
                    item["hash_status"] = self._derived_hash_status(
                        item.get("sha256") or "", item.get("hash_expected") or ""
                    )
                if item["hash_status"] in ("verified", "match", "mismatch"):
                    item["hash_checked_at"] = now_iso()
                elif item["hash_status"] in ("unchecked", "pending"):
                    item["hash_checked_at"] = ""
                self._save()
                return True
        return False

    def favorite_count(self) -> int:
        with self._lock:
            return sum(1 for item in self._items if item.get("favorite"))

    def remove(self, entry_id: str) -> None:
        with self._lock:
            before = len(self._items)
            self._items = [item for item in self._items if item.get("id") != entry_id]
            if len(self._items) != before:
                self._save()

    def clear(self) -> None:
        with self._lock:
            self._items = []
            self._save()

    def get_stats(self) -> dict:
        """Aggregate counts/bytes for today, the current month and the last 14 days."""
        with self._lock:
            items = [dict(item) for item in self._items]

        today = date.today()
        month_start = today.replace(day=1)
        stats: dict = {
            "today_count": 0,
            "today_bytes": 0,
            "month_count": 0,
            "month_bytes": 0,
            "total_count": len(items),
            "total_bytes": 0,
            "by_day": [],
        }
        day_counts: dict[date, tuple[int, int]] = {}

        for item in items:
            try:
                size = int(item.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            if size < 0:
                size = 0
            stats["total_bytes"] += size
            entry_day = _entry_date(item.get("timestamp"))
            if entry_day is None:
                continue
            count, byte_total = day_counts.get(entry_day, (0, 0))
            day_counts[entry_day] = (count + 1, byte_total + size)
            if entry_day == today:
                stats["today_count"] += 1
                stats["today_bytes"] += size
            if entry_day >= month_start and entry_day <= today:
                stats["month_count"] += 1
                stats["month_bytes"] += size

        stats["by_day"] = [
            {
                "date": (today - timedelta(days=offset)).isoformat(),
                "count": day_counts.get(today - timedelta(days=offset), (0, 0))[0],
                "bytes": day_counts.get(today - timedelta(days=offset), (0, 0))[1],
            }
            for offset in range(13, -1, -1)
        ]
        return stats
