"""Lightweight update checker.

The application never replaces its own binary.  It only reads a small JSON
document (``version.json``) from a URL configured in the settings and tells the
user when a newer release is available, along with the download page.

Expected JSON shape::

    {"version": "1.0.1", "url": "https://example.com/taif-setup.exe",
     "notes": "Optional release notes"}
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from app.paths import APP_VERSION
from app.utils.logger import log

_UA = "Taif-Updater/1.0 (+https://example.invalid)"


@dataclass(frozen=True)
class UpdateResult:
    """Outcome of one update check."""

    status: str  # "available" | "latest" | "unset" | "error"
    version: str = ""
    url: str = ""
    notes: str = ""
    detail: str = ""


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(value or "").strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(candidate: str, current: str = APP_VERSION) -> bool:
    return _version_tuple(candidate) > _version_tuple(current)


def check_for_update(url: str, timeout: float = 10.0) -> UpdateResult:
    """Fetch the version document and compare it with the running version."""
    url = (url or "").strip()
    if not url:
        return UpdateResult(status="unset")

    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(256 * 1024)
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as exc:  # network / JSON problems are non fatal
        log.warning("Update check failed: %s", exc)
        return UpdateResult(status="error", detail=str(exc)[:200])

    if not isinstance(data, dict):
        return UpdateResult(status="error", detail="invalid version document")

    version = str(data.get("version") or "").strip()
    if not version:
        return UpdateResult(status="error", detail="missing version field")

    result = UpdateResult(
        status="available" if is_newer(version) else "latest",
        version=version,
        url=str(data.get("url") or "").strip(),
        notes=str(data.get("notes") or "").strip()[:400],
    )
    return result
