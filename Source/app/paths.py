"""Filesystem locations used by the application."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ProMediaDownloader"
APP_VERSION = "1.0.9"

# Folder that contains main.py / the `app` package.
if getattr(sys, "frozen", False):  # PyInstaller executable
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

BIN_DIR = BASE_DIR / "bin"


def _user_data_root() -> Path:
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root)
        return Path.home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _pick_app_dir() -> Path:
    preferred = _user_data_root() / APP_NAME
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return preferred
    except OSError:
        fallback = BASE_DIR / "userdata"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


APP_DIR = _pick_app_dir()
CONFIG_FILE = APP_DIR / "config.json"
HISTORY_FILE = APP_DIR / "history.json"
FAILURES_FILE = APP_DIR / "failures.json"
GROUPS_FILE = APP_DIR / "groups.json"
CACHE_DIR = APP_DIR / "cache"
THUMB_DIR = CACHE_DIR / "thumbnails"
LOG_FILE = APP_DIR / "app.log"


def ensure_runtime_dirs() -> None:
    """Create all directories needed at runtime (safe to call repeatedly)."""
    for folder in (APP_DIR, CACHE_DIR, THUMB_DIR):
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def resource_path(relative: str) -> Path:
    """Resolve a bundled resource both in development and in a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    return base / relative


ensure_runtime_dirs()
