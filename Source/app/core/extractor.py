"""Media metadata extraction built on yt-dlp."""

from __future__ import annotations

import hashlib
import io
import urllib.request

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.errors import TaskFailed, friendly_error
from app.core.models import MediaEntry, MediaInfo
from app.paths import CACHE_DIR, THUMB_DIR
from app.utils.helpers import format_bytes, platform_name
from app.utils.logger import log

MAX_PLAYLIST_ITEMS = 300
_THUMB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class _YdlLogger:
    """Route yt-dlp messages to the application log."""

    def debug(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        log.warning("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.error("yt-dlp: %s", msg)


def _entry_url(entry: dict) -> str:
    if not isinstance(entry, dict):
        return ""
    url = entry.get("webpage_url") or entry.get("url") or ""
    if isinstance(url, str) and url.startswith("http"):
        return url
    video_id = entry.get("id")
    if not video_id:
        return ""
    ie_key = str(entry.get("ie_key") or entry.get("extractor_key") or "").lower()
    if not ie_key or "youtube" in ie_key:
        return f"https://www.youtube.com/watch?v={video_id}"
    return ""


def _size_bytes(value: object) -> int:
    """Return a positive byte count, or 0 for missing/invalid values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    try:
        return int(value) if value > 0 else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def _approx_size(info: dict) -> str:
    """Best-effort human-readable size estimate; "" when nothing is known."""
    if not isinstance(info, dict):
        return ""
    candidate = _size_bytes(info.get("filesize")) or _size_bytes(info.get("filesize_approx"))
    if not candidate:
        for fmt in info.get("formats") or []:
            if not isinstance(fmt, dict):
                continue
            for key in ("filesize", "filesize_approx"):
                candidate = max(candidate, _size_bytes(fmt.get(key)))
    return format_bytes(candidate, "") if candidate else ""


def _pick_thumbnail(info: dict, entries: list[dict]) -> str:
    thumb = info.get("thumbnail")
    if thumb:
        return str(thumb)
    for entry in entries:
        thumb = entry.get("thumbnail") if isinstance(entry, dict) else None
        if not thumb:
            thumbs = entry.get("thumbnails") if isinstance(entry, dict) else None
            if thumbs:
                thumb = thumbs[-1].get("url")
        if thumb:
            return str(thumb)
    return ""


def download_thumbnail(url: str, timeout: float = 20.0) -> str:
    """Download and normalise a thumbnail; returns a local path or ""."""
    if not url:
        return ""
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    target = THUMB_DIR / f"{digest}.jpg"
    if target.exists() and target.stat().st_size > 0:
        return str(target)

    try:
        request = urllib.request.Request(url, headers={"User-Agent": _THUMB_UA})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            return ""
        from PIL import Image

        image = Image.open(io.BytesIO(data))
        image = image.convert("RGB")
        image.thumbnail((1280, 720))
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, "JPEG", quality=90)
        return str(target)
    except Exception as exc:  # thumbnails are optional; never fail the fetch
        log.debug("Thumbnail download failed: %s", exc)
        return ""


class MediaExtractor:
    """Fetches metadata (and playlist entries) without downloading media."""

    def __init__(self, ffmpeg_dir: str | None = None, js_runtimes: dict | None = None) -> None:
        if not ffmpeg_dir:
            try:
                from app.utils.ffmpeg import find_ffmpeg

                found = find_ffmpeg()
                ffmpeg_dir = str(found.directory) if found else None
            except Exception:  # pragma: no cover - detection is best effort
                ffmpeg_dir = None
        self.ffmpeg_dir = ffmpeg_dir
        if js_runtimes is None:
            try:
                from app.utils.js_runtime import find_js_runtimes

                js_runtimes = find_js_runtimes()
            except Exception:  # pragma: no cover - detection is best effort
                js_runtimes = None
        self.js_runtimes = js_runtimes

    def _options(self) -> dict:
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": False,
            "extract_flat": "in_playlist",
            "playlistend": MAX_PLAYLIST_ITEMS,
            "ignoreerrors": "in_playlist",
            "socket_timeout": 25,
            "retries": 3,
            "cachedir": str(CACHE_DIR / "ytdlp"),
            "logger": _YdlLogger(),
        }
        if self.ffmpeg_dir:
            options["ffmpeg_location"] = self.ffmpeg_dir
        if self.js_runtimes:
            options["js_runtimes"] = self.js_runtimes
        return options

    def fetch(self, url: str) -> MediaInfo:
        """Return :class:`MediaInfo`; raises :class:`TaskFailed` on failure."""
        try:
            with YoutubeDL(self._options()) as ydl:
                info = ydl.extract_info(url, download=False)
        except DownloadError as exc:
            key, detail = friendly_error(exc)
            raise TaskFailed(key, detail) from exc
        except Exception as exc:
            key, detail = friendly_error(exc)
            raise TaskFailed(key, detail) from exc

        if not info:
            raise TaskFailed("err_unavailable", "extractor returned no data")

        approx_size = _approx_size(info)
        entries_raw = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
        is_playlist = bool(info.get("entries")) or info.get("_type") == "playlist"

        if is_playlist:
            return self._build_playlist_info(url, info, entries_raw, approx_size)

        heights: set[int] = set()
        for fmt in info.get("formats") or []:
            if not isinstance(fmt, dict):
                continue
            if fmt.get("vcodec") in (None, "none"):
                continue
            height = fmt.get("height")
            if isinstance(height, (int, float)) and height > 0:
                heights.add(int(height))
        if not heights and isinstance(info.get("height"), (int, float)):
            heights.add(int(info["height"]))

        thumbnail_url = _pick_thumbnail(info, [])
        return MediaInfo(
            url=url,
            title=str(info.get("title") or "").strip() or url,
            uploader=str(info.get("uploader") or info.get("channel") or "").strip(),
            duration=_as_float(info.get("duration")),
            thumbnail_path=download_thumbnail(thumbnail_url),
            platform=platform_name(info.get("extractor_key") or info.get("extractor")),
            is_playlist=False,
            heights=sorted(heights, reverse=True),
            approx_size=approx_size,
        )

    def _build_playlist_info(
        self, url: str, info: dict, raw_entries: list[dict], approx_size: str = ""
    ) -> MediaInfo:
        entries: list[MediaEntry] = []
        for entry in raw_entries[:MAX_PLAYLIST_ITEMS]:
            if not isinstance(entry, dict):
                continue
            entry_url = _entry_url(entry)
            if not entry_url:
                continue
            entries.append(
                MediaEntry(
                    url=entry_url,
                    title=str(entry.get("title") or entry_url).strip(),
                    duration=_as_float(entry.get("duration")),
                    id=str(entry.get("id") or ""),
                )
            )
        if not entries:
            raise TaskFailed("err_playlist_empty", "no usable playlist entries")

        thumbnail_url = _pick_thumbnail(info, raw_entries)
        return MediaInfo(
            url=url,
            title=str(info.get("title") or "").strip() or url,
            uploader=str(info.get("uploader") or info.get("channel") or "").strip(),
            duration=None,
            thumbnail_path=download_thumbnail(thumbnail_url),
            platform=platform_name(info.get("extractor_key") or info.get("extractor")),
            is_playlist=True,
            entries=entries,
            approx_size=approx_size,
        )


def _as_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
