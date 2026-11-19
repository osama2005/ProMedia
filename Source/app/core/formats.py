"""Format / quality choices offered by the UI."""

from __future__ import annotations

from dataclasses import dataclass

MAX_HEIGHT = 4320  # 8K


@dataclass(frozen=True)
class FormatChoice:
    """A single entry in the quality drop-down."""

    id: str
    kind: str  # "video" | "audio"
    height: int | None = None
    codec: str = ""  # "mp3" | "m4a"
    bitrate: int | None = None

    @property
    def is_best(self) -> bool:
        return self.kind == "video" and self.height is None


def build_video_choices(heights: list[int] | None) -> list[FormatChoice]:
    """Build video quality options from the heights reported by yt-dlp."""
    cleaned: set[int] = set()
    for height in heights or []:
        try:
            value = int(height)
        except (TypeError, ValueError):
            continue
        if 0 < value <= MAX_HEIGHT:
            cleaned.add(value)

    choices = [FormatChoice(id="video-best", kind="video", height=None)]
    for height in sorted(cleaned, reverse=True):
        choices.append(FormatChoice(id=f"video-{height}", kind="video", height=height))
    return choices


def build_audio_choices() -> list[FormatChoice]:
    return [
        FormatChoice(id="audio-mp3-320", kind="audio", codec="mp3", bitrate=320),
        FormatChoice(id="audio-mp3-256", kind="audio", codec="mp3", bitrate=256),
        FormatChoice(id="audio-mp3-192", kind="audio", codec="mp3", bitrate=192),
        FormatChoice(id="audio-mp3-128", kind="audio", codec="mp3", bitrate=128),
        FormatChoice(id="audio-m4a", kind="audio", codec="m4a", bitrate=None),
    ]


def video_selector(height: int | None, container: str = "mp4") -> str:
    """yt-dlp format selector for a video download.

    ``container`` nudges the selector towards formats that merge cleanly into
    the requested output container (MP4 / MKV / WEBM).
    """
    container = (container or "mp4").lower()
    if not height:
        if container == "webm":
            return "bv*[ext=webm]+ba[ext=webm]/bv*+ba/b"
        if container == "mp4":
            return "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
        return "bv*+ba/b"
    if container == "webm":
        return (
            f"bv*[height<={height}][ext=webm]+ba[ext=webm]/"
            f"bv*[height<={height}]+ba/b[height<={height}]/b"
        )
    if container == "mp4":
        return (
            f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={height}]+ba/"
            f"b[height<={height}]/b"
        )
    return (
        f"bv*[height<={height}]+ba/"
        f"b[height<={height}]/b"
    )


def audio_selector() -> str:
    return "ba/b"
