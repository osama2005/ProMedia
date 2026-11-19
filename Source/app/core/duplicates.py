"""Duplicate-file detection across the download library.

Detection runs entirely from cached metadata (SHA-256 digests produced by the
integrity feature, plus filename + size) so a scan never reads file contents.
Deletion is opt-in and routes files through the Recycle Bin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.utils.trash import send_to_trash

_COPY_SUFFIX = re.compile(r"(?:\s*\(\d+\)|\s*[-–]\s*copy(?:\s*\d+)?|\s*نسخة(?:\s*\d+)?)+$", re.I)


@dataclass
class DuplicateGroup:
    """A set of library entries that point at the same media."""

    key: str
    reason: str  # "hash" | "name_size"
    entries: list[dict[str, Any]] = field(default_factory=list)
    wasted_bytes: int = 0
    keep_id: str = ""

    @property
    def removable_ids(self) -> list[str]:
        return [str(e.get("id") or "") for e in self.entries if str(e.get("id") or "") != self.keep_id]


def _normalised_name(filepath: str) -> str:
    name = Path(str(filepath or "")).name.lower()
    stem = Path(name).stem
    stem = _COPY_SUFFIX.sub("", stem).strip()
    return stem


def _entry_size(entry: dict[str, Any]) -> int:
    try:
        return int(entry.get("size") or 0)
    except (TypeError, ValueError):
        return 0


def _preferred_keep(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep favourites first, then the oldest entry that still exists."""
    def rank(entry: dict[str, Any]) -> tuple[int, str]:
        exists = 0 if Path(str(entry.get("filepath") or "")).is_file() else 1
        favourite = 0 if entry.get("favorite") else 1
        return (favourite, f"{exists:01d}-{str(entry.get('timestamp') or '9999')}")

    return sorted(candidates, key=rank)[0]


def find_duplicates(entries: Iterable[dict[str, Any]], min_size: int = 1024) -> list[DuplicateGroup]:
    """Return duplicate groups, strongest evidence first.

    Entries with a computed SHA-256 are grouped by digest.  Remaining entries
    are grouped by normalised filename + byte size.  An entry never appears in
    two groups.
    """
    items = [dict(entry) for entry in (entries or [])]
    by_hash: dict[str, list[dict[str, Any]]] = {}
    hashed: set[str] = set()
    for entry in items:
        digest = str(entry.get("sha256") or "").strip().lower()
        if len(digest) == 64 and _entry_size(entry) >= min_size:
            by_hash.setdefault(digest, []).append(entry)
            hashed.add(str(entry.get("id") or ""))

    groups: list[DuplicateGroup] = []
    for digest, candidates in by_hash.items():
        if len(candidates) < 2:
            continue
        keep = _preferred_keep(candidates)
        size = _entry_size(keep)
        groups.append(DuplicateGroup(
            key=digest[:16],
            reason="hash",
            entries=sorted(candidates, key=lambda e: str(e.get("timestamp") or "")),
            wasted_bytes=size * (len(candidates) - 1),
            keep_id=str(keep.get("id") or ""),
        ))

    by_name: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for entry in items:
        if str(entry.get("id") or "") in hashed:
            continue
        size = _entry_size(entry)
        name = _normalised_name(entry.get("filepath") or "")
        if size >= min_size and name:
            by_name.setdefault((name, size), []).append(entry)

    for (name, size), candidates in by_name.items():
        if len(candidates) < 2:
            continue
        keep = _preferred_keep(candidates)
        groups.append(DuplicateGroup(
            key=f"{name}:{size}",
            reason="name_size",
            entries=sorted(candidates, key=lambda e: str(e.get("timestamp") or "")),
            wasted_bytes=size * (len(candidates) - 1),
            keep_id=str(keep.get("id") or ""),
        ))

    return sorted(groups, key=lambda g: g.wasted_bytes, reverse=True)


def cleanup_duplicates(
    groups: list[DuplicateGroup],
    history,
    *,
    delete_files: bool = True,
) -> dict[str, int]:
    """Remove the non-recommended copies.  Returns a small result summary.

    Only entries from the supplied groups are touched, and the recommended
    keep entry is always left in place.
    """
    removed_history = 0
    removed_files = 0
    failed = 0
    allowed = {
        entry_id
        for group in groups
        for entry_id in group.removable_ids
    }
    for entry_id in allowed:
        entry = next((e for e in history.entries() if str(e.get("id") or "") == entry_id), None)
        if not entry:
            continue
        if delete_files:
            filepath = str(entry.get("filepath") or "")
            if filepath and Path(filepath).is_file():
                if send_to_trash(filepath):
                    removed_files += 1
                else:
                    failed += 1
        history.remove(entry_id)
        removed_history += 1
    return {"history": removed_history, "files": removed_files, "failed": failed}
