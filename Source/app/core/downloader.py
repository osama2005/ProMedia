"""Download engine: queue, worker threads, pause/resume/cancel and history events."""

from __future__ import annotations

import os
import queue
import re
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from yt_dlp import YoutubeDL

from app.config import Settings
from app.core.errors import DownloadCancelled, TaskFailed, friendly_error
from app.core.formats import audio_selector, video_selector
from app.core.models import DownloadRequest
from app.utils.ffmpeg import FFmpegInfo
from app.utils.logger import log

EventSink = Callable[[str, dict], None]
SettingsProvider = Callable[[], Settings]
# (priority key, insertion order, task); None is the worker shutdown sentinel.
QueueItem = tuple[float, int, "DownloadTask | None"]

_THROTTLE_SECONDS = 0.25
_PARTIAL_SUFFIXES = {".part", ".ytdl", ".jpg", ".jpeg", ".png", ".webp"}
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_ACTIVE_STATES = ("pending", "scheduled", "downloading", "paused", "processing")


def _clean_title(title: str, limit: int = 120) -> str:
    """Make a title safe for use as a literal yt-dlp output template."""
    cleaned = _ILLEGAL_FILENAME_CHARS.sub(" ", str(title or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(". ")
    cleaned = cleaned.replace("%", "%%")  # yt-dlp treats % as a template marker
    if not cleaned:
        cleaned = "media"
    return cleaned[:limit].rstrip(" .") or "media"


class _YdlLogger:
    def debug(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        log.debug("yt-dlp warning: %s", msg)

    def error(self, msg: str) -> None:
        log.debug("yt-dlp error: %s", msg)


def build_ydl_opts(
    request: DownloadRequest,
    settings: Settings,
    ffmpeg: FFmpegInfo | None,
    progress_hook: Callable[[dict], None] | None = None,
    postprocessor_hook: Callable[[dict], None] | None = None,
    js_runtimes: dict | None = None,
) -> dict:
    """Create the yt-dlp options dictionary for one download request."""
    dest = Path(request.dest_dir or settings.download_dir)
    dest.mkdir(parents=True, exist_ok=True)

    is_audio = request.mode == "audio"
    if getattr(settings, "smart_naming", False):
        outtmpl = f"{_clean_title(request.title or request.url)}.%(ext)s"
    else:
        outtmpl = "%(title).120B [%(id)s].%(ext)s"
    options: dict = {
        "format": audio_selector() if is_audio else video_selector(request.height, settings.video_container),
        "paths": {"home": str(dest)},
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "windowsfilenames": True,
        "continuedl": True,
        "overwrites": False,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "merge_output_format": settings.video_container,
        "logger": _YdlLogger(),
        "progress_hooks": [progress_hook] if progress_hook else [],
        "postprocessor_hooks": [postprocessor_hook] if postprocessor_hook else [],
    }

    # A request-level cap wins over the global setting.  yt-dlp expects bytes
    # per second; 0/None means unlimited.
    try:
        request_limit = int(getattr(request, "speed_limit_kbps", 0) or 0)
    except (TypeError, ValueError):
        request_limit = 0
    if request_limit < 0:  # explicit "unlimited" for this download
        options.pop("ratelimit", None)
    elif request_limit > 0:
        options["ratelimit"] = request_limit * 1024
    elif settings.speed_limit_kbps and settings.speed_limit_kbps > 0:
        options["ratelimit"] = int(settings.speed_limit_kbps) * 1024
    if settings.proxy:
        options["proxy"] = settings.proxy

    if ffmpeg:
        options["ffmpeg_location"] = str(ffmpeg.directory)
    if js_runtimes:
        options["js_runtimes"] = js_runtimes

    postprocessors: list[dict] = []
    if is_audio and request.audio_codec == "mp3":
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(request.audio_bitrate or settings.audio_quality),
            }
        )

    if settings.embed_subtitles and ffmpeg and not is_audio:
        langs = [item.strip() for item in settings.subtitle_langs.split(",") if item.strip()]
        options["writesubtitles"] = True
        options["writeautomaticsub"] = True
        options["subtitleslangs"] = langs or ["ar", "en"]
        options["subtitlesformat"] = "srt/best"
        postprocessors.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": True})

    if settings.embed_thumbnail and ffmpeg:
        options["writethumbnail"] = True
        postprocessors.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
        postprocessors.append({"key": "EmbedThumbnail"})

    if settings.embed_metadata and ffmpeg:
        postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})

    options["postprocessors"] = postprocessors
    return options


class DownloadTask:
    """Mutable state of one queued item, with thread-safe snapshots."""

    def __init__(self, request: DownloadRequest) -> None:
        self.id = uuid.uuid4().hex
        self.request = request
        self.title = request.title or request.url
        self.priority = 0
        self.status = "pending"
        self.progress = 0.0
        self.speed = 0.0
        self.eta: int | None = None
        self.downloaded = 0
        self.total = 0
        self.filepath = ""
        self.size = 0
        self.error_key = ""
        self.error_detail = ""
        self.attempt = 1
        self.created_at = time.time()
        self.scheduled_for = 0.0
        self.finished_at = 0.0
        self.lock = threading.RLock()
        self.pause_flag = threading.Event()
        self.cancel_flag = threading.Event()
        self._last_emit = 0.0
        self.ydl = None  # live YoutubeDL instance for per-task speed changes

    def snapshot(self) -> dict:
        with self.lock:
            data = {
                "id": self.id,
                "title": self.title,
                "status": self.status,
                "progress": round(self.progress, 2),
                "speed": self.speed,
                "eta": self.eta,
                "downloaded": self.downloaded,
                "total": self.total,
                "filepath": self.filepath,
                "size": self.size,
                "error_key": self.error_key,
                "error_detail": self.error_detail,
                "attempt": self.attempt,
                "platform": self.request.platform,
                "priority": self.priority,
                "thumbnail": str(
                    getattr(self.request, "thumbnail", "") or self.request.thumbnail_path or ""
                ),
                "created_at": self.created_at,
                "scheduled_for": self.scheduled_for,
                "request": asdict(self.request),
            }
            return data


def _should_throttle(task: DownloadTask) -> bool:
    now = time.monotonic()
    with task.lock:
        if now - task._last_emit < _THROTTLE_SECONDS:
            return True
        task._last_emit = now
    return False


def _locate_output(info: dict, dest: Path, mode: str, codec: str) -> str:
    """Find the final file after merge/post-processing."""
    candidates: list[Path] = []
    for item in info.get("requested_downloads") or []:
        if not isinstance(item, dict):
            continue
        for key in ("filepath", "_filename"):
            value = item.get(key)
            if value:
                candidates.append(Path(value))
    for key in ("filepath", "_filename"):
        value = info.get(key)
        if value:
            candidates.append(Path(value))

    def usable(path: Path) -> bool:
        try:
            return path.is_file() and path.suffix.lower() not in _PARTIAL_SUFFIXES
        except OSError:
            return False

    existing = [path for path in candidates if usable(path)]

    video_id = str(info.get("id") or "")
    if not existing and video_id:
        try:
            existing = [
                path
                for path in dest.glob(f"*{video_id}*")
                if usable(path) and not path.name.endswith(".ytdl")
            ]
        except OSError:
            existing = []

    if not existing:
        return ""

    wanted_suffix = ".mp3" if (mode == "audio" and codec == "mp3") else ""
    if wanted_suffix:
        mp3_files = [path for path in existing if path.suffix.lower() == wanted_suffix]
        if mp3_files:
            existing = mp3_files

    try:
        newest = max(existing, key=lambda path: path.stat().st_mtime)
    except (OSError, ValueError):
        newest = existing[0]
    return str(newest)


class DownloadManager:
    """Threaded download queue with pause / resume / cancel support."""

    def __init__(
        self,
        settings_provider: SettingsProvider,
        ffmpeg: FFmpegInfo | None,
        event_sink: EventSink | None = None,
        js_runtimes: dict | None = None,
    ) -> None:
        self._settings_provider = settings_provider
        if ffmpeg is None:
            try:
                from app.utils.ffmpeg import find_ffmpeg

                ffmpeg = find_ffmpeg()
            except Exception:  # pragma: no cover - detection is best effort
                ffmpeg = None
        self._ffmpeg = ffmpeg
        self._sink = event_sink
        self._js_runtimes = js_runtimes
        self._queue: queue.PriorityQueue[QueueItem] = queue.PriorityQueue()
        self._queue_seq = 0
        self._tasks: dict[str, DownloadTask] = {}
        self._scheduled: dict[str, DownloadTask] = {}
        self._lock = threading.RLock()
        self._workers: list[threading.Thread] = []
        self._closed = False
        # Optional hook used by Auto Shutdown; called once when the queue drains.
        self.on_all_complete: Callable[[], None] | None = None
        self._all_complete_fired = False

        worker_count = max(1, settings_provider().max_concurrent)
        for index in range(worker_count):
            worker = threading.Thread(
                target=self._worker,
                name=f"download-worker-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

        self._scheduler = threading.Thread(
            target=self._scheduler_loop,
            name="download-scheduler",
            daemon=True,
        )
        self._scheduler.start()

    # -- events -----------------------------------------------------------
    def _emit(self, name: str, task: DownloadTask, force: bool = False) -> None:
        if not force and _should_throttle(task):
            return
        if self._sink:
            try:
                self._sink(name, task.snapshot())
            except Exception:  # pragma: no cover - sink must never kill a worker
                log.exception("Event sink failed")

    def _queue_item(self, task: DownloadTask | None) -> QueueItem:
        """Build a comparable queue entry; higher priority sorts first."""
        with self._lock:
            self._queue_seq += 1
            seq = self._queue_seq
        if task is None:
            return (float("inf"), seq, None)
        try:
            priority = int(task.priority)
        except (TypeError, ValueError):
            priority = 0
        return (-priority, seq, task)

    # -- public API -------------------------------------------------------
    def enqueue(
        self,
        request: DownloadRequest,
        priority: int = 0,
        delay_seconds: float = 0,
        attempt: int = 1,
    ) -> DownloadTask:
        task = DownloadTask(request)
        try:
            task.priority = int(priority)
        except (TypeError, ValueError):
            task.priority = 0
        try:
            task.attempt = max(1, int(attempt))
        except (TypeError, ValueError):
            task.attempt = 1
        with self._lock:
            self._all_complete_fired = False
        if delay_seconds and delay_seconds > 0:
            with task.lock:
                task.status = "scheduled"
                task.scheduled_for = time.time() + float(delay_seconds)
            with self._lock:
                self._tasks[task.id] = task
                self._scheduled[task.id] = task
            self._emit("added", task, force=True)
            log.info("Scheduled %s in %ss", request.url, int(delay_seconds))
            return task
        with self._lock:
            self._tasks[task.id] = task
        self._emit("added", task, force=True)
        self._queue.put(self._queue_item(task))
        return task

    def retry(self, task_id: str) -> DownloadTask | None:
        with self._lock:
            old = self._tasks.get(task_id)
        if not old or old.status not in ("error", "cancelled"):
            return None
        attempt = getattr(old, "attempt", 1) + 1
        return self.enqueue(old.request, priority=old.priority, attempt=attempt)

    def pause(self, task_id: str) -> None:
        task = self._get(task_id)
        if not task or task.status not in ("pending", "downloading"):
            return
        task.pause_flag.set()
        with task.lock:
            task.status = "paused"
            task.speed = 0.0
            task.eta = None
        self._emit("update", task, force=True)

    def resume(self, task_id: str) -> None:
        task = self._get(task_id)
        if not task or task.status != "paused":
            return
        task.pause_flag.clear()
        with task.lock:
            task.status = "downloading"
        self._emit("update", task, force=True)

    def pause_all(self) -> None:
        """Pause every pending/active task using the normal pause mechanism."""
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            with task.lock:
                status = task.status
            if status not in _ACTIVE_STATES:
                continue
            if status in ("pending", "downloading"):
                self.pause(task.id)
                continue
            if status == "paused" and task.pause_flag.is_set():
                continue
            # Scheduled/processing tasks are not handled by pause(); use the
            # same pause flag directly so they cannot start unexpectedly.
            task.pause_flag.set()
            with task.lock:
                task.status = "paused"
                task.speed = 0.0
                task.eta = None
            self._emit("update", task, force=True)

    def resume_all(self) -> None:
        """Resume every paused task, preserving scheduled task state."""
        with self._lock:
            tasks = list(self._tasks.values())
            scheduled_ids = set(self._scheduled)
        for task in tasks:
            with task.lock:
                status = task.status
            if status != "paused":
                continue
            if task.id in scheduled_ids:
                task.pause_flag.clear()
                with task.lock:
                    task.status = "scheduled"
                self._emit("update", task, force=True)
            else:
                self.resume(task.id)

    def cancel(self, task_id: str) -> None:
        task = self._get(task_id)
        if not task:
            return
        if task.status in ("completed", "error", "cancelled"):
            return
        task.cancel_flag.set()
        task.pause_flag.clear()
        if task.status in ("pending", "paused", "scheduled"):
            self._mark_cancelled(task)

    def cancel_all(self) -> None:
        with self._lock:
            ids = list(self._tasks)
        for task_id in ids:
            self.cancel(task_id)

    def has_active(self) -> bool:
        with self._lock:
            return any(task.status in _ACTIVE_STATES for task in self._tasks.values())

    def snapshots(self) -> list[dict]:
        """Return snapshots of all queued tasks in creation order."""
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda task: task.created_at)
        return [task.snapshot() for task in tasks]

    def set_task_speed_limit(self, task_id: str, kbps: int) -> bool:
        """Apply a per-task speed cap, live when the download is running."""
        try:
            limit = max(-1, min(8192, int(kbps)))
        except (TypeError, ValueError):
            return False
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            task.request.speed_limit_kbps = limit
            ydl = task.ydl
        if ydl is not None:
            try:
                if limit > 0:
                    ydl.params["ratelimit"] = limit * 1024
                else:
                    ydl.params.pop("ratelimit", None)
            except Exception:  # pragma: no cover - yt-dlp internals may vary
                log.debug("Could not adjust live rate limit", exc_info=True)
        self._emit("update", task, force=True)
        return True

    def tasks_for_group(self, group_id: str) -> list[str]:
        """Task ids whose request belongs to *group_id*."""
        with self._lock:
            return [
                task.id for task in self._tasks.values()
                if str(getattr(task.request, "group", "") or "") == group_id
            ]

    def group_action(self, group_id: str, action: str) -> int:
        """Pause or resume every task in a group.  Returns affected count."""
        ids = self.tasks_for_group(group_id)
        changed = 0
        for task_id in ids:
            task = self._get(task_id)
            if not task:
                continue
            if action == "pause" and task.status in ("pending", "downloading"):
                self.pause(task_id)
                changed += 1
            elif action in ("start", "resume") and task.status == "paused":
                self.resume(task_id)
                changed += 1
        return changed

    def shutdown(self) -> None:
        self._closed = True
        self.cancel_all()
        for _ in self._workers:
            self._queue.put(self._queue_item(None))
        for worker in self._workers:
            worker.join(timeout=0.5)
        try:
            self._scheduler.join(timeout=0.5)
        except Exception:  # pragma: no cover - best effort
            pass

    # -- scheduler --------------------------------------------------------
    def _scheduler_loop(self) -> None:
        """Promote scheduled tasks into the real queue once their time comes."""
        while not self._closed:
            due: list[DownloadTask] = []
            now = time.time()
            with self._lock:
                for task_id, task in list(self._scheduled.items()):
                    if task.cancel_flag.is_set():
                        self._scheduled.pop(task_id, None)
                        continue
                    if task.pause_flag.is_set():
                        continue  # stay scheduled until resume_all()/resume()
                    if now >= task.scheduled_for:
                        due.append(task)
                        self._scheduled.pop(task_id, None)
            for task in due:
                with task.lock:
                    task.status = "pending"
                self._emit("update", task, force=True)
                self._queue.put(self._queue_item(task))
            time.sleep(0.5)

    # -- internals --------------------------------------------------------
    def _get(self, task_id: str) -> DownloadTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def _maybe_fire_all_complete(self) -> None:
        """Fire the completion hook once when nothing is left to download."""
        callback = self.on_all_complete
        if callback is None:
            return
        with self._lock:
            if self._closed or self._all_complete_fired:
                return
            if not self._queue.empty():
                return
            if any(task.status in _ACTIVE_STATES for task in self._tasks.values()):
                return
            self._all_complete_fired = True
        try:
            callback()
        except Exception:  # pragma: no cover - callback must not break workers
            log.exception("on_all_complete callback failed")

    def _mark_cancelled(self, task: DownloadTask) -> None:
        with self._lock:
            self._scheduled.pop(task.id, None)
        with task.lock:
            if task.status == "cancelled":
                return
            task.status = "cancelled"
            task.speed = 0.0
            task.finished_at = time.time()
        self._emit("cancelled", task, force=True)
        self._maybe_fire_all_complete()

    def _mark_failed(self, task: DownloadTask, key: str, detail: str) -> None:
        with task.lock:
            task.status = "error"
            task.error_key = key
            task.error_detail = detail
            task.speed = 0.0
            task.eta = None
            task.finished_at = time.time()
        log.error("Task %s failed: %s (%s)", task.id, key, detail)
        self._emit("failed", task, force=True)
        self._maybe_fire_all_complete()

    def _wait_while_paused(self, task: DownloadTask) -> None:
        was_paused = False
        while task.pause_flag.is_set() and not task.cancel_flag.is_set():
            was_paused = True
            time.sleep(0.12)
        if was_paused and not task.cancel_flag.is_set():
            with task.lock:
                task.status = "downloading"
            self._emit("update", task, force=True)

    def _worker(self) -> None:
        while not self._closed:
            task: DownloadTask | None = None
            _, _, task = self._queue.get()
            try:
                if task is None:
                    return
                if self._closed:
                    return
                if task.cancel_flag.is_set():
                    self._mark_cancelled(task)
                    continue
                if task.pause_flag.is_set():
                    self._wait_while_paused(task)
                    if task.cancel_flag.is_set():
                        self._mark_cancelled(task)
                        continue
                self._execute(task)
            except Exception:  # pragma: no cover - worker safety net
                log.exception("Unexpected worker error")
                if task is not None:
                    self._mark_failed(task, "err_generic", "unexpected worker error")
            finally:
                self._queue.task_done()

    def _execute(self, task: DownloadTask) -> None:
        request = task.request
        settings = self._settings_provider()

        if request.mode == "audio" and request.audio_codec == "mp3" and not self._ffmpeg:
            self._mark_failed(task, "err_ffmpeg", "ffmpeg is required for MP3 conversion")
            return

        with task.lock:
            task.status = "downloading"
            task.progress = 0.0
            task.speed = 0.0
            task.error_key = ""
            task.error_detail = ""
        self._emit("update", task, force=True)

        def progress_hook(data: dict) -> None:
            if task.cancel_flag.is_set():
                raise DownloadCancelled("cancelled by user")
            self._wait_while_paused(task)
            if task.cancel_flag.is_set():
                raise DownloadCancelled("cancelled by user")

            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                downloaded = data.get("downloaded_bytes") or 0
                progress = 0.0
                if total:
                    progress = min(100.0, downloaded * 100.0 / total)
                elif data.get("fragment_count"):
                    progress = min(
                        100.0,
                        (data.get("fragment_index") or 0) * 100.0 / data["fragment_count"],
                    )
                with task.lock:
                    task.progress = progress
                    task.downloaded = int(downloaded)
                    task.total = int(total)
                    task.speed = float(data.get("speed") or 0.0)
                    eta = data.get("eta")
                    task.eta = int(eta) if isinstance(eta, (int, float)) else None
                self._emit("update", task)
            elif status == "finished":
                with task.lock:
                    task.progress = 100.0
                    task.downloaded = task.total or task.downloaded
                    task.status = "processing"
                    task.speed = 0.0
                    task.eta = None
                self._emit("update", task, force=True)
            elif status == "error":
                raise TaskFailed("err_network", "download hook reported an error")

        def postprocessor_hook(data: dict) -> None:
            if data.get("status") in ("started", "processing"):
                with task.lock:
                    task.status = "processing"
                self._emit("update", task, force=True)

        options = build_ydl_opts(
            request,
            settings,
            self._ffmpeg,
            progress_hook=progress_hook,
            postprocessor_hook=postprocessor_hook,
            js_runtimes=self._js_runtimes,
        )
        log.info("Starting download %s (%s)", request.url, request.mode)

        try:
            with YoutubeDL(options) as ydl:
                task.ydl = ydl
                info = ydl.extract_info(request.url, download=True)
            if task.cancel_flag.is_set():
                raise DownloadCancelled("cancelled by user")
            if not info:
                raise TaskFailed("err_unavailable", "extractor returned no data")

            final_path = _locate_output(
                info,
                Path(request.dest_dir or settings.download_dir),
                request.mode,
                request.audio_codec,
            )
            if not final_path:
                raise TaskFailed("err_generic", "output file was not found after download")

            size = 0
            try:
                size = os.path.getsize(final_path)
            except OSError:
                pass

            with task.lock:
                task.filepath = final_path
                task.size = size
                task.progress = 100.0
                task.status = "completed"
                task.speed = 0.0
                task.eta = 0
                task.finished_at = time.time()
                if info.get("title"):
                    task.title = str(info["title"])
            log.info("Completed: %s", final_path)
            self._emit("completed", task, force=True)
            self._maybe_fire_all_complete()
        except DownloadCancelled:
            self._mark_cancelled(task)
        except TaskFailed as exc:
            if task.cancel_flag.is_set():
                self._mark_cancelled(task)
            else:
                self._mark_failed(task, exc.key, exc.detail)
        except Exception as exc:
            if task.cancel_flag.is_set():
                self._mark_cancelled(task)
            else:
                key, detail = friendly_error(exc)
                self._mark_failed(task, key, detail)
        finally:
            task.ydl = None
