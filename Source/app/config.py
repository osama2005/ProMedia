"""Persistent application settings stored as JSON."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.core.rules import DEFAULT_RULES, sanitize_rules
from app.paths import CONFIG_FILE
from app.ui.theme import DEFAULT_PALETTE, PALETTE_KEYS
from app.utils.helpers import default_download_dir
from app.utils.logger import log

VALID_LANGUAGES = ("ar", "en")
VALID_THEMES = ("dark", "light", "system")
VALID_PALETTES = PALETTE_KEYS
VALID_CONTAINERS = ("mp4", "mkv", "webm")
VALID_UI_SCALES = ("normal", "large")
VALID_LIBRARY_VIEWS = ("grid", "list")
VALID_LIBRARY_SORTS = ("date_desc", "date_asc", "size_desc", "size_asc", "name_asc", "name_desc", "type")
SPEED_LIMITS_KBPS = (0, 256, 512, 1024, 2048, 4096, 8192)


@dataclass
class Settings:
    language: str = "ar"
    theme: str = "dark"
    palette: str = DEFAULT_PALETTE
    download_dir: str = field(default_factory=default_download_dir)
    max_concurrent: int = 1
    audio_quality: str = "320"
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    history_limit: int = 500
    window_geometry: str = "1180x900"
    # --- advanced download options -----------------------------------
    speed_limit_kbps: int = 0  # 0 disables the limiter
    video_container: str = "mp4"  # mp4 | mkv | webm
    embed_subtitles: bool = False
    subtitle_langs: str = "ar,en"
    proxy: str = ""
    auto_clipboard: bool = True
    update_url: str = ""
    schedule_minutes: int = 0
    # --- accessibility / layout ---------------------------------------
    ui_scale: str = "normal"  # normal | large
    reduce_motion: bool = False
    library_view: str = "grid"  # grid | list
    library_sort: str = "date_desc"  # see VALID_LIBRARY_SORTS
    sidebar_collapsed: bool = False
    # --- smart queue / automation ---
    smart_naming: bool = True
    auto_shutdown: bool = False
    auto_fetch_clipboard: bool = False
    enable_stats: bool = True
    show_task_thumbnails: bool = True
    auto_retry_failed: bool = False  # reschedule transient failures automatically
    link_inbox: str = ""  # saved batch-link inbox text
    verify_hashes: bool = True  # compute SHA-256 for finished downloads
    download_rules: list = field(
        default_factory=lambda: [dict(rule) for rule in DEFAULT_RULES]
    )
    onboarding_done: bool = False  # first-run guided tour already shown
    duplicate_min_size_mb: int = 5  # ignore tiny files during duplicate scans

    def sanitized(self) -> "Settings":
        """Return a copy with values constrained to supported ranges."""
        data = asdict(self)
        data["language"] = data["language"] if data["language"] in VALID_LANGUAGES else "ar"
        data["theme"] = data["theme"] if data["theme"] in VALID_THEMES else "dark"
        data["palette"] = data["palette"] if data["palette"] in VALID_PALETTES else DEFAULT_PALETTE
        data["ui_scale"] = data["ui_scale"] if data["ui_scale"] in VALID_UI_SCALES else "normal"
        data["library_view"] = (
            data["library_view"] if data["library_view"] in VALID_LIBRARY_VIEWS else "grid"
        )
        data["library_sort"] = (
            data["library_sort"] if data.get("library_sort") in VALID_LIBRARY_SORTS else "date_desc"
        )
        data["reduce_motion"] = bool(data["reduce_motion"])
        data["sidebar_collapsed"] = bool(data["sidebar_collapsed"])
        data["smart_naming"] = bool(data["smart_naming"])
        data["auto_shutdown"] = bool(data["auto_shutdown"])
        data["auto_fetch_clipboard"] = bool(data["auto_fetch_clipboard"])
        data["enable_stats"] = bool(data["enable_stats"])
        data["show_task_thumbnails"] = bool(data["show_task_thumbnails"])
        data["auto_retry_failed"] = bool(data["auto_retry_failed"])
        data["link_inbox"] = str(data.get("link_inbox") or "")[:20000]
        data["verify_hashes"] = bool(data.get("verify_hashes", True))
        data["download_rules"] = sanitize_rules(data.get("download_rules"))
        data["onboarding_done"] = bool(data.get("onboarding_done", False))
        try:
            data["duplicate_min_size_mb"] = min(
                1000, max(1, int(data.get("duplicate_min_size_mb", 5)))
            )
        except (TypeError, ValueError):
            data["duplicate_min_size_mb"] = 5
        try:
            data["max_concurrent"] = min(4, max(1, int(data["max_concurrent"])))
        except (TypeError, ValueError):
            data["max_concurrent"] = 1
        if data["audio_quality"] not in ("320", "256", "192", "128"):
            data["audio_quality"] = "320"
        try:
            data["history_limit"] = min(2000, max(20, int(data["history_limit"])))
        except (TypeError, ValueError):
            data["history_limit"] = 500
        data["embed_metadata"] = bool(data["embed_metadata"])
        data["embed_thumbnail"] = bool(data["embed_thumbnail"])
        data["embed_subtitles"] = bool(data["embed_subtitles"])
        data["auto_clipboard"] = bool(data["auto_clipboard"])
        try:
            limit = int(data["speed_limit_kbps"])
        except (TypeError, ValueError):
            limit = 0
        data["speed_limit_kbps"] = limit if limit in SPEED_LIMITS_KBPS else 0
        if data["video_container"] not in VALID_CONTAINERS:
            data["video_container"] = "mp4"
        data["subtitle_langs"] = str(data.get("subtitle_langs") or "ar,en").strip()[:80]
        data["proxy"] = str(data.get("proxy") or "").strip()[:300]
        data["update_url"] = str(data.get("update_url") or "").strip()[:500]
        try:
            minutes = int(data["schedule_minutes"])
        except (TypeError, ValueError):
            minutes = 0
        data["schedule_minutes"] = minutes if minutes in (0, 5, 15, 30, 60, 120) else 0
        directory = Path(str(data["download_dir"])).expanduser()
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            directory = Path(default_download_dir())
        data["download_dir"] = str(directory)
        return Settings(**data)


class ConfigManager:
    """Loads/saves :class:`Settings` atomically."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else CONFIG_FILE
        self._lock = threading.RLock()
        self._settings = Settings()

    def load(self) -> Settings:
        with self._lock:
            try:
                if self.path.exists():
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        known = {f for f in Settings.__dataclass_fields__}
                        self._settings = Settings(**{k: v for k, v in raw.items() if k in known})
                else:
                    self._settings = Settings()
            except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
                log.warning("Could not read settings (%s); using defaults", exc)
                self._settings = Settings()
            self._settings = self._settings.sanitized()
            return self._settings

    def save(self, settings: Settings | None = None) -> None:
        with self._lock:
            if settings is not None:
                self._settings = settings.sanitized()
            data: dict[str, Any] = asdict(self._settings)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(self.path)
            except OSError as exc:
                log.error("Could not save settings: %s", exc)

    @property
    def settings(self) -> Settings:
        with self._lock:
            return self._settings
