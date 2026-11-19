"""Small, dependency-free helper functions used across the app."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

URL_RE = re.compile(r"https?://[^\s<>\"'،؛؟]+", re.IGNORECASE)
BARE_DOMAIN_RE = re.compile(
    r"^(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?::\d+)?(?:/.*)?$",
    re.IGNORECASE,
)
_TRAILING_CHARS = ".,;:!?)]}>\"'،؛؟"


def normalize_url(text: str) -> str:
    """Extract and clean a URL from arbitrary clipboard text.

    Returns an empty string when no plausible URL is present.
    """
    if not text:
        return ""
    text = text.strip()
    match = URL_RE.search(text)
    if match:
        url = match.group(0)
    else:
        candidate = text.splitlines()[0].strip()
        if BARE_DOMAIN_RE.match(candidate) and " " not in candidate:
            url = "https://" + candidate
        else:
            return ""
    return url.rstrip(_TRAILING_CHARS)


def is_valid_url(url: str) -> bool:
    """Basic sanity check for an http(s) media URL."""
    if not url or len(url) > 4096:
        return False
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
    except ValueError:
        return False
    host = parsed.hostname or ""
    if " " in url or not host:
        return False
    if "." not in host and host.lower() != "localhost":
        return False
    return True


def extract_urls(text: str) -> list[str]:
    """Return every unique, valid http(s) URL found in *text*.

    Several links per line, bare ``www.`` domains and trailing punctuation are
    all supported.  The order of first appearance is preserved so callers can
    enqueue a batch in the order the user pasted it.
    """
    if not text:
        return []
    urls: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        url = candidate.strip().rstrip(_TRAILING_CHARS)
        if url and url not in seen and is_valid_url(url):
            seen.add(url)
            urls.append(url)

    for line in text.splitlines():
        matched = False
        for match in URL_RE.finditer(line):
            matched = True
            add(match.group(0))
        if not matched:
            candidate = line.strip()
            if BARE_DOMAIN_RE.match(candidate):
                add("https://" + candidate)
    return urls


def format_bytes(value: float | int | None, unknown: str = "—") -> str:
    """Human readable byte count (e.g. ``12.4 MB``)."""
    if value is None or value < 0:
        return unknown
    size = float(value)
    if size < 1024:
        return f"{int(size)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024.0
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TB"


def format_speed(bytes_per_second: float | None, unknown: str = "—") -> str:
    if not bytes_per_second or bytes_per_second <= 0:
        return unknown
    return f"{format_bytes(bytes_per_second, unknown)}/s"


def format_duration(seconds: float | int | None) -> str:
    """Format seconds as ``H:MM:SS`` or ``M:SS``."""
    if seconds is None or seconds < 0:
        return "—"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_eta(seconds: float | int | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    if total >= 3600:
        hours, remainder = divmod(total, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{hours}h {minutes:02d}m"
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def truncate(text: str, limit: int = 80) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def format_date(iso_value: str | None) -> str:
    if not iso_value:
        return "—"
    try:
        return datetime.fromisoformat(iso_value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(iso_value)


def default_download_dir() -> str:
    downloads = Path.home() / "Downloads"
    target = downloads / "Media Downloader"
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        target = Path.home()
    return str(target)


def open_path(path: str | Path) -> bool:
    """Open a file or folder with the operating system's default handler."""
    try:
        target = str(path)
        if os.name == "nt":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return True
    except Exception:
        return False


def reveal_in_folder(path: str | Path) -> bool:
    """Open the containing folder and select the file when possible."""
    try:
        target = Path(path)
        if not target.exists():
            return open_path(target.parent)
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", str(target)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        else:
            return open_path(target.parent)
        return True
    except Exception:
        return False


_VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".m4v", ".ts", ".mpeg", ".mpg"}
_AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".opus", ".ogg", ".wav", ".flac", ".wma", ".oga"}
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}


def media_kind(path: str | None) -> str:
    """Classify a file path as video / audio / image / other."""
    suffix = Path(str(path or "")).suffix.lower()
    if suffix in _VIDEO_SUFFIXES:
        return "video"
    if suffix in _AUDIO_SUFFIXES:
        return "audio"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    return "other"


def format_clock(epoch: float | int | None) -> str:
    """Format a Unix timestamp as a short local clock string."""
    if not epoch:
        return "—"
    try:
        return datetime.fromtimestamp(float(epoch)).strftime("%H:%M")
    except (OSError, OverflowError, ValueError):
        return "—"


def platform_name(extractor: str | None) -> str:
    """Normalise yt-dlp extractor keys to friendly platform names."""
    if not extractor:
        return "Other"
    key = extractor.lower()
    mapping = {
        "youtube": "YouTube",
        "youtube:tab": "YouTube",
        "youtubetab": "YouTube",
        "tiktok": "TikTok",
        "instagram": "Instagram",
        "facebook": "Facebook",
        "twitter": "X (Twitter)",
        "x": "X (Twitter)",
        "vimeo": "Vimeo",
        "dailymotion": "Dailymotion",
        "soundcloud": "SoundCloud",
        "twitch": "Twitch",
        "reddit": "Reddit",
        "pinterest": "Pinterest",
        "snapchat": "Snapchat",
        "linkedin": "LinkedIn",
        "telegram": "Telegram",
        "generic": "Web",
    }
    if key in mapping:
        return mapping[key]
    for prefix, name in mapping.items():
        if key.startswith(prefix):
            return name
    cleaned = extractor.replace("IE", "").replace("_", " ").strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else "Other"
