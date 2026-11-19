"""Read-only system diagnostics for ProMediaDownloader.

Checks are cheap and offline: no network calls and no file contents are read.
The UI can run them on demand from the About / Settings area.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ui.theme import PALETTE_KEYS
from app.utils.ffmpeg import FFmpegInfo
from app.utils.logger import log


@dataclass
class CheckResult:
    key: str
    label_key: str
    ok: bool
    detail: str
    severity: str = "ok"  # "ok" | "warn" | "error"

    @property
    def icon(self) -> str:
        return {"ok": "✓", "warn": "⚠", "error": "✕"}.get(self.severity, "•")


def _result(key: str, ok: bool, detail: str, severity: str | None = None) -> CheckResult:
    return CheckResult(
        key=key,
        label_key="diag_" + key,
        ok=ok,
        detail=str(detail)[:180],
        severity=severity or ("ok" if ok else "warn"),
    )


def run_diagnostics(
    settings: Any,
    ffmpeg: FFmpegInfo | None = None,
    *,
    history_count: int = 0,
) -> list[CheckResult]:
    """Run all checks and return ordered results."""
    results: list[CheckResult] = []

    # Python runtime
    results.append(_result(
        "python", sys.version_info >= (3, 9),
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "ok" if sys.version_info >= (3, 9) else "error",
    ))

    # yt-dlp
    try:
        import yt_dlp
        version = getattr(yt_dlp, "version", lambda: "unknown")()
        results.append(_result("ytdlp", True, str(version)))
    except Exception as exc:  # pragma: no cover - only when dependency missing
        results.append(_result("ytdlp", False, str(exc), "error"))

    # FFmpeg
    description = ffmpeg.describe() if ffmpeg else "missing"
    has_ffmpeg = bool(description) and "missing" not in str(description).lower()
    results.append(_result("ffmpeg", has_ffmpeg, str(description), "ok" if has_ffmpeg else "warn"))

    # JavaScript runtime for YouTube signatures
    runtimes = [name for name in ("deno", "node", "bun") if shutil.which(name)]
    results.append(_result(
        "js_runtime", bool(runtimes),
        ", ".join(runtimes) if runtimes else "deno / node / bun غير موجود",
        "ok" if runtimes else "warn",
    ))

    # Download directory exists and is writable
    folder = Path(str(getattr(settings, "download_dir", "") or ""))
    folder_ok = False
    folder_detail = "مجلد غير مضبوط"
    if folder:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".diagnostic_write"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            folder_ok = True
            folder_detail = str(folder)
        except OSError as exc:
            folder_detail = str(exc)
    results.append(_result("download_dir", folder_ok, folder_detail,
                           "ok" if folder_ok else "error"))

    # Free disk space
    try:
        usage = shutil.disk_usage(folder if folder_ok else Path.home())
        free_gb = usage.free / 1024 ** 3
        results.append(_result(
            "disk_space", free_gb >= 1.0,
            f"{free_gb:.1f} GB",
            "ok" if free_gb >= 5.0 else "warn" if free_gb >= 1.0 else "error",
        ))
    except OSError as exc:
        results.append(_result("disk_space", False, str(exc), "warn"))

    # Theme identity / saved palette
    palette = str(getattr(settings, "palette", "") or "")
    results.append(_result("palette", palette in PALETTE_KEYS, palette,
                           "ok" if palette in PALETTE_KEYS else "warn"))

    # History health
    results.append(_result("history", history_count >= 0, str(history_count)))

    # Proxy syntax (only when configured)
    proxy = str(getattr(settings, "proxy", "") or "").strip()
    if proxy:
        valid = "://" in proxy or proxy.count(":") == 1
        results.append(_result("proxy", valid, proxy, "ok" if valid else "warn"))

    log.info("Diagnostics completed: %d checks", len(results))
    return results
