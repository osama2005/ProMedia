"""Download groups persisted as a small JSON document.

A group is a named bucket that downloads can be assigned to by URL.  URLs are
used instead of runtime task ids so membership survives restarts.  The store
is thread-safe and deliberately dependency-free.
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from app.paths import GROUPS_FILE
from app.utils.logger import log

GROUP_COLORS = ("#4CAF88", "#5B9BD5", "#C678DD", "#E5A93B", "#E06C75", "#61AFEF")
MAX_GROUPS = 24


class GroupStore:
    """Persistent collection of download groups and URL membership."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else GROUPS_FILE
        self._lock = threading.RLock()
        self._groups: list[dict[str, Any]] = []
        self._members: dict[str, str] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            if self.path.is_file():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    groups = data.get("groups") or []
                    members = data.get("members") or {}
                    self._groups = [
                        {
                            "id": str(item.get("id") or uuid.uuid4().hex)[:60],
                            "name": str(item.get("name") or "Group")[:60],
                            "color": str(item.get("color") or GROUP_COLORS[0])[:16],
                        }
                        for item in groups[:MAX_GROUPS]
                        if isinstance(item, dict) and str(item.get("name") or "").strip()
                    ]
                    self._members = {
                        str(url)[:2000]: str(group_id)[:60]
                        for url, group_id in (members.items() if isinstance(members, dict) else [])
                        if str(group_id)[:60] in {g["id"] for g in self._groups}
                    }
        except (OSError, ValueError):
            log.warning("Could not read groups file", exc_info=True)
            self._groups, self._members = [], {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"groups": self._groups, "members": self._members},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except OSError:
            log.warning("Could not save groups file", exc_info=True)

    # ------------------------------------------------------------------
    # Group CRUD
    # ------------------------------------------------------------------
    def groups(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(group) for group in self._groups]

    def add_group(self, name: str, color: str = "") -> dict[str, Any]:
        with self._lock:
            clean = str(name or "").strip()[:60]
            if not clean or len(self._groups) >= MAX_GROUPS:
                return {}
            group = {
                "id": uuid.uuid4().hex,
                "name": clean,
                "color": color if color in GROUP_COLORS else GROUP_COLORS[len(self._groups) % len(GROUP_COLORS)],
            }
            self._groups.append(group)
            self._save()
            return dict(group)

    def rename_group(self, group_id: str, name: str) -> bool:
        with self._lock:
            clean = str(name or "").strip()[:60]
            if not clean:
                return False
            for group in self._groups:
                if group["id"] == group_id:
                    group["name"] = clean
                    self._save()
                    return True
            return False

    def remove_group(self, group_id: str) -> bool:
        with self._lock:
            before = len(self._groups)
            self._groups = [g for g in self._groups if g["id"] != group_id]
            if len(self._groups) == before:
                return False
            self._members = {url: gid for url, gid in self._members.items() if gid != group_id}
            self._save()
            return True

    # ------------------------------------------------------------------
    # Membership
    # ------------------------------------------------------------------
    def assign(self, url: str, group_id: str) -> bool:
        with self._lock:
            clean_url = str(url or "").strip()
            if not clean_url:
                return False
            if group_id and group_id not in {g["id"] for g in self._groups}:
                return False
            if group_id:
                self._members[clean_url] = group_id
            else:
                self._members.pop(clean_url, None)
            self._save()
            return True

    def group_for(self, url: str) -> str:
        with self._lock:
            return self._members.get(str(url or "").strip(), "")

    def urls_for(self, group_id: str) -> list[str]:
        with self._lock:
            return [url for url, gid in self._members.items() if gid == group_id]

    def unassign_url(self, url: str) -> None:
        with self._lock:
            if self._members.pop(str(url or "").strip(), None) is not None:
                self._save()

    def group_name(self, group_id: str) -> str:
        with self._lock:
            for group in self._groups:
                if group["id"] == group_id:
                    return group["name"]
            return ""

    def group_color(self, group_id: str) -> str:
        with self._lock:
            for group in self._groups:
                if group["id"] == group_id:
                    return group["color"]
            return GROUP_COLORS[0]

    def summary(self, snapshots: list[dict]) -> list[dict[str, Any]]:
        """Return one summary row per group with live task counts."""
        with self._lock:
            result: list[dict[str, Any]] = []
            for group in self._groups:
                tasks = [
                    snap for snap in snapshots
                    if self._members.get(str((snap.get("request") or {}).get("url") or "")) == group["id"]
                ]
                done = sum(1 for t in tasks if t.get("status") == "completed")
                active = sum(1 for t in tasks if t.get("status") in ("pending", "scheduled", "downloading", "paused", "processing"))
                failed = sum(1 for t in tasks if t.get("status") == "error")
                result.append({
                    **group,
                    "total": len(tasks),
                    "done": done,
                    "active": active,
                    "failed": failed,
                    "progress": (done / len(tasks) * 100) if tasks else 0.0,
                })
            return result
