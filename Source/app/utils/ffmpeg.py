"""Locate a usable FFmpeg installation."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.paths import BIN_DIR


@dataclass(frozen=True)
class FFmpegInfo:
    ffmpeg: Path
    ffprobe: Path | None
    directory: Path

    @property
    def available(self) -> bool:
        return self.ffmpeg.exists()

    def describe(self) -> str:
        return str(self.ffmpeg)


def _winget_candidates() -> list[Path]:
    if os.name != "nt":
        return []
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return []
    root = Path(local) / "Microsoft" / "WinGet" / "Packages"
    results: list[Path] = []
    if root.is_dir():
        for package in root.glob("Gyan.FFmpeg*"):
            results.extend(package.glob("*/bin/ffmpeg.exe"))
            results.extend(package.glob("ffmpeg*/bin/ffmpeg.exe"))
    return results


def _common_candidates() -> list[Path]:
    candidates: list[Path] = []
    if os.name == "nt":
        candidates += [
            Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
            Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
            Path(r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"),
        ]
    else:
        candidates += [
            Path("/usr/local/bin/ffmpeg"),
            Path("/opt/homebrew/bin/ffmpeg"),
            Path("/usr/bin/ffmpeg"),
        ]
    return candidates


def _probe_for(ffmpeg: Path) -> Path | None:
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    sibling = ffmpeg.with_name(name)
    if sibling.exists():
        return sibling
    found = shutil.which(name)
    return Path(found) if found else None


def _make_info(ffmpeg: Path) -> FFmpegInfo:
    ffmpeg = ffmpeg.resolve()
    return FFmpegInfo(ffmpeg=ffmpeg, ffprobe=_probe_for(ffmpeg), directory=ffmpeg.parent)


def find_ffmpeg() -> FFmpegInfo | None:
    """Search for ffmpeg in the environment, project bin folder and common paths."""
    explicit = os.environ.get("FFMPEG_PATH")
    if explicit:
        path = Path(explicit)
        if path.is_dir():
            path = path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if path.exists():
            return _make_info(path)

    found = shutil.which("ffmpeg")
    if found:
        return _make_info(Path(found))

    local = BIN_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if local.exists():
        return _make_info(local)

    for candidate in _common_candidates() + _winget_candidates():
        if candidate.exists():
            return _make_info(candidate)
    return None
