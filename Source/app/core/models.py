"""Data structures shared by the downloader engine and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MediaEntry:
    """One video inside a playlist."""

    url: str
    title: str
    duration: float | None = None
    id: str = ""


@dataclass
class MediaInfo:
    """Metadata shown after inspecting a URL."""

    url: str
    title: str = ""
    uploader: str = ""
    duration: float | None = None
    thumbnail_path: str = ""
    platform: str = "Other"
    is_playlist: bool = False
    entries: list[MediaEntry] = field(default_factory=list)
    heights: list[int] = field(default_factory=list)
    approx_size: str = ""  # human-readable estimate, e.g. "48.2 MB"; "" when unknown

    @property
    def entry_count(self) -> int:
        return len(self.entries)


@dataclass
class DownloadRequest:
    """Everything needed to download one item (single video or playlist entry)."""

    url: str
    title: str = ""
    mode: str = "video"  # "video" | "audio"
    height: int | None = None
    audio_codec: str = "mp3"  # "mp3" | "m4a"
    audio_bitrate: int | None = 320
    dest_dir: str = ""
    platform: str = ""
    thumbnail_path: str = ""
    applied_rules: str = ""  # ids of smart rules already applied (retry-safe)
    speed_limit_kbps: int = 0  # per-download cap; 0 uses the global setting
    group: str = ""  # download group id
