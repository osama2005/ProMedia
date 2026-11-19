"""Friendly, localised error handling for yt-dlp failures."""

from __future__ import annotations

import re

# Ordered list: (regex, translation key)
_ERROR_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ffmpeg (?:is )?not (?:installed|found)|ffprobe|could not find ffmpeg", re.I), "err_ffmpeg"),
    (re.compile(r"requested format is not available|no video formats found", re.I), "err_format"),
    (re.compile(r"private video|video is private|this video is private", re.I), "err_private"),
    (re.compile(r"sign in to confirm|please (?:sign|log) ?in|login required|age[- ]restricted|cookies|confirm your age", re.I), "err_login"),
    (re.compile(r"not available in your country|geo[- ]?restrict|blocked (?:it )?in your country|not available from your location", re.I), "err_geo"),
    (re.compile(r"http error 429|too many requests", re.I), "err_rate_limit"),
    (re.compile(r"copyright|blocked it on copyright grounds", re.I), "err_copyright"),
    (re.compile(r"no space left|disk full|errno 28", re.I), "err_disk"),
    (re.compile(r"video unavailable|has been removed|does not exist|been deleted|account (?:has been )?terminated|content isn't available|this content is not available|removed by the uploader", re.I), "err_unavailable"),
    (re.compile(r"unsupported url|is not a valid url|invalid url|no suitable info extractor", re.I), "err_invalid_url"),
    (re.compile(r"urlopen error|timed out|connection (?:reset|aborted|refused)|temporary failure|getaddrinfo failed|network is unreachable|read timed out|ssl|handshake|http error 5\d\d", re.I), "err_network"),
    (re.compile(r"unable to download (?:video|webpage)|unable to extract|failed to extract", re.I), "err_unavailable"),
]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class DownloadCancelled(Exception):
    """Raised from yt-dlp hooks when the user cancels a task."""


class TaskFailed(Exception):
    """Raised with an already localised key."""

    def __init__(self, key: str, detail: str = "") -> None:
        super().__init__(detail or key)
        self.key = key
        self.detail = detail


def clean_detail(exc: BaseException | str) -> str:
    text = _ANSI_RE.sub("", str(exc)).strip()
    text = re.sub(r"^ERROR:\s*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text[:500]


def friendly_error(exc: BaseException | str) -> tuple[str, str]:
    """Map an exception/message to ``(translation_key, technical_detail)``."""
    detail = clean_detail(exc)
    for pattern, key in _ERROR_RULES:
        if pattern.search(detail):
            return key, detail
    return "err_generic", detail
