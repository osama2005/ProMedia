"""Detect a JavaScript runtime required by recent yt-dlp YouTube extraction."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# yt-dlp priority order: deno > node > bun > quickjs
_RUNTIME_ORDER = ("deno", "node", "bun", "quickjs")


def _windows_candidates(name: str) -> list[Path]:
    exe = f"{name}.exe"
    local = os.environ.get("LOCALAPPDATA")
    roaming = os.environ.get("APPDATA")
    profile = os.environ.get("USERPROFILE")
    results: list[Path] = []
    if profile:
        results.append(Path(profile) / ".deno" / "bin" / exe)
    if local:
        results.extend((Path(local) / "Microsoft" / "WinGet" / "Packages").glob(f"DenoLand.Deno*/**/{exe}"))
        results.extend((Path(local) / "Microsoft" / "WinGet" / "Packages").glob(f"OpenJS.NodeJS*/**/{exe}"))
        results.append(Path(local) / "Programs" / "deno" / exe)
    if roaming:
        results.append(Path(roaming) / "npm" / exe)
    results.append(Path(r"C:\Program Files\nodejs") / exe)
    return results


def find_js_runtimes() -> dict[str, dict] | None:
    """Return a yt-dlp ``js_runtimes`` mapping for the first runtime found."""
    for name in _RUNTIME_ORDER:
        found = shutil.which(name)
        if found:
            return {name: {"path": found}}
        if os.name == "nt":
            for candidate in _windows_candidates(name):
                if candidate.is_file():
                    return {name: {"path": str(candidate)}}
    return None
