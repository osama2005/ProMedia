"""Main application window built with CustomTkinter.

Layout: a slim sidebar for navigation and a two-column workspace.
Motion: page slides, an animated nav indicator, easing progress bars,
thumbnail reveal and slide-up toast notifications.
"""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
import tkinter as tk
import webbrowser
import weakref
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageOps

from app.config import ConfigManager, Settings, SPEED_LIMITS_KBPS
from app.core.downloader import DownloadManager
from app.core.errors import TaskFailed, friendly_error
from app.core.extractor import MediaExtractor
from app.core.formats import (
    FormatChoice,
    build_audio_choices,
    build_video_choices,
)
from app.core.failures import FailureStore, TRANSIENT_ERROR_KEYS
from app.core.groups import GroupStore
from app.core.history import HistoryStore
from app.core.models import DownloadRequest, MediaEntry, MediaInfo
from app.core.rules import (
    KIND_VALUES,
    VALID_ACTIONS,
    VALID_CONDITIONS,
    apply_rules,
    parse_size_text,
    sanitize_rules,
)
from app.core.updater import check_for_update
from app.i18n import VIDEO_HEIGHT_TAGS, is_rtl, shape_for_tk, translate
from app.paths import APP_DIR, APP_VERSION, BASE_DIR, resource_path
from app.ui.dialogs import AboutDialog, NotificationsDialog
from app.ui.diagnostics_dialog import DiagnosticsDialog
from app.ui.duplicates_dialog import DuplicatesDialog
from app.ui.failed_center_dialog import FailedCenterDialog
from app.ui.groups_dialog import GroupsDialog
from app.ui.link_inbox_dialog import LinkInboxDialog
from app.ui.onboarding_dialog import OnboardingDialog
from app.ui.playlist_dialog import PlaylistDialog
from app.ui.qr_dialog import QRDialog
from app.ui.theme import DEFAULT_PALETTE, PALETTE_KEYS, preview_colours
from app.ui.theme import tokens as theme_tokens
from app.ui.widgets import (
    HistoryRow,
    MediaCard,
    SkeletonBox,
    TaskCard,
    Toast,
    Tooltip,
    apply_palette as apply_widget_palette,
)
from app.utils.ffmpeg import find_ffmpeg
from app.utils.hash import normalize_sha256, sha256_file
from app.utils.helpers import (
    format_bytes,
    format_duration,
    format_speed,
    is_valid_url,
    media_kind,
    normalize_url,
    open_path,
    reveal_in_folder,
)
from app.utils.js_runtime import find_js_runtimes
from app.utils.logger import log

try:  # optional drag & drop support
    from tkinterdnd2 import DND_FILES, DND_TEXT, TkinterDnD

    DND_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    DND_FILES = DND_TEXT = None
    TkinterDnD = None
    DND_AVAILABLE = False

# Backoff used by the automatic retry of transient failures (seconds).
AUTO_RETRY_DELAYS = (10, 30, 60)

# Library sort modes: (setting value, translation key).
LIBRARY_SORTS = (
    ("date_desc", "sort_date_desc"),
    ("date_asc", "sort_date_asc"),
    ("size_desc", "sort_size_desc"),
    ("size_asc", "sort_size_asc"),
    ("name_asc", "sort_name_asc"),
    ("name_desc", "sort_name_desc"),
    ("type", "sort_type"),
)

# Extra FFmpeg tools appended to the three original media utilities.
EXTRA_TOOL_SPECS = (
    ("convert", "tool_convert_title", "tool_convert_desc"),
    ("gif", "tool_gif_title", "tool_gif_desc"),
    ("merge", "tool_merge_title", "tool_merge_desc"),
    ("subtitle", "tool_subtitle_title", "tool_subtitle_desc"),
    ("cover", "tool_cover_title", "tool_cover_desc"),
)
CONVERT_FORMATS = ("mp4", "mkv", "webm", "mp3", "m4a")
TOOL_SUFFIXES = {
    "extract": "_audio.mp3",
    "compress": "_compressed.mp4",
    "trim": "_trim.mp4",
    "gif": "_animated.gif",
    "merge": "_merged.mp4",
    "subtitle": "_subtitled.mp4",
    "cover": "_cover.jpg",
}


def _fmt_number(value: float) -> str:
    """Compact numeric formatting for FFmpeg arguments."""
    return f"{value:g}"


def _ffmpeg_filter_path(path: str) -> str:
    """Escape a path for use inside an FFmpeg ``subtitles=`` filter."""
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

# Theme-aware colours shared by the whole window.  ``apply_palette`` refreshes
# every global from ``app.ui.theme`` so a palette change can rebuild the UI.
_DEFAULT_TOKENS = theme_tokens(DEFAULT_PALETTE)

BG = _DEFAULT_TOKENS["bg"]
CARD = _DEFAULT_TOKENS["card"]
CARD_BORDER = _DEFAULT_TOKENS["border"]
SIDEBAR = _DEFAULT_TOKENS["sidebar"]
SIDEBAR_BORDER = _DEFAULT_TOKENS["sidebar_border"]
MUTED = _DEFAULT_TOKENS["muted"]
ACCENT = _DEFAULT_TOKENS["accent"]
ACCENT_HOVER = _DEFAULT_TOKENS["accent_hover"]
ACCENT_SOFT = _DEFAULT_TOKENS["accent_soft"]
DANGER = _DEFAULT_TOKENS["danger"]
SOFT_BUTTON = _DEFAULT_TOKENS["soft_button"]
SOFT_HOVER = _DEFAULT_TOKENS["soft_hover"]
SOFT_TEXT = _DEFAULT_TOKENS["soft_text"]
SUCCESS = _DEFAULT_TOKENS["success"]
WARN = _DEFAULT_TOKENS["warn"]


def apply_palette(key: str) -> None:
    """Point every module-level colour at *key* and refresh child widgets."""
    global BG, CARD, CARD_BORDER, SIDEBAR, SIDEBAR_BORDER, MUTED
    global ACCENT, ACCENT_HOVER, ACCENT_SOFT, DANGER
    global SOFT_BUTTON, SOFT_HOVER, SOFT_TEXT, SUCCESS, WARN

    tokens = theme_tokens(key)
    BG = tokens["bg"]
    CARD = tokens["card"]
    CARD_BORDER = tokens["border"]
    SIDEBAR = tokens["sidebar"]
    SIDEBAR_BORDER = tokens["sidebar_border"]
    MUTED = tokens["muted"]
    ACCENT = tokens["accent"]
    ACCENT_HOVER = tokens["accent_hover"]
    ACCENT_SOFT = tokens["accent_soft"]
    DANGER = tokens["danger"]
    SOFT_BUTTON = tokens["soft_button"]
    SOFT_HOVER = tokens["soft_hover"]
    SOFT_TEXT = tokens["soft_text"]
    SUCCESS = tokens["success"]
    WARN = tokens["warn"]
    apply_widget_palette(key)


apply_palette(DEFAULT_PALETTE)

SIDEBAR_WIDTH = 236
SIDEBAR_COLLAPSED_WIDTH = 78
THUMB_SIZE = (200, 113)
MAX_DISPLAY_ENTRIES = 300

# Live responsive sizing.  The saved default geometry is the reference point;
# the result is quantised so a drag burst updates a handful of times instead of
# re-laying out the whole UI on every pixel of mouse movement.
BASE_WINDOW_SIZE = (1180, 900)
MIN_WINDOW_SCALE = 0.84
MAX_WINDOW_SCALE = 1.30
WINDOW_SCALE_STEP = 0.04

PAGE_HEADERS = (
    ("home_title", "home_subtitle"),
    ("download_title", "download_subtitle"),
    ("active_title", "active_subtitle"),
    ("queue_title", "queue_subtitle"),
    ("library_title", "library_subtitle"),
    ("history_section", "history_subtitle"),
    ("tools_title", "tools_subtitle"),
    ("settings_section", "settings_subtitle"),
)


class NavItem(ctk.CTkFrame):
    """One clickable row in the sidebar navigation."""

    def __init__(self, master, icon: str, label: str, command, app) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=10, height=46)
        self.app = app
        self.command = command
        self.active = False
        self._badge_count = 0
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)

        self.icon_label = ctk.CTkLabel(
            self,
            text=icon,
            width=24,
            font=app._font(15, family="Segoe UI Symbol"),
        )
        self.text_label = ctk.CTkLabel(
            self,
            text=label,
            font=app.f_body,
            anchor="w",
        )
        self.badge = ctk.CTkLabel(
            self,
            text="",
            width=19,
            height=19,
            corner_radius=10,
            fg_color=ACCENT,
            text_color="#FFFFFF",
            font=app._font(9, weight="bold"),
        )
        self._register_shape = app._register_shape
        self._register_shape(self, height=46)
        self._register_shape(self.badge, width=19, height=19)
        self.tooltip = Tooltip(self, label)
        self.apply_direction()

        for widget in (self, self.icon_label, self.text_label):
            widget.bind("<Button-1>", self._on_click)
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            try:
                widget.configure(cursor="hand2")
            except Exception:
                pass
        self.set_active(False)

    # ------------------------------------------------------------------
    def apply_direction(self) -> None:
        rtl = is_rtl(self.app.settings.language)
        collapsed = bool(getattr(self.app, "sidebar_collapsed", False))
        self.icon_label.grid_forget()
        self.text_label.grid_forget()
        for column in (0, 1, 2):
            self.grid_columnconfigure(column, weight=0)

        if collapsed:
            self.grid_columnconfigure(0, weight=1)
            self.icon_label.configure(width=28)
            # Explicitly hide text label in collapsed mode
            self.text_label.grid_remove()
            self.icon_label.grid(row=0, column=0, padx=0)
            self._place_badge(collapsed=True)
            return

        self.grid_columnconfigure(0, weight=0 if not rtl else 1)
        self.grid_columnconfigure(1, weight=1 if not rtl else 0)
        if rtl:
            self.text_label.configure(anchor="e", justify="right")
            self.text_label.grid(row=0, column=0, sticky="ew", padx=(12, 0))
            self.icon_label.grid(row=0, column=1, padx=(6, 14))
        else:
            self.text_label.configure(anchor="w", justify="left")
            self.icon_label.grid(row=0, column=0, padx=(14, 6))
            self.text_label.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        self._place_badge(collapsed=False, rtl=rtl)

    def _place_badge(self, *, collapsed: bool, rtl: bool = False) -> None:
        if self._badge_count <= 0:
            self.badge.place_forget()
            return
        self.badge.configure(text=str(min(99, self._badge_count)))
        if collapsed:
            self.badge.place(relx=0.78, rely=0.2, anchor="center")
        elif rtl:
            self.badge.place(x=6, rely=0.5, anchor="w")
        else:
            self.badge.place(relx=1.0, x=-8, rely=0.5, anchor="e")
        self.badge.lift()

    def set_badge(self, count: int) -> None:
        self._badge_count = max(0, int(count))
        self._place_badge(
            collapsed=bool(getattr(self.app, "sidebar_collapsed", False)),
            rtl=is_rtl(self.app.settings.language),
        )

    def set_text(self, text: str) -> None:
        self.text_label.configure(text=text)
        try:
            self.tooltip.update_text(text)
        except Exception:
            pass

    def set_active(self, active: bool) -> None:
        self.active = active
        color = ACCENT if active else "transparent"
        self.configure(fg_color=color)
        self.icon_label.configure(text_color="#FFFFFF" if active else MUTED)
        self.text_label.configure(
            text_color="#FFFFFF" if active else SOFT_TEXT,
            font=self.app.f_body_bold if active else self.app.f_body,
        )

    def _on_click(self, _event=None) -> None:
        self.command()

    def _on_enter(self, _event=None) -> None:
        if not self.active:
            self.configure(fg_color=SOFT_BUTTON)

    def _on_leave(self, _event=None) -> None:
        if not self.active:
            self.configure(fg_color="transparent")


class MediaDownloaderApp(ctk.CTk):
    """The main window: fetch, choose quality, download and browse history."""

    def __init__(
        self,
        config: ConfigManager | None = None,
        history: HistoryStore | None = None,
        failures: FailureStore | None = None,
        groups: GroupStore | None = None,
    ) -> None:
        self.config = config or ConfigManager()
        self.settings: Settings = self.config.load()
        apply_palette(self.settings.palette)
        try:
            ctk.ThemeManager.theme["CTkFont"]["family"] = "Segoe UI"
        except Exception:
            pass
        ctk.set_appearance_mode(self.settings.theme)

        super().__init__(fg_color=BG)

        self.ffmpeg = find_ffmpeg()
        self.js_runtimes = find_js_runtimes()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        # Results from FFmpeg media-tool workers are marshalled back to the UI
        # through this queue.  Calling ``after`` from a worker thread is not
        # thread-safe in Tkinter (the callback is registered but never runs),
        # so ``_poll_events`` drains this queue on the main thread instead.
        self.tool_results: queue.Queue[tuple[str, bool, str, str]] = queue.Queue()
        self.manager = DownloadManager(
            lambda: self.settings,
            self.ffmpeg,
            self._on_manager_event,
            js_runtimes=self.js_runtimes,
        )
        self.manager.on_all_complete = self._on_all_complete
        self.history = history or HistoryStore(limit=self.settings.history_limit)
        self.failures = failures or FailureStore(limit=200)
        self.groups = groups or GroupStore()
        self.workspace_visible = False

        self.current_info: MediaInfo | None = None
        self.quality_choices: list[FormatChoice] = build_video_choices([])
        self.quality_index = 0
        self.current_mode_index = 0
        self.current_tab_index = 0
        self.current_page: ctk.CTkFrame | None = None
        self._fetching = False
        self._alive = True
        self._status_state: tuple[str, dict, bool] = ("status_ready", {}, False)
        self._thumb_image: ctk.CTkImage | None = None
        self._thumb_frame_scale = 1.0
        self._logo_image: ctk.CTkImage | None = None
        self._toast_widget: Toast | None = None

        # Responsive sizing registry.  Entries are weak references: once a
        # widget/font/image is destroyed (e.g. by a UI rebuild) it disappears
        # from the registry on the next resize without any manual cleanup.
        self._ui_scale_factor = 1.0
        self._scale_fonts: list[weakref.ReferenceType] = []
        self._scale_images: list[weakref.ReferenceType] = []
        self._scale_shapes: list[weakref.ReferenceType] = []
        self._scale_spacings: list[weakref.ReferenceType] = []
        self._resize_job: str | None = None
        self._resize_size = (0, 0)
        self._page_job: str | None = None
        self._nav_job: str | None = None
        self._thumb_job: str | None = None
        self._rebuild_job: str | None = None
        self._clipboard_job: str | None = None
        self._search_job: str | None = None
        self._update_job: str | None = None
        self._status_job: str | None = None
        self._dyn_job: str | None = None
        self._mini_job: str | None = None
        self._mini_window: ctk.CTkToplevel | None = None
        self._mini_host: ctk.CTkScrollableFrame | None = None
        self._shutdown_job: str | None = None
        self._shutdown_dialog: ctk.CTkToplevel | None = None
        self._history_layout_job: str | None = None
        self._saved_job: str | None = None
        self._clipboard_last = ""
        self._manual_update = False
        self._auto_url = ""
        self.history_query = ""
        self.history_kind = "all"
        self.favorites_only = False
        self.library_sort = getattr(self.settings, "library_sort", "date_desc") or "date_desc"
        self._sort_menu: ctk.CTkToplevel | None = None
        self._history_columns = 0
        self._history_visible: list[dict] = []
        self.sidebar_collapsed = False  # Sidebar always expanded; collapse button removed
        self.settings.sidebar_collapsed = False
        self.notifications: list[dict] = []
        self._notif_seen = 0
        self._connection_online = True
        self._disk_busy = False
        self._dnd_ready = False
        self.task_cards: dict[str, TaskCard] = {}
        self.history_rows: dict[str, object] = {}
        self._static_bindings: list[tuple[ctk.CTkBaseClass, str]] = []
        self.palette_values: list[str] = []
        self.palette_chips: list[ctk.CTkFrame] = []

        self._fonts()
        self._set_window_icon()
        self._build_window()
        self._build_sidebar()
        self._build_content()
        self._build_pages()
        self._collect_spacings()
        self._render_info()
        self._refresh_quality_menu()
        self._refresh_history()
        self._set_status("status_ready")
        self._update_header_buttons()
        self._switch_page(0, animate=False)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._bind_shortcuts()
        self._install_dnd()
        self._update_notification_badge()
        self._update_status_bar()
        self._collect_spacings()
        self._poll_job = self.after(100, self._poll_events)
        self._status_job = self.after(2600, self._tick_status_bar)
        self.after(30, self._move_indicator)
        self.after(60, self._fade_in)
        self._start_clipboard_watch()
        self.after(2500, self._auto_check_updates)
        # Only the real app shows the first-run tour.  Tests inject their own
        # stores and run headless-style update loops, where a modal grab would
        # interfere with assertions.
        import sys as _sys
        _is_test = "test" in Path(_sys.argv[0]).stem.lower()
        if (config is None and history is None and failures is None
                and not _is_test
                and not getattr(self.settings, "onboarding_done", False)):
            self.after(1600, self._open_onboarding)
        log.info("Application started (language=%s, theme=%s, palette=%s, ffmpeg=%s)",
                 self.settings.language, self.settings.theme, self.settings.palette,
                 self.ffmpeg.describe() if self.ffmpeg else "missing")

    # ==================================================================
    # Text helpers
    # ==================================================================
    def T(self, key: str, **kwargs) -> str:
        return shape_for_tk(translate(self.settings.language, key, **kwargs), self.settings.language)

    def S(self, text: str) -> str:
        return shape_for_tk(text, self.settings.language)

    @property
    def text_anchor(self) -> str:
        return "e" if is_rtl(self.settings.language) else "w"

    @property
    def text_justify(self) -> str:
        return "right" if is_rtl(self.settings.language) else "left"

    @property
    def palette_tokens(self) -> dict[str, tuple[str, str]]:
        return theme_tokens(self.settings.palette)

    @property
    def color_muted(self) -> tuple[str, str]:
        return MUTED

    @property
    def animations_enabled(self) -> bool:
        return not bool(self.settings.reduce_motion)

    @property
    def sidebar_width(self) -> int:
        return SIDEBAR_COLLAPSED_WIDTH if self.sidebar_collapsed else SIDEBAR_WIDTH

    @property
    def _start_sticky(self) -> str:
        return "e" if is_rtl(self.settings.language) else "w"

    @property
    def _end_sticky(self) -> str:
        return "w" if is_rtl(self.settings.language) else "e"

    def _grid_col(self, logical: int, total: int) -> int:
        """Map a logical (reading-order) grid column to the visual one."""
        return total - 1 - logical if is_rtl(self.settings.language) else logical

    def _pad(self, start: int, end: int) -> tuple[int, int]:
        """Return grid/pack padding for a start/end pair in reading order."""
        return (end, start) if is_rtl(self.settings.language) else (start, end)

    # ------------------------------------------------------------------
    # Live responsive sizing
    # ------------------------------------------------------------------
    def _font_size(self, base_size: int) -> int:
        """Font size combining the saved preference and the live window scale."""
        preference = 1.16 if self.settings.ui_scale == "large" else 1.0
        return max(9, int(round(int(base_size) * preference * self._ui_scale_factor)))

    def _scaled_pair(self, base_size: tuple[int, int]) -> tuple[int, int]:
        return tuple(
            max(1, int(round(value * self._ui_scale_factor)))
            for value in base_size
        )

    def _register_font(self, font, base_size: int):
        """Make one CTkFont resizable in place; returns the same object."""
        if font is None:
            return None
        base = int(base_size or getattr(font, "_ui_base_size", 0) or 13)
        font._ui_base_size = base
        try:
            font.configure(size=self._font_size(base))
        except Exception:
            pass
        self._scale_fonts.append(weakref.ref(font))
        return font

    def _font(self, size: int, *, family: str = "Segoe UI", **kwargs):
        """Create a registered font so it follows both UI scale and window size."""
        return self._register_font(
            ctk.CTkFont(family=family, size=int(size), **kwargs), int(size)
        )

    def _register_image(self, image, base_size: tuple[int, int]):
        """Make one CTkImage resizable in place; returns the same object."""
        if image is None:
            return None
        base = (int(base_size[0]), int(base_size[1]))
        image._ui_base_size = base
        try:
            image.configure(size=self._scaled_pair(base))
        except Exception:
            pass
        self._scale_images.append(weakref.ref(image))
        return image

    def _register_shape(self, widget, width: int | None = None, height: int | None = None):
        """Remember a widget's base dimensions so they can be scaled in place."""
        if widget is None:
            return None
        widget._ui_base_shape = (width, height)
        kwargs = {}
        if width is not None:
            kwargs["width"] = max(1, int(round(width * self._ui_scale_factor)))
        if height is not None:
            kwargs["height"] = max(1, int(round(height * self._ui_scale_factor)))
        if kwargs:
            try:
                widget.configure(**kwargs)
            except Exception:
                pass
        self._scale_shapes.append(weakref.ref(widget))
        return widget

    def _fonts(self) -> None:
        family = "Segoe UI"
        self.f_logo = self._font(26, family=family, weight="bold")
        self.f_h1 = self._font(20, family=family, weight="bold")
        self.f_h2 = self._font(15, family=family, weight="bold")
        self.f_body = self._font(13, family=family)
        self.f_body_bold = self._font(13, family=family, weight="bold")
        self.f_small = self._font(12, family=family)
        self.f_small_bold = self._font(12, family=family, weight="bold")

    def _on_window_resize(self, event=None) -> None:
        """Coalesce a drag burst into one idle-time scaling pass."""
        if event is not None and getattr(event, "widget", self) is not self:
            return
        width = int(self.winfo_width())
        height = int(self.winfo_height())
        if width <= 60 or height <= 60:
            return
        self._resize_size = (width, height)
        if self._resize_job is None:
            self._resize_job = self.after_idle(self._apply_window_scale)

    def _apply_window_scale(self) -> None:
        """Track the window dimensions, then refresh sizes when they change."""
        self._resize_job = None
        width, height = self._resize_size
        if width <= 0 or height <= 0:
            return
        raw = min(width / BASE_WINDOW_SIZE[0], height / BASE_WINDOW_SIZE[1])
        raw = max(MIN_WINDOW_SCALE, min(MAX_WINDOW_SCALE, raw))
        factor = round(round(raw / WINDOW_SCALE_STEP) * WINDOW_SCALE_STEP, 2)
        if abs(factor - self._ui_scale_factor) < 0.001:
            return
        self._ui_scale_factor = factor
        self._refresh_registered_sizes()

    @staticmethod
    def _parse_pad(value) -> int | tuple[int, int] | None:
        try:
            parts = str(value).split()
            if not parts:
                return None
            if len(parts) == 1:
                return int(float(parts[0]))
            return (int(float(parts[0])), int(float(parts[1])))
        except Exception:
            return None

    def _scale_pad(self, value):
        if isinstance(value, tuple):
            return tuple(max(0, int(round(v * self._ui_scale_factor))) for v in value)
        return max(0, int(round(value * self._ui_scale_factor)))

    def _register_spacing(self, widget, geometry: str, base: dict) -> None:
        widget._ui_spacing = (geometry, base)
        self._scale_spacings.append(weakref.ref(widget))

    def _collect_spacings(self) -> None:
        """Record existing pack/grid padding once so it can scale in place."""
        self._scale_spacings.clear()

        def walk(parent):
            for child in parent.winfo_children():
                yield child
                yield from walk(child)

        for widget in walk(self):
            try:
                if not widget.winfo_exists():
                    continue
                info = widget.grid_info() or widget.pack_info()
                if not info:
                    continue
                geometry = "grid" if widget.grid_info() else "pack"
                base = {}
                for key in ("padx", "pady", "ipadx", "ipady"):
                    if key not in info:
                        continue
                    value = self._parse_pad(info[key])
                    if value in (None, 0, (0, 0)):
                        continue
                    base[key] = value
                if base:
                    self._register_spacing(widget, geometry, base)
            except Exception:
                continue

    def _apply_spacings(self) -> None:
        for ref in list(self._scale_spacings):
            widget = ref()
            if widget is None:
                self._scale_spacings.remove(ref)
                continue
            try:
                if not widget.winfo_exists():
                    self._scale_spacings.remove(ref)
                    continue
                geometry, base = widget._ui_spacing
                kwargs = {key: self._scale_pad(value) for key, value in base.items()}
                if geometry == "grid":
                    widget.grid_configure(**kwargs)
                else:
                    widget.pack_configure(**kwargs)
            except Exception:
                pass

    def _refresh_registered_sizes(self) -> None:
        """Reconfigure registered objects only — never rebuild the UI."""
        factor = self._ui_scale_factor
        for ref in list(self._scale_fonts):
            font = ref()
            if font is None:
                self._scale_fonts.remove(ref)
                continue
            try:
                font.configure(size=self._font_size(font._ui_base_size))
            except Exception:
                pass

        for ref in list(self._scale_images):
            image = ref()
            if image is None:
                self._scale_images.remove(ref)
                continue
            try:
                image.configure(size=self._scaled_pair(image._ui_base_size))
            except Exception:
                pass

        for ref in list(self._scale_shapes):
            widget = ref()
            if widget is None:
                self._scale_shapes.remove(ref)
                continue
            base_w, base_h = widget._ui_base_shape
            kwargs = {}
            if base_w is not None:
                kwargs["width"] = max(1, int(round(base_w * factor)))
            if base_h is not None:
                kwargs["height"] = max(1, int(round(base_h * factor)))
            if kwargs:
                try:
                    widget.configure(**kwargs)
                except Exception:
                    pass

        self._apply_spacings()
        self._apply_history_columns()
        self._rescale_preview_thumbnail()

    def _apply_history_columns(self, force: bool = False) -> None:
        """Re-grid existing library cards when the card count per row changes.

        This only re-grids widgets that already exist — it never destroys or
        recreates cards during a resize, which was the old source of stutter.
        """
        self._history_layout_job = None
        if getattr(self, "library_view", "grid") != "grid":
            return
        scroll = getattr(self, "history_scroll", None)
        if scroll is None or not scroll.winfo_exists():
            return
        cards = [
            card for card in self.history_rows.values()
            if getattr(card, "winfo_exists", lambda: False)()
        ]
        if not cards:
            return
        try:
            available = int(scroll.winfo_width())
        except Exception:
            available = 0
        if available < 220:
            available = max(260, int(self.winfo_width()) - 150)
        available = max(260, available - 20)  # room for the scrollbar
        gap = max(4, int(round(8 * self._ui_scale_factor)))
        base_card = max(150, int(round(240 * self._ui_scale_factor)))
        columns = max(1, min(4, (available + gap) // (base_card + gap)))
        if columns == self._history_columns and not force:
            return
        self._history_columns = columns
        cell = max(120, (available - gap * (columns - 1)) // columns)
        for column in range(4):
            scroll.grid_columnconfigure(
                column, weight=1 if column < columns else 0,
                uniform="history_card" if column < columns else "",
            )
        for index, card in enumerate(cards):
            try:
                card.configure(width=cell)
                card.grid(
                    row=index // columns,
                    column=index % columns,
                    padx=(gap // 2, gap // 2),
                    pady=gap,
                    sticky="nsew",
                )
            except Exception:
                pass

    def _thumb_display_size(self, frame_scale: float = 1.0) -> tuple[int, int]:
        scaled = self._ui_scale_factor * float(frame_scale)
        return (
            max(1, int(round(THUMB_SIZE[0] * scaled))),
            max(1, int(round(THUMB_SIZE[1] * scaled))),
        )

    def _rescale_preview_thumbnail(self) -> None:
        image = self._thumb_image
        label = getattr(self, "thumb_label", None)
        if image is None or label is None:
            return
        try:
            if not label.winfo_exists():
                return
            size = self._thumb_display_size(self._thumb_frame_scale)
            image.configure(size=size)
            label.configure(width=size[0], height=size[1])
        except Exception:
            pass

    def _set_window_icon(self) -> None:
        try:
            icon = tk.PhotoImage(file=str(resource_path("assets/icon.png")))
            self.iconphoto(True, icon)
            self._icon_image = icon
        except Exception:
            self._icon_image = None

    # ------------------------------------------------------------------
    def _label(self, parent, key: str, **kwargs) -> ctk.CTkLabel:
        kwargs.setdefault("anchor", self.text_anchor)
        kwargs.setdefault("justify", self.text_justify)
        widget = ctk.CTkLabel(parent, text=self.T(key), **kwargs)
        self._static_bindings.append((widget, key))
        return widget

    def _button(self, parent, key: str, command, **kwargs) -> ctk.CTkButton:
        kwargs.setdefault("fg_color", ACCENT)
        kwargs.setdefault("hover_color", ACCENT_HOVER)
        widget = ctk.CTkButton(parent, text=self.T(key), command=command, **kwargs)
        self._static_bindings.append((widget, key))
        return widget

    def _start_side(self) -> str:
        return "right" if is_rtl(self.settings.language) else "left"

    def _end_side(self) -> str:
        return "left" if is_rtl(self.settings.language) else "right"

    def _autowrap(self, label: ctk.CTkLabel, padding: int = 4) -> None:
        """Keep a label wrapping exactly to the width its container gives it.

        The wrap length is derived from the *parent* width and only applied
        when it changes. Setting it from the label's own width makes the label
        resize itself, which feeds a Configure loop that never settles.
        """
        master = label.master
        state = {"width": -1, "job": None}

        def apply() -> None:
            state["job"] = None
            width = state["width"]
            if width <= 60:
                return
            target = max(60, width - padding)
            try:
                current = int(label.cget("wraplength") or 0)
            except Exception:
                current = -1
            if current != target:
                try:
                    label.configure(wraplength=target)
                except Exception:
                    pass

        def on_configure(event) -> None:
            width = int(event.width)
            if width <= 60 or width == state["width"]:
                return
            state["width"] = width
            # Collapse a whole drag burst into a single idle-time update.
            if state["job"] is None:
                state["job"] = self.after_idle(apply)

        master.bind("<Configure>", on_configure, add="+")

    # ==================================================================
    # Window construction
    # ==================================================================
    def _build_window(self) -> None:
        # The OS title bar renders Arabic natively, so the raw text is used
        # here instead of the shaped string meant for Tk labels.
        self.title(translate(self.settings.language, "app_title"))
        self.geometry(self.settings.window_geometry)
        self.minsize(1040, 740)
        self.bind("<Configure>", self._on_window_resize, add="+")
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(0, weight=1)

    def _load_logo(self, size: int = 44) -> ctk.CTkImage | None:
        candidates = [
            resource_path("assets/logo.png"),
            BASE_DIR / "logo.png",
            resource_path("assets/icon.png"),
        ]
        for path in candidates:
            try:
                if not Path(path).exists():
                    continue
                image = Image.open(path).convert("RGBA")
                image = ImageOps.fit(image, (size, size), Image.LANCZOS)
                return self._register_image(
                    ctk.CTkImage(light_image=image, dark_image=image, size=(size, size)),
                    (size, size),
                )
            except Exception:
                continue
        return None

    def _build_sidebar(self) -> None:
        width = self.sidebar_width
        compact = self.sidebar_collapsed
        sidebar = ctk.CTkFrame(
            self,
            width=width,
            corner_radius=0,
            fg_color=SIDEBAR,
            border_width=1,
            border_color=SIDEBAR_BORDER,
        )
        sidebar.grid(row=0, column=2 if is_rtl(self.settings.language) else 0, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(4, weight=1)
        self.sidebar = sidebar
        self._register_shape(sidebar, width=width)

        # ---- Brand ------------------------------------------------
        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(
            row=0, column=0, sticky="ew",
            padx=(10 if compact else 16), pady=(20, 10),
        )
        brand.grid_columnconfigure(0, weight=1)
        brand.grid_columnconfigure(1, weight=0)
        self.brand = brand

        self._logo_image = self._logo_image or self._load_logo(42)
        if self._logo_image is not None:
            self.brand_logo = ctk.CTkLabel(brand, text="", image=self._logo_image, width=42)
        else:
            self.brand_logo = ctk.CTkLabel(
                brand,
                text="⇩",
                width=42,
                height=42,
                corner_radius=12,
                fg_color=ACCENT,
                text_color="#FFFFFF",
                font=self.f_h2,
            )
        self._register_shape(self.brand_logo, width=42, height=42)

        text_box = ctk.CTkFrame(brand, fg_color="transparent")
        self.brand_text_box = text_box
        self.brand_title = ctk.CTkLabel(
            text_box,
            text=self.T("app_title"),
            font=self.f_h2,
            anchor=self.text_anchor,
            justify=self.text_justify,
            wraplength=140,
        )
        self.brand_title.pack(anchor=self.text_anchor, fill="x")
        self.brand_version = ctk.CTkLabel(
            text_box,
            text=f"v{APP_VERSION}",
            font=self.f_small,
            text_color=MUTED,
            anchor=self.text_anchor,
        )
        self.brand_version.pack(anchor=self.text_anchor, fill="x")

        # ---- Section caption --------------------------------------
        self.nav_caption = ctk.CTkLabel(
            sidebar,
            text=self.T("nav_menu"),
            font=self.f_small_bold,
            text_color=MUTED,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.nav_caption.grid(row=2, column=0, sticky="ew", padx=22, pady=(4, 6))
        if compact:
            self.nav_caption.grid_remove()

        # ---- Navigation -------------------------------------------
        nav = ctk.CTkFrame(sidebar, fg_color="transparent")
        nav.grid(row=3, column=0, sticky="ew", padx=10)
        nav.grid_columnconfigure(0, weight=1)
        self.nav_frame = nav

        self.nav_items: list[NavItem] = []
        nav_specs = (
            ("⌂", "tab_home", 0, "nav_home_tip"),
            ("↓", "tab_download", 1, "nav_download_tip"),
            ("▶", "tab_active", 2, "nav_active_tip"),
            ("≡", "tab_queue", 3, "nav_queue_tip"),
            ("▣", "tab_library", 4, "nav_library_tip"),
            ("↺", "tab_history", 5, "nav_history_tip"),
            ("✂", "tab_tools", 6, "nav_tools_tip"),
            ("⚙", "tab_settings", 7, "nav_settings_tip"),
        )
        for row, (icon, key, index, tip_key) in enumerate(nav_specs):
            item = NavItem(
                nav,
                icon=icon,
                label=self.T(key),
                command=lambda i=index: self._switch_page(i),
                app=self,
            )
            item.tooltip.update_text(self.T(tip_key))
            item.grid(row=row, column=0, sticky="ew", pady=3)
            self.nav_items.append(item)

        self.nav_indicator = ctk.CTkFrame(
            sidebar, width=4, height=26, corner_radius=2, fg_color=ACCENT
        )
        self.nav_indicator.place(
            x=width - 8 if not is_rtl(self.settings.language) else 4,
            y=120,
        )

        # ---- System status ----------------------------------------
        status = ctk.CTkFrame(sidebar, fg_color="transparent")
        status.grid(
            row=5, column=0, sticky="ew",
            padx=(8 if compact else 16), pady=(8, 2),
        )
        status.grid_columnconfigure(0, weight=1)
        self.sidebar_status = status
        ctk.CTkLabel(
            status, text=self.T("sidebar_status"), font=self.f_small_bold,
            text_color=MUTED, anchor=self.text_anchor,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 3))
        self.side_conn_label = ctk.CTkLabel(
            status, text="● " + self.T("status_connection_online"),
            font=self.f_small, text_color=SUCCESS, anchor=self.text_anchor,
        )
        self.side_conn_label.grid(row=1, column=0, sticky="ew")
        self.side_ffmpeg_label = ctk.CTkLabel(
            status,
            text="● " + self.T("status_ffmpeg_ready" if self.ffmpeg else "ffmpeg_missing_short"),
            font=self.f_small,
            text_color=SUCCESS if self.ffmpeg else WARN,
            anchor=self.text_anchor,
        )
        self.side_ffmpeg_label.grid(row=2, column=0, sticky="ew")
        self.side_deno_label = ctk.CTkLabel(
            status,
            text="● " + self.T("status_deno_ready" if self.js_runtimes else "status_deno_missing"),
            font=self.f_small,
            text_color=SUCCESS if self.js_runtimes else WARN,
            anchor=self.text_anchor,
        )
        self.side_deno_label.grid(row=3, column=0, sticky="ew")
        if compact:
            status.grid_remove()

        # ---- Quick toggles ----------------------------------------
        quick = ctk.CTkFrame(sidebar, fg_color="transparent")
        quick.grid(row=6, column=0, sticky="ew", padx=(8 if compact else 14), pady=(8, 14))
        quick.grid_columnconfigure(0, weight=1)
        quick.grid_columnconfigure(1, weight=1)

        button_width = 34 if compact else 88
        self.theme_btn = ctk.CTkButton(
            quick,
            text="☀",
            width=button_width,
            height=34,
            font=self.f_body,
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=self._toggle_theme,
        )
        self.theme_btn.grid(
            row=0, column=self._grid_col(0, 2), sticky="ew", padx=self._pad(0, 3)
        )
        self.theme_tip = Tooltip(self.theme_btn, self.T("theme_toggle_tip"))

        self.lang_btn = ctk.CTkButton(
            quick,
            text="EN",
            width=button_width,
            height=34,
            font=self.f_small_bold,
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=self._toggle_language,
        )
        self.lang_btn.grid(
            row=0, column=self._grid_col(1, 2), sticky="ew", padx=self._pad(3, 0)
        )
        self.lang_tip = Tooltip(self.lang_btn, self.T("lang_toggle_tip"))

        self._layout_brand()

    def _layout_brand(self) -> None:
        rtl = is_rtl(self.settings.language)
        self.brand_logo.grid_forget()
        self.brand_text_box.grid_forget()
        self.brand.grid_columnconfigure(0, weight=1)
        self.brand.grid_columnconfigure(1, weight=0)
        if self.sidebar_collapsed:
            self.brand_logo.grid(row=0, column=0, sticky="")
            return
        if rtl:
            self.brand_text_box.grid(row=0, column=0, sticky="ew", padx=(0, 10))
            self.brand_logo.grid(row=0, column=1, sticky="e")
        else:
            self.brand_logo.grid(row=0, column=0, sticky="w", padx=(0, 10))
            self.brand_text_box.grid(row=0, column=1, sticky="ew")

    def _build_content(self) -> None:
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(22, 22) if not is_rtl(self.settings.language) else (16, 16),
            pady=(18, 8),
        )
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)
        self.content = content

        # ---- Page header ------------------------------------------
        head = ctk.CTkFrame(content, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        head.grid_columnconfigure(0, weight=1)

        self.page_title = ctk.CTkLabel(
            head,
            text=self.T("download_title"),
            font=self.f_h1,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.page_title.grid(row=0, column=0, sticky="ew")

        self.page_subtitle = ctk.CTkLabel(
            head,
            text=self.T("download_subtitle"),
            font=self.f_small,
            text_color=MUTED,
            anchor=self.text_anchor,
            justify=self.text_justify,
            wraplength=720,
        )
        self.page_subtitle.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._autowrap(self.page_subtitle)

        self.header_accent = ctk.CTkFrame(
            head, width=42, height=3, corner_radius=2, fg_color=ACCENT
        )
        self.header_accent.grid(
            row=2,
            column=0,
            sticky="e" if is_rtl(self.settings.language) else "w",
            pady=(10, 0),
        )

        # ---- Header actions: notifications + about ----------------
        actions = ctk.CTkFrame(head, fg_color="transparent")
        actions.grid(
            row=0, column=1, rowspan=2,
            sticky="nw" if is_rtl(self.settings.language) else "ne",
        )

        self.bell_holder = ctk.CTkFrame(actions, fg_color="transparent", width=42, height=38)
        self.bell_holder.pack(side=self._start_side(), padx=(0, 6) if not is_rtl(self.settings.language) else (6, 0))
        self.bell_holder.pack_propagate(False)
        self.bell_btn = ctk.CTkButton(
            self.bell_holder,
            text="🔔",
            width=38,
            height=36,
            font=self._font(16, family="Segoe UI Symbol"),
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=self._open_notifications,
        )
        self.bell_btn.pack(fill="both", expand=True)
        self._register_shape(self.bell_holder, width=42, height=38)
        self._register_shape(self.bell_btn, width=38, height=36)
        self.bell_badge = ctk.CTkLabel(
            self.bell_holder,
            text="",
            width=18,
            height=18,
            corner_radius=9,
            fg_color=DANGER,
            text_color="#FFFFFF",
            font=self._font(9, weight="bold"),
        )
        self._register_shape(self.bell_badge, width=18, height=18)
        self.bell_badge.place(relx=0.9, rely=0.12, anchor="center")
        self.bell_badge.place_forget()
        self.bell_tip = Tooltip(self.bell_btn, self.T("notification_bell_tip"))

        self.mini_btn = ctk.CTkButton(
            actions,
            text="▢",
            width=38,
            height=36,
            font=self._font(16, family="Segoe UI Symbol"),
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=self._open_mini_mode,
        )
        self._register_shape(self.mini_btn, width=38, height=36)
        self.mini_btn.pack(side=self._start_side())
        self.mini_tip = Tooltip(self.mini_btn, self.T("mini_mode_tip"))

        self.about_btn = ctk.CTkButton(
            actions,
            text="ⓘ",
            width=38,
            height=36,
            font=self._font(16, family="Segoe UI Symbol"),
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=self._open_about,
        )
        self._register_shape(self.about_btn, width=38, height=36)
        self.about_btn.pack(side=self._start_side())
        self.about_tip = Tooltip(self.about_btn, self.T("about_title"))

        # ---- Pages ------------------------------------------------
        self.pages_host = ctk.CTkFrame(content, fg_color="transparent")
        self.pages_host.grid(row=1, column=0, sticky="nsew")
        self.pages_host.grid_rowconfigure(0, weight=1)
        self.pages_host.grid_columnconfigure(0, weight=1)

        # ---- Status bar -------------------------------------------
        bar = ctk.CTkFrame(content, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(6, 2))
        bar.grid_columnconfigure(self._grid_col(0, 6), weight=1)

        self.status_label = ctk.CTkLabel(
            bar,
            text=self.T("status_ready"),
            font=self.f_small,
            text_color=MUTED,
            anchor=self.text_anchor,
        )
        self.status_label.grid(row=0, column=self._grid_col(0, 6), sticky="ew")

        self.conn_label = ctk.CTkLabel(
            bar,
            text="● " + self.T("status_connection_online"),
            font=self.f_small,
            text_color=SUCCESS,
            anchor=self.text_anchor,
        )
        self.conn_label.grid(
            row=0, column=self._grid_col(1, 6), sticky=self._end_sticky,
            padx=self._pad(8, 0),
        )

        self.total_speed_label = ctk.CTkLabel(
            bar,
            text=self.T("status_total_speed", speed="—"),
            font=self.f_small,
            text_color=MUTED,
            anchor=self.text_anchor,
        )
        self.total_speed_label.grid(
            row=0, column=self._grid_col(2, 6), sticky=self._end_sticky,
            padx=self._pad(8, 0),
        )

        self.space_label = ctk.CTkLabel(
            bar,
            text=self.T("status_space", free="—"),
            font=self.f_small,
            text_color=MUTED,
            anchor=self.text_anchor,
        )
        self.space_label.grid(
            row=0, column=self._grid_col(3, 6), sticky=self._end_sticky,
            padx=self._pad(8, 0),
        )

        self.ffmpeg_chip = ctk.CTkLabel(
            bar,
            text="",
            font=self.f_small_bold,
            corner_radius=8,
            height=22,
            padx=8,
            fg_color=SOFT_BUTTON,
        )
        self.ffmpeg_chip.grid(
            row=0, column=self._grid_col(4, 6), sticky=self._end_sticky,
            padx=self._pad(6, 0),
        )

        self.js_chip = ctk.CTkLabel(
            bar,
            text="",
            font=self.f_small_bold,
            corner_radius=8,
            height=22,
            padx=8,
            fg_color=SOFT_BUTTON,
        )
        self.js_chip.grid(
            row=0, column=self._grid_col(5, 6), sticky=self._end_sticky,
            padx=self._pad(6, 0),
        )
        self._refresh_chips()

    def _refresh_chips(self) -> None:
        if self.ffmpeg:
            self.ffmpeg_chip.configure(text="FFmpeg ✓", text_color=SUCCESS)
        else:
            self.ffmpeg_chip.configure(
                text=self.T("ffmpeg_missing_short"), text_color=WARN
            )
        if self.js_runtimes:
            self.js_chip.configure(text="Deno ✓", text_color=SUCCESS)
        else:
            self.js_chip.configure(text="Deno ✕", text_color=WARN)

    def _build_pages(self) -> None:
        def scroll_page() -> ctk.CTkScrollableFrame:
            return ctk.CTkScrollableFrame(
                self.pages_host, fg_color="transparent", corner_radius=0
            )

        self.page_home = scroll_page()
        self.page_download = ctk.CTkFrame(self.pages_host, fg_color="transparent")
        self.page_active = scroll_page()
        self.page_queue = scroll_page()
        self.page_completed = scroll_page()
        self.page_history = ctk.CTkFrame(self.pages_host, fg_color="transparent")
        self.page_tools = scroll_page()
        self.page_settings = scroll_page()
        self.pages = [
            self.page_home,
            self.page_download,
            self.page_active,
            self.page_queue,
            self.page_completed,
            self.page_history,
            self.page_tools,
            self.page_settings,
        ]
        for page in self.pages:
            page.place(x=0, y=0, relwidth=1, relheight=1)
            page.lower()

        self._build_home_page()
        self._build_download_page()
        self._build_active_page()
        self._build_queue_page()
        self._build_completed_page()
        self._build_history_page()
        self._build_tools_page()
        self._build_settings_page()
        self._build_workspace_page()
        # Widgets are new after a rebuild, so invalidate all refresh caches.
        self._home_recent_sig = None
        self._active_page_sig = None
        self._queue_page_sig = None
        self._completed_page_sig = None
        self._queue_bars = {}
        self._active_bars = {}

    def _card(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            corner_radius=18,
            fg_color=CARD,
            border_width=1,
            border_color=CARD_BORDER,
        )

    def _step_header(self, parent, number: str, key: str) -> ctk.CTkFrame:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        badge = ctk.CTkLabel(
            row,
            text=number,
            width=24,
            height=24,
            corner_radius=12,
            fg_color=ACCENT_SOFT,
            text_color=ACCENT,
            font=self.f_small_bold,
        )
        badge.pack(side=self._start_side(), padx=(0, 8) if not is_rtl(self.settings.language) else (8, 0))
        label = self._label(row, key, font=self.f_h2)
        label.pack(side=self._start_side())
        return row

    def _layout_options_rows(self) -> None:
        """Mirror the mode/quality pair and the destination row for the language."""
        start = self._start_side()
        for box in (self.mode_box, self.quality_box, self.bw_box, self.group_box):
            box.pack_forget()
        self.mode_box.pack(side=start, fill="x", expand=True, padx=(4, 4))
        self.quality_box.pack(side=start, fill="x", expand=True, padx=(4, 4))
        self.bw_box.pack(side=start, fill="x", expand=True, padx=(4, 4))
        self.group_box.pack(side=start, fill="x", expand=True, padx=(4, 4))

    def _layout_dest_row(self) -> None:
        rtl = is_rtl(self.settings.language)
        self.dest_entry.pack_forget()
        self.browse_btn.pack_forget()
        if rtl:
            self.browse_btn.pack(side="right", padx=(0, 6))
            self.dest_entry.pack(side="right", fill="x", expand=True)
        else:
            self.browse_btn.pack(side="left", padx=(6, 0))
            self.dest_entry.pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------------
    # Download tab
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Home / queue / completed pages
    # ------------------------------------------------------------------
    def _build_home_page(self) -> None:
        """Premium dashboard: hero, KPIs, quick actions, stats, recent, storage."""
        page = self.page_home
        page.grid_columnconfigure(0, weight=3)
        page.grid_columnconfigure(1, weight=2)

        # ---- Hero ------------------------------------------------------
        hero = self._card(page)
        hero.grid(
            row=0, column=0, columnspan=2, sticky="ew",
            padx=self._pad(10, 10), pady=(10, 12),
        )
        hero.grid_columnconfigure(self._grid_col(0, 2), weight=1)
        copy = ctk.CTkFrame(hero, fg_color="transparent")
        copy.grid(
            row=0, column=self._grid_col(0, 2), sticky="ew",
            padx=self._pad(18, 6), pady=(16, 14),
        )
        copy.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            copy, text=self.T("app_title"), font=self.f_h1,
            anchor=self.text_anchor, justify=self.text_justify,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            copy, text=self.T("app_subtitle"), font=self.f_small,
            text_color=MUTED, anchor=self.text_anchor, justify=self.text_justify,
            wraplength=560,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        hero_actions = ctk.CTkFrame(hero, fg_color="transparent")
        hero_actions.grid(
            row=0, column=self._grid_col(1, 2), sticky="ns",
            padx=self._pad(6, 18), pady=16,
        )
        self._button(
            hero_actions, "tab_download", lambda: self._switch_page(1),
            width=150, height=36,
        ).pack(pady=(0, 6))
        self._button(
            hero_actions, "tab_tools", lambda: self._switch_page(6),
            width=150, height=36,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        ).pack(pady=(0, 6))
        self._button(
            hero_actions, "workspace_open", self._toggle_workspace,
            width=150, height=36,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        ).pack()

        # ---- KPI cards --------------------------------------------------
        stats = ctk.CTkFrame(page, fg_color="transparent")
        stats.grid(row=1, column=0, columnspan=2, sticky="ew", padx=self._pad(10, 10))
        for i in range(4):
            stats.grid_columnconfigure(i, weight=1)
        self.home_kpis: dict[str, ctk.CTkLabel] = {}
        for i, (key, label_key) in enumerate(
            (
                ("total", "home_stats_total"),
                ("active", "home_stats_active"),
                ("completed", "home_stats_completed"),
                ("size", "home_stats_size"),
            )
        ):
            card = self._card(stats)
            card.grid(
                row=0, column=i, sticky="ew",
                padx=self._pad(0 if i == 0 else 5, 5 if i < 3 else 0),
                ipady=4,
            )
            ctk.CTkFrame(
                card, height=3, corner_radius=2, fg_color=ACCENT
            ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
            ctk.CTkLabel(
                card, text=self.T(label_key), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 0))
            value = ctk.CTkLabel(card, text="—", font=self.f_h1, anchor=self.text_anchor)
            value.grid(row=2, column=0, sticky="ew", padx=14, pady=(2, 14))
            self.home_kpis[key] = value

        # ---- Quick actions ---------------------------------------------
        quick = self._card(page)
        quick.grid(
            row=2, column=0, columnspan=2, sticky="ew",
            padx=self._pad(10, 10), pady=(12, 12),
        )
        quick.grid_columnconfigure(self._grid_col(0, 2), weight=1)
        ctk.CTkLabel(
            quick, text=self.T("home_quick_actions"), font=self.f_h2,
            anchor=self.text_anchor,
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 6))
        self.home_url = ctk.CTkEntry(
            quick, placeholder_text="https://...", font=self.f_small, height=36
        )
        self.home_url.grid(
            row=1, column=self._grid_col(0, 2), sticky="ew",
            padx=self._pad(16, 6), pady=(0, 8),
        )
        self.home_url.bind("<Return>", lambda _e: self._home_go())
        self._button(
            quick, "home_go", self._home_go, height=36,
        ).grid(
            row=1, column=self._grid_col(1, 2), sticky="ew",
            padx=self._pad(6, 16), pady=(0, 8),
        )
        chips = ctk.CTkFrame(quick, fg_color="transparent")
        chips.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 14))
        for i, (key, target) in enumerate(
            (("tab_active", 2), ("tab_queue", 3), ("tab_library", 4), ("tab_history", 5))
        ):
            self._button(
                chips, key, lambda p=target: self._switch_page(p),
                height=30, fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER,
                text_color=SOFT_TEXT, font=self.f_small,
            ).grid(row=0, column=i, sticky="ew", padx=self._pad(0 if i == 0 else 5, 5 if i < 3 else 0))

        # ---- Advanced statistics ---------------------------------------
        advanced = self._card(page)
        advanced.grid(
            row=3, column=self._grid_col(0, 2), sticky="ew",
            padx=self._pad(10, 6), pady=(0, 12),
        )
        advanced.grid_columnconfigure(0, weight=1)
        stats_head = ctk.CTkFrame(advanced, fg_color="transparent")
        stats_head.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        stats_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            stats_head, text=self.T("stats_panel_title"),
            font=self.f_h2, anchor=self.text_anchor,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            stats_head, text=self.T("stats_refresh"), width=82, height=26,
            font=self.f_small, fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT, command=self._refresh_home_page,
        ).grid(row=0, column=1, padx=6)
        metrics = ctk.CTkFrame(advanced, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        for c in range(3):
            metrics.grid_columnconfigure(c, weight=1)
        self.stats_labels: dict[str, ctk.CTkLabel] = {}
        for i, key in enumerate(("stats_today", "stats_month", "stats_total")):
            box = ctk.CTkFrame(metrics, fg_color=SOFT_BUTTON, corner_radius=10)
            box.grid(
                row=0, column=i, sticky="ew",
                padx=self._pad(0 if i == 0 else 5, 5 if i < 2 else 0),
            )
            ctk.CTkLabel(
                box, text=self.T(key), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
            value = ctk.CTkLabel(box, text="—", font=self.f_small_bold, anchor=self.text_anchor)
            value.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 10))
            self.stats_labels[key] = value
        self.stats_14_label = ctk.CTkLabel(
            advanced, text=self.T("stats_last14"), font=self.f_small,
            text_color=MUTED, anchor=self.text_anchor,
        )
        self.stats_14_label.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))

        # ---- Recent downloads ------------------------------------------
        recent = self._card(page)
        recent.grid(
            row=4, column=self._grid_col(0, 2), sticky="nsew",
            padx=self._pad(10, 6), pady=(0, 12),
        )
        recent.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            recent, text=self.T("home_recent"), font=self.f_h2, anchor=self.text_anchor
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        self.home_recent_host = ctk.CTkFrame(recent, fg_color="transparent")
        self.home_recent_host.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 12))
        self.home_recent_host.grid_columnconfigure(0, weight=1)

        # ---- Storage ----------------------------------------------------
        storage = self._card(page)
        storage.grid(
            row=3, column=self._grid_col(1, 2), rowspan=2, sticky="nsew",
            padx=self._pad(6, 10), pady=(0, 12),
        )
        storage.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            storage, text=self.T("home_storage"), font=self.f_h2,
            anchor=self.text_anchor,
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        self.home_space_label = ctk.CTkLabel(
            storage, text="—", font=self.f_h1, text_color=ACCENT,
            anchor=self.text_anchor,
        )
        self.home_space_label.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 0))
        ctk.CTkLabel(
            storage, text=self.T("home_storage_path"), font=self.f_small,
            text_color=MUTED, anchor=self.text_anchor,
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 0))
        self.home_folder_label = ctk.CTkLabel(
            storage, text=str(self.settings.download_dir), font=self.f_small,
            text_color=SOFT_TEXT, anchor=self.text_anchor,
            justify=self.text_justify, wraplength=240,
        )
        self.home_folder_label.grid(row=3, column=0, sticky="ew", padx=16, pady=(2, 10))
        self._button(
            storage, "home_open_folder", lambda: reveal_in_folder(self.settings.download_dir),
            height=32, fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT, font=self.f_small,
        ).grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 14))

    def _home_go(self) -> None:
        url = self.home_url.get().strip()
        if not url:
            return
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url)
        self.home_url.delete(0, "end")
        self._switch_page(1)
        self.after(120, self.fetch_media)

    def _build_active_page(self) -> None:
        """Skeleton for the live-downloads page (filled in step 4)."""
        page = self.page_active
        page.grid_columnconfigure(0, weight=1)
        host = self._card(page)
        host.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        host.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            host, text=self.T("active_title"), font=self.f_h2,
            anchor=self.text_anchor, justify=self.text_justify,
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 2))
        ctk.CTkLabel(
            host, text=self.T("active_subtitle"), font=self.f_small,
            text_color=MUTED, anchor=self.text_anchor, justify=self.text_justify,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))

        # Failed Center + groups entry points — keeps the 8-item sidebar intact.
        head_actions = ctk.CTkFrame(host, fg_color="transparent")
        head_actions.grid(
            row=0, column=1, rowspan=2, sticky=self._end_sticky,
            padx=self._pad(0, 16), pady=(14, 0),
        )
        self.failed_center_btn = self._button(
            head_actions, "failed_center_btn", self._open_failed_center,
            height=32, width=132, font=self.f_small, corner_radius=8,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.failed_center_btn.pack(side=self._start_side(), padx=(0, 6))
        self._button(
            head_actions, "groups_manage", self._open_groups,
            height=32, width=128, font=self.f_small, corner_radius=8,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        ).pack(side=self._start_side())
        self.failed_count_label = ctk.CTkLabel(
            host, text="", font=self.f_small_bold, text_color=DANGER,
            anchor=self.text_anchor, justify=self.text_justify,
        )
        self.failed_count_label.grid(
            row=1, column=1, sticky=self._end_sticky, padx=self._pad(0, 16), pady=(0, 10)
        )
        self._update_failed_badge()

        self.active_host = ctk.CTkFrame(host, fg_color="transparent")
        self.active_host.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 14))
        self.active_host.grid_columnconfigure(0, weight=1)

    def _build_tools_page(self) -> None:
        """FFmpeg-powered media utilities, each executed off the UI thread."""
        page = self.page_tools
        page.grid_columnconfigure(0, weight=1)
        host = self._card(page)
        host.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        host.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            host, text=self.T("tools_title"), font=self.f_h2,
            anchor=self.text_anchor, justify=self.text_justify,
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 2))
        ctk.CTkLabel(
            host, text=self.T("tools_subtitle"), font=self.f_small,
            text_color=MUTED, anchor=self.text_anchor, justify=self.text_justify,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.tools_host = ctk.CTkFrame(host, fg_color="transparent")
        self.tools_host.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 14))
        self.tools_host.grid_columnconfigure(0, weight=1)

        self.tool_files: dict[str, str] = {}
        self.tool_file_labels: dict[str, ctk.CTkLabel] = {}
        self.tool_status_labels: dict[str, ctk.CTkLabel] = {}
        self.tool_widgets: dict[str, dict] = {}
        self._tool_busy = False

        specs = (
            ("extract", "tool_extract_title", "tool_extract_desc"),
            ("compress", "tool_compress_title", "tool_compress_desc"),
            ("trim", "tool_trim_title", "tool_trim_desc"),
        ) + EXTRA_TOOL_SPECS
        for index, (tool, title_key, desc_key) in enumerate(specs):
            card = self._card(self.tools_host)
            card.grid(row=index, column=0, sticky="ew", pady=(0 if index == 0 else 8, 8))
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                card, text=self.T(title_key), font=self.f_h2,
                anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 2))
            ctk.CTkLabel(
                card, text=self.T(desc_key), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

            file_row = ctk.CTkFrame(card, fg_color="transparent")
            file_row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))
            file_row.grid_columnconfigure(0, weight=1)
            self._button(
                file_row, "tool_choose", lambda t=tool: self._choose_tool_file(t),
                height=30, width=110, font=self.f_small,
                fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
            ).grid(row=0, column=self._grid_col(0, 2), sticky="ew", padx=self._pad(0, 6))
            path_label = ctk.CTkLabel(
                file_row, text="—", font=self.f_small,
                text_color=SOFT_TEXT, anchor=self.text_anchor,
            )
            path_label.grid(
                row=0, column=self._grid_col(1, 2), sticky="ew",
                padx=self._pad(6, 0),
            )
            self.tool_file_labels[tool] = path_label

            next_row = self._build_tool_options(card, tool, 3)

            status = ctk.CTkLabel(
                card, text=self.T("tool_ready"), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            )
            status.grid(row=next_row, column=0, sticky="ew", padx=16, pady=(2, 6))
            self.tool_status_labels[tool] = status
            self._button(
                card, "tool_run", lambda t=tool: self._run_tool(t),
                height=32, width=120, font=self.f_small,
            ).grid(row=next_row + 1, column=0, sticky=self._start_sticky, padx=16, pady=(0, 14))

    def _build_tool_options(self, card, tool: str, row: int) -> int:
        """Add per-tool controls; return the next free grid row on *card*."""
        widgets: dict = {}
        self.tool_widgets[tool] = widgets

        if tool == "trim":
            pair = ctk.CTkFrame(card, fg_color="transparent")
            pair.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 6))
            pair.grid_columnconfigure(0, weight=1)
            pair.grid_columnconfigure(1, weight=1)
            self.tool_trim_start = ctk.CTkEntry(
                pair, placeholder_text=self.T("tool_start"), font=self.f_small, height=30
            )
            self.tool_trim_start.grid(
                row=0, column=self._grid_col(0, 2), sticky="ew", padx=self._pad(0, 5)
            )
            self.tool_trim_duration = ctk.CTkEntry(
                pair, placeholder_text=self.T("tool_duration"), font=self.f_small, height=30
            )
            self.tool_trim_duration.grid(
                row=0, column=self._grid_col(1, 2), sticky="ew", padx=self._pad(5, 0)
            )
            widgets["start"] = self.tool_trim_start
            widgets["duration"] = self.tool_trim_duration
            return row + 1

        if tool == "convert":
            holder = ctk.CTkFrame(card, fg_color="transparent")
            holder.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 6))
            holder.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                holder, text=self.T("tool_format"), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=0, column=self._grid_col(0, 2), sticky="ew", padx=self._pad(0, 8))
            var = tk.StringVar(value=CONVERT_FORMATS[0])
            ctk.CTkOptionMenu(
                holder, variable=var, values=list(CONVERT_FORMATS),
                font=self.f_small, height=30, corner_radius=8,
            ).grid(row=0, column=self._grid_col(1, 2), sticky="ew", padx=self._pad(8, 0))
            widgets["format"] = var
            return row + 1

        if tool == "gif":
            first = ctk.CTkFrame(card, fg_color="transparent")
            first.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 6))
            first.grid_columnconfigure(0, weight=1)
            first.grid_columnconfigure(1, weight=1)
            widgets["start"] = ctk.CTkEntry(
                first, placeholder_text=self.T("tool_start"), font=self.f_small, height=30
            )
            widgets["start"].grid(
                row=0, column=self._grid_col(0, 2), sticky="ew", padx=self._pad(0, 5)
            )
            widgets["duration"] = ctk.CTkEntry(
                first, placeholder_text=self.T("tool_duration"), font=self.f_small, height=30
            )
            widgets["duration"].grid(
                row=0, column=self._grid_col(1, 2), sticky="ew", padx=self._pad(5, 0)
            )
            second = ctk.CTkFrame(card, fg_color="transparent")
            second.grid(row=row + 1, column=0, sticky="ew", padx=14, pady=(0, 6))
            second.grid_columnconfigure(0, weight=1)
            second.grid_columnconfigure(1, weight=1)
            widgets["fps"] = ctk.CTkEntry(
                second, placeholder_text=self.T("tool_fps"), font=self.f_small, height=30
            )
            widgets["fps"].grid(
                row=0, column=self._grid_col(0, 2), sticky="ew", padx=self._pad(0, 5)
            )
            widgets["width"] = ctk.CTkEntry(
                second, placeholder_text=self.T("tool_width"), font=self.f_small, height=30
            )
            widgets["width"].grid(
                row=0, column=self._grid_col(1, 2), sticky="ew", padx=self._pad(5, 0)
            )
            return row + 2

        if tool in ("merge", "subtitle"):
            key = "merge:audio" if tool == "merge" else "subtitle:sub"
            label_key = "tool_choose_audio" if tool == "merge" else "tool_choose_subtitle"
            holder = ctk.CTkFrame(card, fg_color="transparent")
            holder.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 6))
            holder.grid_columnconfigure(1, weight=1)
            self._button(
                holder, label_key, lambda t=tool: self._choose_tool_second(t),
                height=30, width=110, font=self.f_small,
                fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
            ).grid(row=0, column=self._grid_col(0, 2), sticky="ew", padx=self._pad(0, 6))
            path_label = ctk.CTkLabel(
                holder, text="—", font=self.f_small,
                text_color=SOFT_TEXT, anchor=self.text_anchor,
            )
            path_label.grid(row=0, column=self._grid_col(1, 2), sticky="ew", padx=self._pad(6, 0))
            widgets["second_label"] = path_label
            self.tool_files[key] = ""
            return row + 1

        return row

    def _choose_tool_second(self, tool: str) -> None:
        key = "merge:audio" if tool == "merge" else "subtitle:sub"
        if tool == "merge":
            patterns = [
                ("Audio files", "*.mp3 *.m4a *.wav *.flac *.aac *.ogg"),
                ("All files", "*.*"),
            ]
        else:
            patterns = [
                ("Subtitle files", "*.srt *.ass *.ssa *.vtt"),
                ("All files", "*.*"),
            ]
        path = filedialog.askopenfilename(title=self.T("tool_choose"), filetypes=patterns)
        if not path:
            return
        self.tool_files[key] = path
        label = self.tool_widgets.get(tool, {}).get("second_label")
        if label is not None:
            shown = path if len(path) <= 68 else "…" + path[-65:]
            label.configure(text=shown)
        status = self.tool_status_labels.get(tool)
        if status is not None:
            status.configure(text=self.T("tool_ready"), text_color=MUTED)

    def _gather_tool_options(self, tool: str) -> dict:
        """Collect current values of the controls built by ``_build_tool_options``."""
        opts: dict = {}
        for key, widget in self.tool_widgets.get(tool, {}).items():
            if key == "second_label":
                continue
            if hasattr(widget, "get"):
                opts[key] = widget.get()
        if tool in ("merge", "subtitle"):
            key = "merge:audio" if tool == "merge" else "subtitle:sub"
            opts["second"] = self.tool_files.get(key, "")
        return opts

    @staticmethod
    def _tool_number(value, default=None, minimum: float = 0.0, maximum: float = 1e9):
        try:
            number = float(value) if value not in (None, "") else default
        except (TypeError, ValueError):
            return None
        if number is None or number < minimum or number > maximum:
            return None
        return number

    def _choose_tool_file(self, tool: str) -> None:
        media_types = [
            ("Media files", "*.mp4 *.mkv *.webm *.mov *.avi *.mp3 *.m4a *.wav *.flac"),
            ("All files", "*.*"),
        ]
        path = filedialog.askopenfilename(title=self.T("tool_choose"), filetypes=media_types)
        if not path:
            return
        self.tool_files[tool] = path
        label = self.tool_file_labels.get(tool)
        if label is not None:
            shown = path if len(path) <= 68 else "…" + path[-65:]
            label.configure(text=shown)
        status = self.tool_status_labels.get(tool)
        if status is not None:
            status.configure(text=self.T("tool_ready"), text_color=MUTED)

    def _tool_output_path(self, tool: str, source: str, options: dict | None = None) -> str:
        suffix = TOOL_SUFFIXES.get(tool, "_output.mp4")
        if tool == "convert":
            fmt = str((options or {}).get("format") or "mp4")
            suffix = "_converted." + (fmt if fmt in CONVERT_FORMATS else "mp4")
        path = Path(source)
        return str(path.with_name(path.stem + suffix))

    def _tool_command(
        self, tool: str, source: str, output: str, options: dict | None = None
    ) -> list[str] | None:
        """Build the FFmpeg argv for *tool*, or None when inputs are invalid.

        Kept separate from ``_run_tool`` so command generation can be tested
        without launching a process or touching the UI.
        """
        ffmpeg = self.ffmpeg
        if not ffmpeg:
            return None
        opts = options or {}
        binary = str(ffmpeg.ffmpeg)
        base = [binary, "-y", "-i", source]

        if tool == "extract":
            return base + ["-vn", "-acodec", "libmp3lame", "-q:a", "2", output]
        if tool == "compress":
            return base + [
                "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
                "-c:a", "aac", "-b:a", "96k", output,
            ]
        if tool == "trim":
            start = self._tool_number(opts.get("start"), 0)
            duration = self._tool_number(opts.get("duration"), None, 0.01)
            if start is None or duration is None:
                return None
            return base + [
                "-ss", _fmt_number(start), "-t", _fmt_number(duration),
                "-c", "copy", output,
            ]
        if tool == "convert":
            fmt = str(opts.get("format") or "mp4")
            if fmt not in CONVERT_FORMATS:
                return None
            if fmt == "mp3":
                return base + ["-vn", "-acodec", "libmp3lame", "-q:a", "2", output]
            if fmt == "m4a":
                return base + ["-vn", "-acodec", "aac", "-b:a", "192k", output]
            if fmt == "webm":
                return base + [
                    "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0",
                    "-c:a", "libopus", "-b:a", "128k", output,
                ]
            return base + [
                "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
                "-c:a", "aac", "-b:a", "160k", output,
            ]
        if tool == "gif":
            start = self._tool_number(opts.get("start"), 0)
            duration = self._tool_number(opts.get("duration"), None, 0.1)
            fps = self._tool_number(opts.get("fps"), 12, 1, 30)
            width = self._tool_number(opts.get("width"), 480, 120, 1920)
            if any(value is None for value in (start, duration, fps, width)):
                return None
            vf = f"fps={_fmt_number(fps)},scale={int(width)}:-2"
            return [
                binary, "-y", "-ss", _fmt_number(start), "-i", source,
                "-t", _fmt_number(duration), "-vf", vf, "-loop", "0", output,
            ]
        if tool == "merge":
            second = str(opts.get("second") or "")
            if not second:
                return None
            return [
                binary, "-y", "-i", source, "-i", second,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-shortest", output,
            ]
        if tool == "subtitle":
            second = str(opts.get("second") or "")
            if not second:
                return None
            return base + [
                "-vf", "subtitles=" + _ffmpeg_filter_path(second),
                "-c:a", "copy", output,
            ]
        if tool == "cover":
            return base + ["-frames:v", "1", "-update", "1", "-q:v", "2", output]
        return None

    def _run_tool(self, tool: str) -> None:
        if getattr(self, "_tool_busy", False):
            return
        status = self.tool_status_labels.get(tool)
        source = self.tool_files.get(tool)

        def fail(key: str) -> None:
            if status is not None:
                status.configure(text=self.T(key), text_color=WARN)

        if not source:
            fail("tool_no_file")
            return
        ffmpeg = self.ffmpeg
        if not ffmpeg:
            fail("tool_no_ffmpeg")
            return
        options = self._gather_tool_options(tool)
        output = self._tool_output_path(tool, source, options)
        command = self._tool_command(tool, source, output, options)
        if command is None:
            bad_key = {
                "trim": "tool_bad_time",
                "merge": "tool_no_second",
                "subtitle": "tool_no_second",
            }.get(tool, "tool_bad_value")
            fail(bad_key)
            return

        self._tool_busy = True
        if status is not None:
            status.configure(text=self.T("tool_running"), text_color=ACCENT)

        def worker() -> None:
            ok = False
            detail = ""
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
                result = subprocess.run(
                    command, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", creationflags=flags,
                )
                ok = result.returncode == 0 and Path(output).exists()
                if not ok:
                    lines = (result.stderr or result.stdout or "").strip().splitlines()
                    detail = lines[-1] if lines else "ffmpeg error"
            except Exception as exc:
                detail = str(exc)
            if self._alive:
                # Marshal the result to the main thread via a queue; calling
                # Tkinter ``after`` from this worker is not thread-safe.
                self.tool_results.put((tool, ok, output, detail))

        threading.Thread(target=worker, daemon=True).start()

    def _tool_finished(self, tool: str, ok: bool, output: str, detail: str) -> None:
        self._tool_busy = False
        status = self.tool_status_labels.get(tool)
        if status is None:
            return
        if ok:
            status.configure(
                text=self.T("tool_done", path=Path(output).name), text_color=SUCCESS
            )
        else:
            message = detail if len(detail) <= 90 else detail[-87:]
            status.configure(
                text=self.T("tool_failed", error=message), text_color=DANGER
            )

    def _build_queue_page(self) -> None:
        page = self.page_queue
        page.grid_columnconfigure(0, weight=1)
        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for c in range(3):
            bar.grid_columnconfigure(c, weight=1)
        commands = (
            ("queue_pause_all", lambda: self._bulk_queue("pause"), SOFT_BUTTON),
            ("queue_resume_all", lambda: self._bulk_queue("resume"), SOFT_BUTTON),
            ("queue_cancel_all", lambda: self._bulk_queue("cancel"), DANGER),
        )
        for i, (key, cmd, colour) in enumerate(commands):
            ctk.CTkButton(
                bar, text=self.T(key), font=self.f_small_bold,
                fg_color=colour, hover_color=SOFT_HOVER if i < 2 else colour,
                command=cmd,
            ).grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 5, 5 if i < 2 else 0))

        host = self._card(page)
        host.grid(row=1, column=0, sticky="nsew")
        host.grid_columnconfigure(0, weight=1)
        self.queue_page_host = ctk.CTkFrame(host, fg_color="transparent")
        self.queue_page_host.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.queue_page_host.grid_columnconfigure(0, weight=1)

    def _bulk_queue(self, action: str) -> None:
        manager = getattr(self, "manager", None)
        method = getattr(manager, {"pause": "pause_all", "resume": "resume_all", "cancel": "cancel_all"}[action], None)
        if callable(method):
            try:
                method()
            except Exception:
                log.debug("Bulk queue action failed", exc_info=True)
        self._schedule_dynamic_refresh()

    def _build_completed_page(self) -> None:
        page = self.page_completed
        page.grid_columnconfigure(0, weight=1)
        host = self._card(page)
        host.grid(row=0, column=0, sticky="nsew")
        host.grid_columnconfigure(0, weight=1)
        self.completed_host = ctk.CTkFrame(host, fg_color="transparent")
        self.completed_host.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        self.completed_host.grid_columnconfigure(0, weight=1)

    def _schedule_dynamic_refresh(self) -> None:
        if getattr(self, "_dyn_job", None) is not None:
            try:
                self.after_cancel(self._dyn_job)
            except Exception:
                pass
        self._dyn_job = self.after(220, self._refresh_dynamic_pages)

    def _refresh_dynamic_pages(self) -> None:
        self._dyn_job = None
        if not getattr(self, "_alive", False):
            return
        # Only the visible page needs fresh data.  Rebuilding three pages on
        # every event (or page switch) was a major UI-thread cost.
        if getattr(self, "workspace_visible", False):
            try:
                self._refresh_workspace()
            except Exception:
                log.debug("Workspace refresh failed", exc_info=True)
        refresh = {
            0: self._refresh_home_page,
            2: self._refresh_active_page,
            3: self._refresh_queue_page,
            4: self._refresh_completed_page,
        }.get(getattr(self, "current_tab_index", 0))
        if refresh is None:
            return
        try:
            refresh()
        except Exception:
            log.debug("Dynamic page refresh failed", exc_info=True)

    def _refresh_home_page(self) -> None:
        entries = []
        try:
            entries = list(self.history.entries())
        except Exception:
            pass
        if hasattr(self, "home_kpis"):
            total_size = sum(int(e.get("size") or 0) for e in entries)
            active = sum(
                1 for c in self.task_cards.values()
                if c.snapshot.get("status") in ("pending", "scheduled", "downloading", "processing")
            )
            completed = sum(1 for e in entries if e.get("status") == "completed")
            for key, value in (
                ("total", str(len(entries))), ("active", str(active)),
                ("completed", str(completed)), ("size", format_bytes(total_size)),
            ):
                try:
                    self.home_kpis[key].configure(text=value)
                except Exception:
                    pass
        # Advanced daily / monthly statistics from the history store.
        stats: dict | None = None
        try:
            if bool(getattr(self.settings, "enable_stats", True)):
                stats = self.history.get_stats()
        except Exception:
            stats = None
        for key, prefix in (
            ("stats_today", "today"),
            ("stats_month", "month"),
            ("stats_total", "total"),
        ):
            label = getattr(self, "stats_labels", {}).get(key)
            if label is None:
                continue
            if stats:
                text = (
                    f"{self.T('stats_count', count=int(stats.get(prefix + '_count') or 0))}"
                    f"  •  {format_bytes(int(stats.get(prefix + '_bytes') or 0))}"
                )
            else:
                text = self.T("stats_empty")
            try:
                label.configure(text=text)
            except Exception:
                pass
        host = getattr(self, "home_recent_host", None)
        if host is None:
            return
        recent = list(reversed(entries))[:6]
        # Skip the teardown/rebuild when the visible data did not change.
        recent_sig = tuple(
            (
                str(e.get("id") or ""), str(e.get("timestamp") or ""),
                int(e.get("size") or 0), str(e.get("title") or ""),
                str(e.get("status") or ""),
            )
            for e in recent
        )
        if recent_sig == getattr(self, "_home_recent_sig", None):
            return
        self._home_recent_sig = recent_sig
        for child in host.winfo_children():
            child.destroy()
        if not recent:
            ctk.CTkLabel(
                host, text=self.T("home_recent_empty"), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", pady=18)
            return
        for i, entry in enumerate(recent):
            row = ctk.CTkFrame(host, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=2)
            row.grid_columnconfigure(0, weight=1)
            title = str(entry.get("title") or entry.get("filepath") or "—")
            ctk.CTkLabel(
                row, text=(title[:54] + "…") if len(title) > 55 else title,
                font=self.f_small, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", padx=6, pady=3)
            ctk.CTkLabel(
                row, text=format_bytes(int(entry.get("size") or 0)),
                font=self.f_small, text_color=MUTED,
            ).grid(row=0, column=1, padx=6, pady=3)

    def _refresh_active_page(self) -> None:
        """Live progress view for downloads currently running or paused."""
        host = getattr(self, "active_host", None)
        if host is None:
            return
        active_states = ("pending", "scheduled", "downloading", "processing", "paused")
        rows = [
            (tid, card) for tid, card in self.task_cards.items()
            if card.snapshot.get("status") in active_states
        ]
        sig = tuple(
            (tid, card.snapshot.get("status"), str(card.snapshot.get("title") or ""))
            for tid, card in rows
        )
        if sig == getattr(self, "_active_page_sig", None):
            for tid, card in rows:
                bar = getattr(self, "_active_bars", {}).get(tid)
                if bar is None:
                    continue
                try:
                    if bar.winfo_exists():
                        bar.set(float(card.snapshot.get("progress") or 0) / 100.0)
                except Exception:
                    pass
            return
        self._active_page_sig = sig
        self._active_bars = {}
        for child in host.winfo_children():
            child.destroy()
        if not rows:
            ctk.CTkLabel(
                host, text=self.T("queue_empty"), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", pady=22)
            return
        for i, (task_id, card) in enumerate(rows):
            snap = card.snapshot
            row = self._card(host)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(0, weight=1)
            title = str(snap.get("title") or "—")
            ctk.CTkLabel(
                row, text=(title[:48] + "…") if len(title) > 49 else title,
                font=self.f_small_bold, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
            speed = format_speed(float(snap.get("speed") or 0))
            ctk.CTkLabel(
                row, text=speed if speed else "—", font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=0, column=1, padx=8, pady=(8, 0))
            bar = ctk.CTkProgressBar(row, height=6, corner_radius=3, progress_color=ACCENT)
            bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
            try:
                bar.set(float(snap.get("progress") or 0) / 100.0)
            except Exception:
                bar.set(0)
            self._active_bars[task_id] = bar
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
            paused = snap.get("status") == "paused"
            self._button(
                actions, "ctx_resume" if paused else "ctx_pause",
                lambda t=task_id: self.toggle_pause(t),
                height=26, width=90, font=self.f_small,
                fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
            ).pack(side=self._start_side(), padx=self._pad(0, 5))
            self._button(
                actions, "ctx_cancel", lambda t=task_id: self.cancel_task(t),
                height=26, width=90, font=self.f_small,
                fg_color=DANGER, hover_color=DANGER,
            ).pack(side=self._start_side(), padx=self._pad(5, 0))

    def _refresh_queue_page(self) -> None:
        host = getattr(self, "queue_page_host", None)
        if host is None:
            return
        rows = [
            (tid, card) for tid, card in self.task_cards.items()
            if card.snapshot.get("status") in ("pending", "scheduled", "downloading", "processing")
        ]
        # Rebuild only when the set of tasks/statuses changes.  Progress alone
        # is updated in place on the existing bars — no widget churn.
        sig = tuple((tid, card.snapshot.get("status")) for tid, card in rows)
        if sig == getattr(self, "_queue_page_sig", None):
            for tid, card in rows:
                bar = getattr(self, "_queue_bars", {}).get(tid)
                if bar is None:
                    continue
                try:
                    if bar.winfo_exists():
                        bar.set(float(card.snapshot.get("progress") or 0) / 100.0)
                except Exception:
                    pass
            return
        self._queue_page_sig = sig
        self._queue_bars = {}
        for child in host.winfo_children():
            child.destroy()
        if not rows:
            ctk.CTkLabel(
                host, text=self.T("queue_empty"), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", pady=22)
            return
        for i, (task_id, card) in enumerate(rows):
            snap = card.snapshot
            row = self._card(host)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(0, weight=1)
            title = str(snap.get("title") or "—")
            ctk.CTkLabel(
                row, text=(title[:48] + "…") if len(title) > 49 else title,
                font=self.f_small_bold, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
            ctk.CTkLabel(
                row,
                text=self.T(
                    "queue_priority_label",
                    name=self._priority_name(int(snap.get("priority") or 0)),
                ),
                font=self.f_small, text_color=MUTED,
            ).grid(row=0, column=1, padx=8, pady=(8, 0))
            bar = ctk.CTkProgressBar(row, height=6, corner_radius=3, progress_color=ACCENT)
            bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
            try:
                bar.set(float(snap.get("progress") or 0) / 100.0)
            except Exception:
                bar.set(0)
            self._queue_bars[task_id] = bar
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))
            paused = snap.get("status") == "paused"
            ctk.CTkButton(
                actions,
                text=self.T("btn_resume") if paused else self.T("btn_pause"),
                width=86, height=26, font=self.f_small, fg_color=SOFT_BUTTON,
                hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
                command=lambda tid=task_id: self.toggle_pause(tid),
            ).pack(side="right" if is_rtl(self.settings.language) else "left", padx=3)
            ctk.CTkButton(
                actions, text=self.T("btn_cancel"), width=86, height=26,
                font=self.f_small, fg_color=DANGER, hover_color=DANGER,
                command=lambda tid=task_id: self.cancel_task(tid),
            ).pack(side="right" if is_rtl(self.settings.language) else "left", padx=3)

    def _refresh_completed_page(self) -> None:
        host = getattr(self, "completed_host", None)
        if host is None:
            return
        try:
            entries = [e for e in self.history.entries() if e.get("status") == "completed"]
        except Exception:
            entries = []
        shown = list(reversed(entries))[:30]
        sig = tuple(str(e.get("id") or e.get("filepath") or "") for e in shown)
        if sig == getattr(self, "_completed_page_sig", None):
            return
        self._completed_page_sig = sig
        for child in host.winfo_children():
            child.destroy()
        if not shown:
            ctk.CTkLabel(
                host, text=self.T("completed_empty"), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", pady=22)
            return
        for i, entry in enumerate(shown):
            row = self._card(host)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(0, weight=1)
            title = str(entry.get("title") or entry.get("filepath") or "—")
            ctk.CTkLabel(
                row, text=(title[:56] + "…") if len(title) > 57 else title,
                font=self.f_small_bold, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
            ctk.CTkLabel(
                row,
                text=f"{format_bytes(int(entry.get('size') or 0))}  •  {str(entry.get('timestamp', ''))[:10]}",
                font=self.f_small, text_color=MUTED,
            ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
            ctk.CTkButton(
                row, text=self.T("btn_open"), width=80, height=26,
                font=self.f_small, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                command=lambda e=entry: self.open_history_file(e),
            ).grid(row=0, column=1, rowspan=2, padx=10, pady=8)

    def _build_download_page(self) -> None:
        page = self.page_download
        page.grid_columnconfigure(self._grid_col(0, 2), weight=5, minsize=440)
        page.grid_columnconfigure(self._grid_col(1, 2), weight=3, minsize=280)
        page.grid_rowconfigure(3, weight=1)

        # ---- URL card -------------------------------------------------
        url_card = self._card(page)
        url_card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        url_card.grid_columnconfigure(self._grid_col(0, 3), weight=1)

        self._step_header(url_card, "1", "url_section").grid(
            row=0, column=0, columnspan=3, sticky="ew", padx=18, pady=(14, 8)
        )

        self.url_entry = ctk.CTkEntry(
            url_card,
            placeholder_text=self.T("url_placeholder"),
            height=44,
            font=self.f_body,
            corner_radius=10,
        )
        self.url_entry.grid(
            row=1, column=self._grid_col(0, 3), sticky="ew",
            padx=self._pad(18, 8), pady=(0, 16),
        )
        self.url_entry.bind("<Return>", self._on_fetch_shortcut)

        self.url_tools = ctk.CTkFrame(url_card, fg_color="transparent")
        self.url_tools.grid(
            row=1, column=self._grid_col(1, 3),
            padx=self._pad(0, 8), pady=(0, 4),
        )

        self.paste_btn = self._button(
            self.url_tools, "paste", self._paste_url,
            width=74, height=44, font=self.f_body, corner_radius=10,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.paste_btn.pack(side=self._start_side(), padx=(0, 4))
        self.paste_tip = Tooltip(self.paste_btn, self.T("paste_tip"))

        self.url_clear_btn = ctk.CTkButton(
            self.url_tools,
            text="✕",
            width=36,
            height=44,
            font=self.f_small_bold,
            corner_radius=10,
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=self._clear_url,
        )
        self.url_clear_btn.pack(side=self._start_side(), padx=(0, 4))
        self.url_clear_tip = Tooltip(self.url_clear_btn, self.T("url_clear_tip"))

        self.qr_btn = self._button(
            self.url_tools, "btn_qr", self._show_qr,
            width=50, height=44, font=self.f_small_bold, corner_radius=10,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.qr_btn.pack(side=self._start_side())

        self.inbox_btn = self._button(
            self.url_tools, "link_inbox_btn", self._open_link_inbox,
            width=104, height=44, font=self.f_small, corner_radius=10,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.inbox_btn.pack(side=self._start_side(), padx=(4, 0))
        self.inbox_tip = Tooltip(self.inbox_btn, self.T("link_inbox_tip"))

        self.fetch_btn = self._button(
            url_card, "fetch", self.fetch_media,
            width=128, height=44, font=self.f_body_bold, corner_radius=10,
        )
        self.fetch_btn.grid(
            row=1, column=self._grid_col(2, 3),
            padx=self._pad(0, 18), pady=(0, 4),
        )

        self.url_hint = ctk.CTkLabel(
            url_card,
            text=self.T("drop_hint"),
            font=self.f_small,
            text_color=MUTED,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.url_hint.grid(
            row=2, column=0, columnspan=3, sticky="ew",
            padx=18, pady=(0, 12),
        )

        # ---- Preview card ---------------------------------------------
        info_card = self._card(page)
        info_card.grid(
            row=1, column=self._grid_col(0, 2), sticky="nsew",
            pady=(0, 10), padx=self._pad(0, 10),
        )
        info_card.grid_columnconfigure(self._grid_col(1, 2), weight=1)
        self.preview_card = info_card

        self._step_header(info_card, "2", "info_section").grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(14, 8)
        )

        self.thumb_label = ctk.CTkLabel(
            info_card,
            text="🎬",
            width=THUMB_SIZE[0],
            height=THUMB_SIZE[1],
            corner_radius=12,
            fg_color=("#EEF0F3", "#24242C"),
            font=self._font(34),
        )
        self._register_shape(self.thumb_label, width=THUMB_SIZE[0], height=THUMB_SIZE[1])
        self.thumb_label.grid(
            row=1, column=self._grid_col(0, 2), rowspan=3,
            padx=self._pad(18, 14), pady=(0, 16),
        )

        self.info_title = ctk.CTkLabel(
            info_card,
            text="",
            font=self.f_h2,
            wraplength=420,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.info_title.grid(
            row=1, column=self._grid_col(1, 2), sticky="ew",
            padx=self._pad(0, 18), pady=(0, 2),
        )
        self._autowrap(self.info_title)

        self.info_meta = ctk.CTkLabel(
            info_card,
            text="",
            font=self.f_small,
            text_color=MUTED,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.info_meta.grid(
            row=2, column=self._grid_col(1, 2), sticky="ew",
            padx=self._pad(0, 18),
        )

        # Soft placeholders shown while a link is being inspected.
        self.thumb_skeleton = SkeletonBox(info_card, THUMB_SIZE[0], THUMB_SIZE[1], self)
        self.thumb_skeleton.grid(
            row=1, column=self._grid_col(0, 2), rowspan=3,
            padx=self._pad(18, 14), pady=(0, 16),
        )
        self.thumb_skeleton.grid_remove()
        self.info_skeleton = SkeletonBox(info_card, 300, 54, self)
        self.info_skeleton.grid(
            row=1, column=self._grid_col(1, 2), rowspan=2, sticky="ew",
            padx=self._pad(0, 18), pady=(0, 4),
        )
        self.info_skeleton.grid_remove()

        self.playlist_frame = ctk.CTkFrame(info_card, fg_color="transparent")
        self.playlist_frame.grid(
            row=3, column=self._grid_col(1, 2), sticky="ew",
            padx=self._pad(0, 18), pady=(8, 16),
        )
        self.playlist_frame.grid_columnconfigure(self._grid_col(0, 2), weight=1)

        self.playlist_label = ctk.CTkLabel(
            self.playlist_frame,
            text="",
            font=self.f_small_bold,
            text_color=ACCENT,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.playlist_label.grid(
            row=0, column=self._grid_col(0, 2), sticky="ew"
        )

        self.choose_btn = ctk.CTkButton(
            self.playlist_frame,
            text=self.T("choose_items"),
            width=140,
            height=30,
            corner_radius=8,
            font=self.f_small,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._open_playlist_dialog,
        )
        self.choose_btn.grid(
            row=0, column=self._grid_col(1, 2), padx=self._pad(8, 0)
        )

        # Preview opens the source page in the browser before downloading.
        self.info_actions = ctk.CTkFrame(info_card, fg_color="transparent")
        self.info_actions.grid(
            row=4, column=0, columnspan=2, sticky="ew",
            padx=18, pady=(0, 14),
        )
        self.preview_btn = ctk.CTkButton(
            self.info_actions,
            text=self.T("btn_preview"),
            width=120,
            height=30,
            corner_radius=8,
            font=self.f_small,
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=self._preview_current,
        )
        self.preview_btn.pack(side=self._start_side())
        self.info_actions.grid_remove()

        # ---- Options card ---------------------------------------------
        options_card = self._card(page)
        options_card.grid(
            row=1, column=self._grid_col(1, 2), sticky="nsew", pady=(0, 10)
        )
        options_card.grid_columnconfigure(0, weight=1)
        self.options_card = options_card

        self._step_header(options_card, "3", "options_section").grid(
            row=0, column=0, sticky="ew", padx=18, pady=(14, 8)
        )

        # Mode and quality sit side by side to keep the card compact.
        self.options_row = ctk.CTkFrame(options_card, fg_color="transparent")
        self.options_row.grid(row=1, column=0, sticky="ew", padx=14)

        self.mode_box = ctk.CTkFrame(self.options_row, fg_color="transparent")
        self._label(self.mode_box, "mode", font=self.f_small, text_color=MUTED).pack(
            anchor=self.text_anchor, fill="x"
        )
        self.mode_values = [self.T("mode_video"), self.T("mode_audio")]
        self.mode_seg = ctk.CTkSegmentedButton(
            self.mode_box,
            values=self.mode_values,
            command=self._on_mode_changed,
            height=36,
            font=self.f_body,
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
        )
        self.mode_seg.pack(fill="x", pady=(4, 0))
        self.mode_seg.set(self.mode_values[0])

        self.quality_box = ctk.CTkFrame(self.options_row, fg_color="transparent")
        self._label(self.quality_box, "quality", font=self.f_small, text_color=MUTED).pack(
            anchor=self.text_anchor, fill="x"
        )
        self.quality_menu = ctk.CTkOptionMenu(
            self.quality_box,
            values=[self.T("quality_best")],
            command=self._on_quality_changed,
            height=36,
            font=self.f_body,
            corner_radius=10,
            dynamic_resizing=False,
            fg_color=ACCENT,
            button_color=ACCENT_HOVER,
            button_hover_color=ACCENT_HOVER,
        )
        self.quality_menu.pack(fill="x", pady=(4, 0))

        # Per-download bandwidth cap and group assignment.
        self.bw_box = ctk.CTkFrame(self.options_row, fg_color="transparent")
        self._label(self.bw_box, "bw_menu", font=self.f_small, text_color=MUTED).pack(
            anchor=self.text_anchor, fill="x"
        )
        self.bw_values = [0, -1] + [v for v in SPEED_LIMITS_KBPS if v]
        self.bw_options = (
            [self.T("bw_auto"), self.T("bw_unlimited")]
            + [self.T("bw_set", speed=v) for v in self.bw_values[2:]]
        )
        self.speed_menu = ctk.CTkOptionMenu(
            self.bw_box, values=self.bw_options, height=36,
            font=self.f_small, corner_radius=10, dynamic_resizing=False,
        )
        self.speed_menu.set(self.bw_options[0])
        self.speed_menu.pack(fill="x", pady=(4, 0))

        self.group_box = ctk.CTkFrame(self.options_row, fg_color="transparent")
        self._label(self.group_box, "groups_assign", font=self.f_small, text_color=MUTED).pack(
            anchor=self.text_anchor, fill="x"
        )
        self.group_options, self.group_lookup = self._group_choices()
        self.group_menu = ctk.CTkOptionMenu(
            self.group_box, values=self.group_options, height=36,
            font=self.f_small, corner_radius=10, dynamic_resizing=False,
        )
        self.group_menu.set(self.group_options[0])
        self.group_menu.pack(fill="x", pady=(4, 0))

        self._layout_options_rows()

        # Destination folder: entry and browse button share one row.
        self._label(options_card, "dest_section", font=self.f_small, text_color=MUTED).grid(
            row=2, column=0, sticky="ew", padx=18, pady=(10, 0)
        )
        self.dest_var = tk.StringVar(value=self.settings.download_dir)
        self.dest_row = ctk.CTkFrame(options_card, fg_color="transparent")
        self.dest_row.grid(row=3, column=0, sticky="ew", padx=18, pady=(4, 10))

        self.dest_entry = ctk.CTkEntry(
            self.dest_row,
            textvariable=self.dest_var,
            height=36,
            font=self.f_small,
            corner_radius=10,
            state="readonly",
        )

        self.browse_btn = self._button(
            self.dest_row, "browse", self._choose_download_dir,
            width=92, height=36, font=self.f_small, corner_radius=10,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self._layout_dest_row()

        # Schedule: start immediately or defer the whole request.
        self.schedule_row = ctk.CTkFrame(options_card, fg_color="transparent")
        self.schedule_row.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 8))
        self._label(
            self.schedule_row, "settings_schedule",
            font=self.f_small, text_color=MUTED,
        ).pack(anchor=self.text_anchor, fill="x")
        self.schedule_options = (0, 15, 30, 60, 120)
        self.schedule_values = [
            self.T("schedule_now"),
            self.T("schedule_15"),
            self.T("schedule_30"),
            self.T("schedule_60"),
            self.T("schedule_120"),
        ]
        self.schedule_menu = ctk.CTkOptionMenu(
            self.schedule_row,
            values=self.schedule_values,
            command=self._on_schedule_changed,
            height=34,
            font=self.f_small,
            corner_radius=10,
            dynamic_resizing=False,
            fg_color=ACCENT,
            button_color=ACCENT_HOVER,
            button_hover_color=ACCENT_HOVER,
        )
        try:
            self.schedule_menu.set(
                self.schedule_values[self.schedule_options.index(self.settings.schedule_minutes)]
            )
        except ValueError:
            self.schedule_menu.set(self.schedule_values[0])
        self.schedule_menu.pack(fill="x", pady=(4, 0))

        # Priority: higher values are dequeued first by the manager.
        self.priority_row = ctk.CTkFrame(options_card, fg_color="transparent")
        self.priority_row.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 8))
        self._label(
            self.priority_row, "queue_priority",
            font=self.f_small, text_color=MUTED,
        ).pack(anchor=self.text_anchor, fill="x")
        self.priority_values = (-1, 0, 1)
        self.priority_labels = [
            self.T("queue_priority_low"),
            self.T("queue_priority_normal"),
            self.T("queue_priority_high"),
        ]
        self.priority_menu = ctk.CTkOptionMenu(
            self.priority_row,
            values=self.priority_labels,
            height=34,
            font=self.f_small,
            corner_radius=10,
            dynamic_resizing=False,
            fg_color=ACCENT,
            button_color=ACCENT_HOVER,
            button_hover_color=ACCENT_HOVER,
        )
        self.priority_menu.set(self.priority_labels[1])
        self.priority_menu.pack(fill="x", pady=(4, 0))

        self.ffmpeg_warning = ctk.CTkLabel(
            options_card,
            text=self.T("ffmpeg_missing_short"),
            font=self.f_small,
            text_color=WARN,
            anchor=self.text_anchor,
        )
        self.ffmpeg_warning.grid(row=6, column=0, sticky="ew", padx=18, pady=(8, 14))
        if self.ffmpeg:
            self.ffmpeg_warning.grid_remove()

        # ---- Sticky action bar ----------------------------------------
        action_bar = ctk.CTkFrame(
            page,
            fg_color=CARD,
            corner_radius=16,
            border_width=1,
            border_color=CARD_BORDER,
        )
        action_bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        info_col = self._grid_col(0, 2)
        button_col = self._grid_col(1, 2)
        action_bar.grid_columnconfigure(info_col, weight=1)
        self.action_bar = action_bar

        self.action_status_label = ctk.CTkLabel(
            action_bar,
            text=self.T("download_status_idle"),
            font=self.f_small,
            text_color=MUTED,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.action_status_label.grid(
            row=0, column=info_col, sticky="ew",
            padx=self._pad(18, 12), pady=(12, 2),
        )

        self.action_progress = ctk.CTkProgressBar(
            action_bar, height=9, corner_radius=4, progress_color=ACCENT
        )
        self.action_progress.grid(
            row=1, column=info_col, sticky="ew",
            padx=self._pad(18, 12), pady=(0, 12),
        )
        self.action_progress.set(0)

        self.download_btn = ctk.CTkButton(
            action_bar,
            text=self.T("download"),
            width=210,
            height=46,
            corner_radius=12,
            font=self.f_body_bold,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._start_download,
        )
        self.download_btn.grid(
            row=0, column=button_col, rowspan=2, sticky=self._end_sticky,
            padx=self._pad(12, 18), pady=10,
        )

        # ---- Queue card -----------------------------------------------
        queue_card = self._card(page)
        queue_card.grid(row=3, column=0, columnspan=2, sticky="nsew")
        queue_card.grid_columnconfigure(0, weight=1)
        queue_card.grid_rowconfigure(1, weight=1)

        queue_head = ctk.CTkFrame(queue_card, fg_color="transparent")
        queue_head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 8))
        queue_head.grid_columnconfigure(self._grid_col(1, 3), weight=1)

        self._label(queue_head, "queue_section", font=self.f_h2).grid(
            row=0, column=self._grid_col(0, 3), sticky=self._start_sticky
        )
        self.queue_count = ctk.CTkLabel(
            queue_head, text="0", font=self.f_small, text_color=MUTED,
            anchor=self.text_anchor, justify=self.text_justify,
        )
        self.queue_count.grid(
            row=0, column=self._grid_col(1, 3), sticky=self._start_sticky,
            padx=self._pad(8, 0),
        )
        self.clear_finished_btn = self._button(
            queue_head, "clear_finished", self._clear_finished_tasks,
            width=132, height=28, font=self.f_small, corner_radius=8,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.clear_finished_btn.grid(
            row=0, column=self._grid_col(2, 3), sticky=self._end_sticky
        )

        self.queue_scroll = ctk.CTkScrollableFrame(
            queue_card, fg_color="transparent", corner_radius=0
        )
        self.queue_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.queue_scroll.grid_columnconfigure(0, weight=1)

        self.queue_empty = self._label(
            self.queue_scroll,
            "queue_empty",
            font=self.f_small,
            text_color=MUTED,
        )
        self.queue_empty.grid(row=0, column=0, sticky="ew", padx=12, pady=34)

    # ------------------------------------------------------------------
    # History tab
    # ------------------------------------------------------------------
    def _build_history_page(self) -> None:
        page = self.page_history
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)

        # ---- KPI cards -------------------------------------------------
        kpis = ctk.CTkFrame(page, fg_color="transparent")
        kpis.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for index in range(5):
            kpis.grid_columnconfigure(self._grid_col(index, 5), weight=1, uniform="kpi")

        kpi_specs = (
            ("history_kpi_files", "stat_count_value"),
            ("history_kpi_size", "stat_size_value"),
            ("history_kpi_last", "stat_last_value"),
            ("history_kpi_active", "stat_active_value"),
            ("history_kpi_speed", "stat_speed_value"),
        )
        for logical, (title_key, attr) in enumerate(kpi_specs):
            card, value = self._kpi_card(kpis, title_key)
            card.grid(
                row=0, column=self._grid_col(logical, 5), sticky="nsew",
                padx=4,
            )
            setattr(self, attr, value)
            self._static_bindings.append((value, "stat_empty"))

        # ---- Search + actions -----------------------------------------
        toolbar = ctk.CTkFrame(page, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        toolbar.grid_columnconfigure(self._grid_col(0, 4), weight=1)

        search_holder = ctk.CTkFrame(toolbar, fg_color="transparent")
        search_holder.grid(
            row=0, column=self._grid_col(0, 4), sticky="ew",
            padx=self._pad(0, 8),
        )

        self.search_icon = ctk.CTkLabel(
            search_holder,
            text="⌕",
            width=26,
            font=self._font(17, family="Segoe UI Symbol"),
            text_color=MUTED,
        )
        self.search_icon.pack(side=self._start_side(), padx=(4, 0))

        self.history_search_var = tk.StringVar(value=self.history_query)
        self.history_search_entry = ctk.CTkEntry(
            search_holder,
            textvariable=self.history_search_var,
            placeholder_text=self.T("history_search_placeholder"),
            height=36,
            font=self.f_small,
            corner_radius=10,
        )
        self.history_search_entry.pack(
            side=self._start_side(), fill="x", expand=True, padx=4
        )
        self.history_search_entry.bind("<KeyRelease>", self._on_history_search_changed)
        self.history_search_entry.bind("<Escape>", lambda _e: self._clear_history_search())
        self.search_tip = Tooltip(self.search_icon, self.T("search_tip"))

        self.search_clear_btn = ctk.CTkButton(
            search_holder,
            text="✕",
            width=30,
            height=30,
            font=self.f_small_bold,
            corner_radius=8,
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=self._clear_history_search,
        )
        self.search_clear_btn.pack(side=self._start_side(), padx=(0, 2))
        self.search_clear_tip = Tooltip(self.search_clear_btn, self.T("search_clear_tip"))

        view_holder = ctk.CTkFrame(toolbar, fg_color="transparent")
        view_holder.grid(row=0, column=self._grid_col(1, 4), padx=self._pad(4, 4))
        self.grid_view_btn = ctk.CTkButton(
            view_holder,
            text="▦",
            width=36,
            height=36,
            font=self.f_body,
            corner_radius=10,
            command=lambda: self._set_library_view("grid"),
        )
        self.grid_view_btn.pack(side=self._start_side(), padx=(0, 3))
        self.list_view_btn = ctk.CTkButton(
            view_holder,
            text="☰",
            width=36,
            height=36,
            font=self.f_body,
            corner_radius=10,
            command=lambda: self._set_library_view("list"),
        )
        self.list_view_btn.pack(side=self._start_side())
        self.view_tip = Tooltip(view_holder, self.T("library_view_tip"))

        self.sort_btn = ctk.CTkButton(
            view_holder,
            text=self.T("library_sort"),
            width=64,
            height=36,
            font=self.f_small,
            corner_radius=10,
            fg_color=SOFT_BUTTON,
            hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=self._show_sort_menu,
        )
        self.sort_btn.pack(side=self._start_side(), padx=(6, 0))
        self.sort_tip = Tooltip(self.sort_btn, self.T("library_sort_tip"))

        self._button(
            view_holder, "dup_open", self._open_duplicates,
            width=112, height=36, font=self.f_small, corner_radius=10,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        ).pack(side=self._start_side(), padx=(6, 0))

        self.open_downloads_btn = self._button(
            toolbar, "btn_open_downloads", self._open_download_dir,
            width=148, height=36, font=self.f_small, corner_radius=10,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.open_downloads_btn.grid(
            row=0, column=self._grid_col(2, 4), padx=self._pad(4, 4)
        )

        self.clear_history_btn = self._button(
            toolbar, "history_clear", self._clear_history,
            width=118, height=36, font=self.f_small, corner_radius=10,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.clear_history_btn.grid(
            row=0, column=self._grid_col(3, 4), padx=self._pad(4, 0)
        )

        # ---- Filter chips ---------------------------------------------
        chip_row = ctk.CTkFrame(page, fg_color="transparent")
        chip_row.grid(row=2, column=0, sticky="ew", pady=(0, 6))

        self.history_filter_values = ["all", "video", "audio", "image", "other"]
        self.history_filter_labels = [
            self.T(f"history_filter_{key}") for key in self.history_filter_values
        ]
        self.history_chip_buttons: dict[str, ctk.CTkButton] = {}
        for kind, label in zip(self.history_filter_values, self.history_filter_labels):
            chip = ctk.CTkButton(
                chip_row,
                text=label,
                height=30,
                width=78,
                corner_radius=15,
                font=self.f_small,
                command=lambda k=kind: self._on_history_chip(k),
            )
            chip.pack(side=self._start_side(), padx=(0, 6) if not is_rtl(self.settings.language) else (6, 0))
            self.history_chip_buttons[kind] = chip

        self.favorite_chip = ctk.CTkButton(
            chip_row,
            text="★ " + self.T("history_filter_favorite"),
            height=30,
            width=88,
            corner_radius=15,
            font=self.f_small,
            command=self._on_favorite_chip,
        )
        self.favorite_chip.pack(
            side=self._start_side(),
            padx=(0, 6) if not is_rtl(self.settings.language) else (6, 0),
        )

        self.history_shown_label = ctk.CTkLabel(
            chip_row,
            text="",
            font=self.f_small,
            text_color=MUTED,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.history_shown_label.pack(side=self._end_side(), padx=(8, 0) if not is_rtl(self.settings.language) else (0, 8))

        # ---- Library content ------------------------------------------
        self.history_scroll = ctk.CTkScrollableFrame(
            page, fg_color="transparent", corner_radius=0
        )
        self.history_scroll.grid(row=3, column=0, sticky="nsew")
        self.history_scroll.grid_columnconfigure(0, weight=1)

        # Column count is recalculated by the root resize pass.  Binding an
        # inner <Configure> here used to re-grid the cards and immediately fire
        # another Configure, creating an infinite event loop.

        self.history_empty = ctk.CTkFrame(self.history_scroll, fg_color="transparent")
        self.history_empty.grid(row=0, column=0, sticky="ew", pady=30)
        self.history_empty_icon = ctk.CTkLabel(
            self.history_empty,
            text="🗂",
            font=self._font(52, family="Segoe UI Symbol"),
            text_color=MUTED,
        )
        self.history_empty_icon.pack(pady=(10, 6))
        self.history_empty_title = ctk.CTkLabel(
            self.history_empty,
            text=self.T("history_empty_title"),
            font=self.f_h2,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.history_empty_title.pack(fill="x", padx=20)
        self.history_empty_hint = ctk.CTkLabel(
            self.history_empty,
            text=self.T("history_empty_hint"),
            font=self.f_small,
            text_color=MUTED,
            wraplength=460,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.history_empty_hint.pack(fill="x", padx=20, pady=(6, 12))
        self.history_empty_action = ctk.CTkButton(
            self.history_empty,
            text=self.T("history_empty_action"),
            height=36,
            width=190,
            corner_radius=10,
            font=self.f_body,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._empty_state_action,
        )
        self.history_empty_action.pack(pady=(0, 12))

        self.history_content = ctk.CTkFrame(
            self.history_scroll, fg_color="transparent"
        )
        self.history_content.grid(row=1, column=0, sticky="ew")
        self.history_content.grid_columnconfigure(0, weight=1)

        # No <Configure> reflow here: cards are packed with fill="x" and Tk
        # already reflows them on resize.  Rebuilding them on every drag was
        # the single biggest source of resize stutter.
        self._style_history_chips()
        self._style_view_buttons()

    # ------------------------------------------------------------------
    def _kpi_card(self, parent, title_key: str) -> tuple[ctk.CTkFrame, ctk.CTkLabel]:
        card = self._card(parent)
        card.grid_columnconfigure(0, weight=1)
        self._label(
            card, title_key, font=self.f_small, text_color=MUTED
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        value = ctk.CTkLabel(
            card,
            text="—",
            font=self.f_h2,
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        value.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        return card, value

    # ------------------------------------------------------------------
    # Settings tab
    # ------------------------------------------------------------------
    def _build_settings_page(self) -> None:
        page = self.page_settings
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.grid_columnconfigure(0, weight=1)
        self._label(header, "settings_section", font=self.f_h2).grid(
            row=0, column=0, sticky=self._start_sticky
        )
        self.saved_badge = ctk.CTkLabel(
            header,
            text=self.T("settings_saved_badge"),
            font=self.f_small_bold,
            text_color=SUCCESS,
            fg_color=ACCENT_SOFT,
            corner_radius=9,
            height=24,
            padx=10,
        )
        self.saved_badge.grid(row=0, column=1, sticky=self._end_sticky)
        self.saved_badge.grid_remove()

        self.settings_tabs = ctk.CTkTabview(
            page,
            fg_color="transparent",
            corner_radius=14,
            segmented_button_fg_color=SOFT_BUTTON,
            segmented_button_unselected_color=SOFT_BUTTON,
            segmented_button_unselected_hover_color=SOFT_HOVER,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            text_color=SOFT_TEXT,
        )
        self.settings_tabs.grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        general = self.settings_tabs.add(self.T("settings_tab_general"))
        format_tab = self.settings_tabs.add(self.T("settings_tab_format"))
        network = self.settings_tabs.add(self.T("settings_tab_network"))
        updates = self.settings_tabs.add(self.T("settings_tab_updates"))
        pro = self.settings_tabs.add(self.T("settings_tab_pro"))
        rules_tab = self.settings_tabs.add(self.T("settings_tab_rules"))
        for tab in (general, format_tab, network, updates, pro, rules_tab):
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_columnconfigure(1, weight=0)

        # ==================================================================
        # General
        # ==================================================================
        self.general_card = general
        self._label(
            general, "settings_download_dir", font=self.f_small, text_color=MUTED
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(14, 0))
        self.settings_dir_entry = ctk.CTkEntry(
            general, textvariable=self.dest_var, height=34, font=self.f_small,
            corner_radius=10, state="readonly",
        )
        self.settings_dir_entry.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(4, 6)
        )
        self.settings_dir_btn = self._button(
            general, "browse", self._choose_download_dir,
            height=32, font=self.f_small, corner_radius=8,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.settings_dir_btn.grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 8)
        )

        self._pair_label(general, 3, "settings_concurrency")
        self.concurrency_menu = ctk.CTkOptionMenu(
            general,
            values=["1", "2", "3", "4"],
            command=self._on_concurrency_changed,
            width=110,
            height=32,
            font=self.f_small,
            corner_radius=8,
            dynamic_resizing=False,
            fg_color=ACCENT,
            button_color=ACCENT_HOVER,
            button_hover_color=ACCENT_HOVER,
        )
        self.concurrency_menu.set(str(self.settings.max_concurrent))
        self.concurrency_menu.grid(
            row=3, column=self._grid_col(1, 2), sticky=self._end_sticky,
            padx=self._pad(0, 18), pady=5,
        )

        self._pair_label(general, 4, "settings_theme")
        self.theme_values = [
            self.T("theme_dark"), self.T("theme_light"), self.T("theme_system")
        ]
        self.theme_seg = ctk.CTkSegmentedButton(
            general,
            values=self.theme_values,
            command=self._on_theme_seg_changed,
            height=32,
            font=self.f_small,
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
        )
        try:
            self.theme_seg.set(self.theme_values[["dark", "light", "system"].index(self.settings.theme)])
        except ValueError:
            self.theme_seg.set(self.theme_values[0])
        self.theme_seg.grid(
            row=4, column=self._grid_col(1, 2), sticky=self._end_sticky,
            padx=self._pad(0, 18), pady=5,
        )
        self._hint_label(general, 5, "settings_theme_hint")

        self._pair_label(general, 6, "settings_language")
        self.lang_values = ["العربية", "English"]
        self.lang_seg = ctk.CTkSegmentedButton(
            general,
            values=self.lang_values,
            command=self._on_lang_seg_changed,
            height=32,
            font=self.f_small,
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
        )
        self.lang_seg.set(self.lang_values[0 if self.settings.language == "ar" else 1])
        self.lang_seg.grid(
            row=6, column=self._grid_col(1, 2), sticky=self._end_sticky,
            padx=self._pad(0, 18), pady=5,
        )

        self._pair_label(general, 7, "settings_audio_bitrate")
        self.bitrate_menu = ctk.CTkOptionMenu(
            general,
            values=["320 kbps", "256 kbps", "192 kbps", "128 kbps"],
            command=self._on_bitrate_changed,
            width=130,
            height=32,
            font=self.f_small,
            corner_radius=8,
            dynamic_resizing=False,
            fg_color=ACCENT,
            button_color=ACCENT_HOVER,
            button_hover_color=ACCENT_HOVER,
        )
        self.bitrate_menu.set(f"{self.settings.audio_quality} kbps")
        self.bitrate_menu.grid(
            row=7, column=self._grid_col(1, 2), sticky=self._end_sticky,
            padx=self._pad(0, 18), pady=5,
        )

        # ---- Palette ---------------------------------------------------
        self._label(general, "settings_palette", font=self.f_h2).grid(
            row=8, column=0, columnspan=2, sticky="ew", padx=18, pady=(12, 2)
        )
        self.palette_card = general
        self.palette_hint = self._label(
            general, "settings_palette_hint", font=self.f_small,
            text_color=MUTED,
        )
        self.palette_hint.grid(
            row=9, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 8)
        )
        self._autowrap(self.palette_hint, padding=40)

        controls = ctk.CTkFrame(general, fg_color="transparent")
        controls.grid(row=10, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 10))
        self.palette_values = [self.T(f"palette_{key}") for key in PALETTE_KEYS]
        self.palette_menu = ctk.CTkOptionMenu(
            controls,
            values=self.palette_values,
            command=self._on_palette_changed,
            width=190,
            height=34,
            font=self.f_small,
            corner_radius=8,
            dynamic_resizing=False,
            fg_color=ACCENT,
            button_color=ACCENT_HOVER,
            button_hover_color=ACCENT_HOVER,
        )
        self.palette_menu.set(
            self.palette_values[PALETTE_KEYS.index(self.settings.palette)]
        )
        chips = ctk.CTkFrame(controls, fg_color="transparent")
        self.palette_chips = []
        for colour in preview_colours(self.settings.palette):
            chip = ctk.CTkFrame(
                chips, width=36, height=24, corner_radius=6,
                fg_color=colour, border_width=1,
                border_color=CARD_BORDER,
            )
            chip.pack(side=self._start_side(), padx=3)
            self.palette_chips.append(chip)
        if is_rtl(self.settings.language):
            self.palette_menu.pack(side="right", padx=(14, 0))
            chips.pack(side="right")
        else:
            self.palette_menu.pack(side="left")
            chips.pack(side="left", padx=(14, 0))

        # ---- Embedding / accessibility --------------------------------
        self.embed_meta_switch = self._settings_switch_row(
            general, 11, "settings_embed_meta", self.settings.embed_metadata,
            self._on_switches_changed, pady=(8, 4),
        )
        self.embed_thumb_switch = self._settings_switch_row(
            general, 12, "settings_embed_thumb", self.settings.embed_thumbnail,
            self._on_switches_changed, pady=(0, 8),
        )

        self._pair_label(general, 13, "settings_ui_scale")
        self.ui_scale_values = [self.T("ui_scale_normal"), self.T("ui_scale_large")]
        self.ui_scale_seg = ctk.CTkSegmentedButton(
            general,
            values=self.ui_scale_values,
            command=self._on_ui_scale_changed,
            height=32,
            font=self.f_small,
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
        )
        self.ui_scale_seg.set(
            self.ui_scale_values[0 if self.settings.ui_scale == "normal" else 1]
        )
        self.ui_scale_seg.grid(
            row=13, column=self._grid_col(1, 2), sticky=self._end_sticky,
            padx=self._pad(0, 18), pady=5,
        )
        self._hint_label(general, 14, "settings_ui_scale_hint")

        self.reduce_switch = self._settings_switch_row(
            general, 15, "settings_reduce_motion", self.settings.reduce_motion,
            self._on_reduce_motion_changed, pady=(8, 2),
        )
        self._hint_label(general, 16, "settings_reduce_motion_hint")

        # ---- Runtime status -------------------------------------------
        self._label(general, "settings_ffmpeg", font=self.f_h2).grid(
            row=17, column=0, columnspan=2, sticky="ew", padx=18, pady=(14, 2)
        )
        status_key = "settings_ffmpeg_ok" if self.ffmpeg else "settings_ffmpeg_missing"
        self.ffmpeg_status = ctk.CTkLabel(
            general,
            text=self.T(status_key),
            font=self.f_small_bold,
            text_color=SUCCESS if self.ffmpeg else WARN,
            anchor=self.text_anchor,
            justify=self.text_justify,
            wraplength=430,
        )
        self.ffmpeg_status.grid(row=18, column=0, columnspan=2, sticky="ew", padx=18)
        self._static_bindings.append((self.ffmpeg_status, status_key))
        if self.ffmpeg:
            self.ffmpeg_path = ctk.CTkLabel(
                general,
                text=str(self.ffmpeg.ffmpeg),
                font=self.f_small,
                text_color=MUTED,
                anchor=self.text_anchor,
                justify=self.text_justify,
                wraplength=430,
            )
            self.ffmpeg_path.grid(row=19, column=0, columnspan=2, sticky="ew", padx=18, pady=(2, 0))
        else:
            self._label(
                general, "settings_ffmpeg_hint", font=self.f_small,
                text_color=MUTED, wraplength=430,
            ).grid(row=19, column=0, columnspan=2, sticky="ew", padx=18, pady=(2, 0))
        self.config_btn = self._button(
            general, "settings_config_folder", self._open_config_folder,
            height=30, font=self.f_small, corner_radius=8,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.config_btn.grid(row=20, column=0, columnspan=2, sticky="ew", padx=18, pady=(10, 8))

        self._label(general, "settings_js_runtime", font=self.f_h2).grid(
            row=21, column=0, columnspan=2, sticky="ew", padx=18, pady=(6, 2)
        )
        js_status_key = "settings_js_ok" if self.js_runtimes else "settings_js_missing"
        self.js_status = ctk.CTkLabel(
            general,
            text=self.T(js_status_key),
            font=self.f_small_bold,
            text_color=SUCCESS if self.js_runtimes else WARN,
            anchor=self.text_anchor,
            justify=self.text_justify,
            wraplength=430,
        )
        self.js_status.grid(row=22, column=0, columnspan=2, sticky="ew", padx=18)
        self._static_bindings.append((self.js_status, js_status_key))
        if self.js_runtimes:
            name, runtime = next(iter(self.js_runtimes.items()))
            ctk.CTkLabel(
                general,
                text=f"{name}: {runtime.get('path', '')}",
                font=self.f_small,
                text_color=MUTED,
                anchor=self.text_anchor,
                justify=self.text_justify,
                wraplength=430,
            ).grid(row=23, column=0, columnspan=2, sticky="ew", padx=18, pady=(2, 16))
        else:
            self._label(
                general, "settings_js_hint", font=self.f_small,
                text_color=MUTED, wraplength=430,
            ).grid(row=23, column=0, columnspan=2, sticky="ew", padx=18, pady=(2, 16))

        # ==================================================================
        # Format
        # ==================================================================
        self._pair_label(format_tab, 0, "settings_container")
        self.container_values = ["mp4", "mkv", "webm"]
        self.container_menu = ctk.CTkOptionMenu(
            format_tab,
            values=[value.upper() for value in self.container_values],
            command=self._on_container_changed,
            width=120,
            height=32,
            font=self.f_small,
            corner_radius=8,
            dynamic_resizing=False,
            fg_color=ACCENT,
            button_color=ACCENT_HOVER,
            button_hover_color=ACCENT_HOVER,
        )
        self.container_menu.set(self.settings.video_container.upper())
        self.container_menu.grid(
            row=0, column=self._grid_col(1, 2), sticky=self._end_sticky,
            padx=self._pad(0, 18), pady=(16, 5),
        )
        self._hint_label(format_tab, 1, "settings_container_hint")

        self.subtitle_switch = self._settings_switch_row(
            format_tab, 2, "settings_subtitles", self.settings.embed_subtitles,
            self._on_subtitle_switch_changed, pady=(10, 4),
        )
        if not self.ffmpeg:
            self.subtitle_switch.configure(state="disabled", text_color=MUTED)
            self._label(
                format_tab, "settings_ffmpeg_required_for_sub",
                font=self.f_small, text_color=WARN, wraplength=430,
            ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 4))

        self._label(
            format_tab, "settings_subtitle_langs", font=self.f_small, text_color=MUTED
        ).grid(row=4, column=0, columnspan=2, sticky="ew", padx=18, pady=(8, 0))
        self.subtitle_var = tk.StringVar(value=self.settings.subtitle_langs)
        self.subtitle_entry = ctk.CTkEntry(
            format_tab,
            textvariable=self.subtitle_var,
            height=34,
            font=self.f_small,
            corner_radius=10,
            placeholder_text="ar,en",
        )
        self.subtitle_entry.grid(
            row=5, column=0, columnspan=2, sticky="ew", padx=18, pady=(4, 2)
        )
        self.subtitle_entry.bind("<FocusOut>", self._on_network_entries_changed)
        self.subtitle_entry.bind("<Return>", self._on_network_entries_changed)
        self._hint_label(format_tab, 6, "settings_subtitle_langs_hint")

        self.clipboard_switch = self._settings_switch_row(
            format_tab, 7, "settings_auto_clipboard", self.settings.auto_clipboard,
            self._on_auto_clipboard_changed, pady=(10, 2),
        )
        self._hint_label(format_tab, 8, "settings_auto_clipboard_hint")

        # ==================================================================
        # Network
        # ==================================================================
        self.advanced_card = network
        self._label(
            network, "settings_proxy", font=self.f_small, text_color=MUTED
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 0))
        self.proxy_var = tk.StringVar(value=self.settings.proxy)
        self.proxy_entry = ctk.CTkEntry(
            network,
            textvariable=self.proxy_var,
            height=34,
            font=self.f_small,
            corner_radius=10,
            placeholder_text="http://127.0.0.1:8080",
        )
        self.proxy_entry.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(4, 2)
        )
        self.proxy_entry.bind("<FocusOut>", self._on_network_entries_changed)
        self.proxy_entry.bind("<Return>", self._on_network_entries_changed)
        self._hint_label(network, 2, "settings_proxy_hint")

        self._pair_label(network, 3, "settings_speed_limit", pady=(14, 5))
        self.speed_values = [0, 256, 512, 1024, 2048, 4096, 8192]
        self.speed_labels = [self.T("speed_unlimited")] + [
            self.T("speed_limit_option", value=value)
            for value in self.speed_values[1:]
        ]
        self.speed_menu = ctk.CTkOptionMenu(
            network,
            values=self.speed_labels,
            command=self._on_speed_limit_changed,
            width=170,
            height=32,
            font=self.f_small,
            corner_radius=8,
            dynamic_resizing=False,
            fg_color=ACCENT,
            button_color=ACCENT_HOVER,
            button_hover_color=ACCENT_HOVER,
        )
        try:
            self.speed_menu.set(
                self.speed_labels[self.speed_values.index(self.settings.speed_limit_kbps)]
            )
        except ValueError:
            self.speed_menu.set(self.speed_labels[0])
        self.speed_menu.grid(
            row=3, column=self._grid_col(1, 2), sticky=self._end_sticky,
            padx=self._pad(0, 18), pady=(14, 5),
        )
        self._hint_label(network, 4, "settings_container_hint")

        self._label(network, "settings_network", font=self.f_h2).grid(
            row=5, column=0, columnspan=2, sticky="ew", padx=18, pady=(18, 2)
        )
        self._hint_label(network, 6, "settings_proxy_hint")

        # ==================================================================
        # Updates
        # ==================================================================
        self.updates_card = updates
        self._label(
            updates, "settings_update_url", font=self.f_small, text_color=MUTED
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 0))
        self.update_url_var = tk.StringVar(value=self.settings.update_url)
        self.update_url_entry = ctk.CTkEntry(
            updates,
            textvariable=self.update_url_var,
            height=34,
            font=self.f_small,
            corner_radius=10,
            placeholder_text="https://example.com/version.json",
        )
        self.update_url_entry.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=18, pady=(4, 2)
        )
        self.update_url_entry.bind("<FocusOut>", self._on_network_entries_changed)
        self.update_url_entry.bind("<Return>", self._on_network_entries_changed)
        self._hint_label(updates, 2, "settings_update_url_hint")

        self.check_updates_btn = self._button(
            updates, "btn_check_updates", self._check_updates,
            height=34, font=self.f_small, corner_radius=8,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.check_updates_btn.grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(8, 4)
        )
        self.version_label = ctk.CTkLabel(
            updates,
            text=f"v{APP_VERSION}",
            font=self.f_small,
            text_color=MUTED,
            anchor=self.text_anchor,
        )
        self.version_label.grid(row=4, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 8))

        self._label(updates, "settings_about", font=self.f_h2).grid(
            row=5, column=0, columnspan=2, sticky="ew", padx=18, pady=(12, 2)
        )
        self.about_text = self._label(
            updates, "settings_about_text", font=self.f_small,
            text_color=MUTED, wraplength=430,
        )
        self.about_text.grid(row=6, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 6))
        self._label(
            updates, "settings_shortcuts", font=self.f_small,
            text_color=MUTED, wraplength=430,
        ).grid(row=7, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 8))

        self.about_open_btn = self._button(
            updates, "about_title", self._open_about,
            height=34, font=self.f_small, corner_radius=8,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        )
        self.about_open_btn.grid(
            row=8, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 16)
        )

        # ==================================================================
        # Pro features
        # ==================================================================
        self.pro_switches: dict[str, ctk.CTkSwitch] = {}
        pro_rows = (
            ("smart_naming", "settings_smart_naming", "settings_smart_naming_hint"),
            ("show_task_thumbnails", "settings_show_thumbnails", "settings_show_thumbnails_hint"),
            ("enable_stats", "settings_enable_stats", "settings_enable_stats_hint"),
            ("auto_fetch_clipboard", "settings_auto_fetch_clipboard", "settings_auto_fetch_clipboard_hint"),
            ("auto_retry_failed", "settings_auto_retry_failed", "settings_auto_retry_failed_hint"),
            ("verify_hashes", "settings_verify_hashes", "settings_verify_hashes_hint"),
            ("auto_shutdown", "settings_auto_shutdown", "settings_auto_shutdown_hint"),
        )
        for i, (attr, label_key, hint_key) in enumerate(pro_rows):
            row = i * 2
            self.pro_switches[attr] = self._settings_switch_row(
                pro, row, label_key,
                bool(getattr(self.settings, attr, False)),
                self._on_pro_switches_changed,
                pady=(10 if i == 0 else 2, 0),
            )
            self._hint_label(pro, row + 1, hint_key)

        pro_tools_row = len(pro_rows) * 2
        self._label(pro, "workspace_quick", font=self.f_h2).grid(
            row=pro_tools_row, column=0, columnspan=2, sticky=self._start_sticky,
            padx=18, pady=(14, 4),
        )
        for i, (key, command) in enumerate((
            ("workspace_open", self._toggle_workspace),
            ("dup_open", self._open_duplicates),
            ("groups_manage", self._open_groups),
            ("diag_open", self._open_diagnostics),
            ("onb_title", self._replay_onboarding),
        )):
            self._button(
                pro, key, command, height=32, font=self.f_small, corner_radius=8,
                fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
            ).grid(
                row=pro_tools_row + 1 + i, column=0, columnspan=2, sticky="ew",
                padx=18, pady=(0, 6),
            )

        self._build_rules_tab(rules_tab)

    # ------------------------------------------------------------------
    def _pair_label(self, parent, row: int, key: str, pady=(5, 5)) -> ctk.CTkLabel:
        label = self._label(parent, key, font=self.f_body)
        label.grid(
            row=row, column=self._grid_col(0, 2), sticky=self._start_sticky,
            padx=self._pad(18, 8), pady=pady,
        )
        return label

    def _hint_label(self, parent, row: int, key: str) -> ctk.CTkLabel:
        label = self._label(
            parent, key, font=self.f_small, text_color=MUTED, wraplength=430
        )
        label.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=18,
            pady=(0, 8),
        )
        return label

    def _settings_switch_row(
        self, parent, row: int, key: str, selected: bool, command, pady
    ) -> ctk.CTkSwitch:
        holder = ctk.CTkFrame(parent, fg_color="transparent")
        holder.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=18, pady=pady
        )
        label = self._label(holder, key, font=self.f_small)
        switch = ctk.CTkSwitch(
            holder,
            text="",
            width=44,
            command=command,
            progress_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
        )
        if selected:
            switch.select()
        if is_rtl(self.settings.language):
            label.pack(side="right", fill="x", expand=True, padx=(10, 0))
            switch.pack(side="left")
        else:
            label.pack(side="left", fill="x", expand=True, padx=(0, 10))
            switch.pack(side="right")
        self._autowrap(label, padding=70)
        return switch

    # ==================================================================
    # Smart download rules
    # ==================================================================
    _RULE_HINTS = {
        "kind_video": "rule_kind_video_hint",
        "kind_audio": "rule_kind_audio_hint",
        "large_files": "rule_large_files_hint",
        "slow_quality": "rule_slow_quality_hint",
    }
    _RULE_VALUE_KEYS = {
        "kind": "rule_value_kind",
        "size": "rule_value_mb",
        "speed": "rule_value_kbps",
        "platform": "rule_value_platform",
        "keyword": "rule_value_keyword",
    }

    def _build_rules_tab(self, tab) -> None:
        tab.grid_rowconfigure(2, weight=1)
        self._label(tab, "rules_title", font=self.f_h2).grid(
            row=0, column=0, columnspan=2, sticky=self._start_sticky,
            padx=18, pady=(14, 2),
        )
        self._hint_label(tab, 1, "rules_hint")
        host = ctk.CTkFrame(tab, fg_color="transparent")
        host.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=12, pady=(4, 8))
        host.grid_columnconfigure(0, weight=1)
        self.rules_host = host
        self.rule_widgets: list[dict] = []
        self._render_rules()
        self._button(
            tab, "rule_add", self._open_rule_dialog,
            height=34, font=self.f_small, corner_radius=8,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 14))

    def _rule_display_name(self, rule: dict) -> str:
        key = str(rule.get("name_key") or "")
        if key:
            try:
                return self.T(key)
            except Exception:
                pass
        return str(rule.get("name") or rule.get("id") or "—")

    def _render_rules(self) -> None:
        host = getattr(self, "rules_host", None)
        if host is None:
            return
        for child in list(host.winfo_children()):
            child.destroy()
        self.rule_widgets = []
        rules = list(getattr(self.settings, "download_rules", []) or [])
        if not rules:
            ctk.CTkLabel(
                host, text=self.T("rule_custom_empty"), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=10)
            return

        for index, rule in enumerate(rules):
            row = ctk.CTkFrame(host, fg_color=SOFT_BUTTON, corner_radius=10)
            row.grid(row=index, column=0, sticky="ew", pady=(0, 6))
            row.grid_columnconfigure(self._grid_col(1, 3), weight=1)

            switch = ctk.CTkSwitch(
                row, text="", width=40, command=self._save_rule_changes,
                progress_color=ACCENT, button_hover_color=ACCENT_HOVER,
            )
            if rule.get("enabled"):
                switch.select()
            switch.grid(
                row=0, column=self._grid_col(0, 3), rowspan=3,
                padx=self._pad(10, 6), pady=10,
            )
            ctk.CTkLabel(
                row, text=self._rule_display_name(rule),
                font=self.f_small_bold, anchor=self.text_anchor,
                justify=self.text_justify,
            ).grid(
                row=0, column=self._grid_col(1, 3), sticky="ew",
                padx=self._pad(0, 6), pady=(8, 0),
            )
            hint_key = self._RULE_HINTS.get(str(rule.get("id") or ""), "rules_hint")
            ctk.CTkLabel(
                row, text=self.T(hint_key), font=self.f_small, text_color=MUTED,
                anchor=self.text_anchor, justify=self.text_justify, wraplength=360,
            ).grid(
                row=1, column=self._grid_col(1, 3), sticky="ew",
                padx=self._pad(0, 6), pady=(2, 4),
            )

            params = ctk.CTkFrame(row, fg_color="transparent")
            params.grid(
                row=2, column=self._grid_col(1, 3), sticky="ew",
                padx=self._pad(0, 6), pady=(0, 8),
            )
            widgets: dict = {"switch": switch, "rule": rule}
            condition = str(rule.get("condition") or "kind")
            value_key = self._RULE_VALUE_KEYS.get(condition, "rule_value")
            ctk.CTkLabel(
                params, text=self.T(value_key), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=0, column=self._grid_col(0, 2), sticky="ew", padx=self._pad(0, 6))
            value_var = tk.StringVar(value=str(rule.get("value") or ""))
            if condition == "kind":
                ctk.CTkOptionMenu(
                    params, variable=value_var, values=list(KIND_VALUES),
                    font=self.f_small, height=28, width=100, corner_radius=8,
                    command=lambda _v: self._save_rule_changes(),
                ).grid(row=0, column=self._grid_col(1, 2), sticky="ew", padx=self._pad(6, 0))
            else:
                ctk.CTkEntry(
                    params, textvariable=value_var, font=self.f_small,
                    height=28, width=100, corner_radius=8,
                ).grid(row=0, column=self._grid_col(1, 2), sticky="ew", padx=self._pad(6, 0))
            widgets["value"] = value_var

            action = str(rule.get("action") or "")
            if action in ("subdir", "max_height"):
                action_key = "rule_action_folder" if action == "subdir" else "rule_action_height"
                ctk.CTkLabel(
                    params, text=self.T(action_key), font=self.f_small,
                    text_color=MUTED, anchor=self.text_anchor,
                ).grid(row=1, column=self._grid_col(0, 2), sticky="ew",
                       padx=self._pad(0, 6), pady=(4, 0))
                action_var = tk.StringVar(value=str(rule.get("action_value") or ""))
                ctk.CTkEntry(
                    params, textvariable=action_var, font=self.f_small,
                    height=28, width=100, corner_radius=8,
                ).grid(row=1, column=self._grid_col(1, 2), sticky="ew",
                       padx=self._pad(6, 0), pady=(4, 0))
                widgets["action_value"] = action_var

            rule_id = str(rule.get("id") or "")
            ctk.CTkButton(
                row, text=self.T("rule_remove"), width=64, height=28,
                font=self.f_small, corner_radius=8,
                fg_color=SOFT_BUTTON, hover_color=DANGER, text_color=SOFT_TEXT,
                command=lambda rid=rule_id: self._remove_rule(rid),
            ).grid(
                row=0, column=self._grid_col(2, 3), rowspan=3,
                padx=self._pad(6, 10), pady=10,
            )
            self.rule_widgets.append(widgets)

    def _save_rule_changes(self) -> None:
        for widgets in getattr(self, "rule_widgets", []):
            rule = widgets["rule"]
            condition = str(rule.get("condition") or "")
            raw = widgets["value"].get()
            if condition in ("size", "speed"):
                try:
                    rule["value"] = int(float(raw))
                except (TypeError, ValueError):
                    pass
            elif condition == "kind":
                value = str(raw).strip().lower()
                if value in KIND_VALUES:
                    rule["value"] = value
            else:
                rule["value"] = str(raw).strip()[:60]
            if "action_value" in widgets:
                action_raw = widgets["action_value"].get()
                if rule.get("action") == "max_height":
                    try:
                        rule["action_value"] = int(float(action_raw))
                    except (TypeError, ValueError):
                        pass
                else:
                    rule["action_value"] = str(action_raw).strip()
            rule["enabled"] = bool(widgets["switch"].get())
        self.settings.download_rules = sanitize_rules(self.settings.download_rules)
        self.config.save(self.settings)
        self._set_status("status_settings_saved")

    def _remove_rule(self, rule_id: str) -> None:
        self.settings.download_rules = [
            rule for rule in (self.settings.download_rules or [])
            if str(rule.get("id") or "") != rule_id
        ]
        self.config.save(self.settings)
        self._render_rules()
        self._toast("success", "toast_rule_removed")

    def _open_rule_dialog(self) -> None:
        tokens = self.palette_tokens
        win = ctk.CTkToplevel(self)
        self.rule_dialog = win
        win.title(self.T("rule_add_title"))
        win.geometry("470x420")
        win.resizable(False, False)
        win.configure(fg_color=tokens["bg"])
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.grid_columnconfigure(0, weight=1)

        self._label(win, "rule_add_title", font=self.f_h2).grid(
            row=0, column=0, sticky=self._start_sticky, padx=18, pady=(14, 6)
        )
        name_var = tk.StringVar(value="")
        ctk.CTkEntry(
            win, textvariable=name_var, placeholder_text=self.T("rule_name"),
            font=self.f_small, height=32, corner_radius=8,
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))

        cond_var = tk.StringVar(value=VALID_CONDITIONS[0])
        action_var = tk.StringVar(value=VALID_ACTIONS[0])
        value_var = tk.StringVar(value="")
        action_value_var = tk.StringVar(value="Media")

        ctk.CTkLabel(
            win, text=self.T("rule_condition"), font=self.f_small,
            text_color=MUTED, anchor=self.text_anchor,
        ).grid(row=2, column=0, sticky="ew", padx=18)
        ctk.CTkOptionMenu(
            win, variable=cond_var,
            values=[self.T("rule_condition_" + key) for key in VALID_CONDITIONS],
            font=self.f_small, height=30, corner_radius=8,
        ).grid(row=3, column=0, sticky="ew", padx=18, pady=(2, 8))

        ctk.CTkLabel(
            win, text=self.T("rule_value"), font=self.f_small,
            text_color=MUTED, anchor=self.text_anchor,
        ).grid(row=4, column=0, sticky="ew", padx=18)
        ctk.CTkEntry(
            win, textvariable=value_var, font=self.f_small,
            height=30, corner_radius=8,
        ).grid(row=5, column=0, sticky="ew", padx=18, pady=(2, 8))

        ctk.CTkLabel(
            win, text=self.T("rule_action"), font=self.f_small,
            text_color=MUTED, anchor=self.text_anchor,
        ).grid(row=6, column=0, sticky="ew", padx=18)
        ctk.CTkOptionMenu(
            win, variable=action_var,
            values=[self.T("rule_action_" + key) for key in VALID_ACTIONS],
            font=self.f_small, height=30, corner_radius=8,
        ).grid(row=7, column=0, sticky="ew", padx=18, pady=(2, 8))
        ctk.CTkEntry(
            win, textvariable=action_value_var, font=self.f_small,
            height=30, corner_radius=8,
        ).grid(row=8, column=0, sticky="ew", padx=18, pady=(0, 10))

        self._button(
            win, "rule_save",
            lambda: self._save_custom_rule(
                name_var.get(), cond_var.get(), value_var.get(),
                action_var.get(), action_value_var.get(), win,
            ),
            height=34, font=self.f_small, corner_radius=8,
        ).grid(row=9, column=0, sticky="ew", padx=18, pady=(0, 14))
        win.after(80, lambda: self._centre_dialog(win, 470, 420))

    def _save_custom_rule(
        self, name: str, condition_label: str, value: str,
        action_label: str, action_value: str, win,
    ) -> None:
        condition = ""
        for key in VALID_CONDITIONS:
            if condition_label == self.T("rule_condition_" + key):
                condition = key
                break
        action = ""
        for key in VALID_ACTIONS:
            if action_label == self.T("rule_action_" + key):
                action = key
                break
        if (
            condition not in VALID_CONDITIONS
            or action not in VALID_ACTIONS
            or not str(value or "").strip()
        ):
            self._toast("error", "toast_rule_invalid")
            return
        raw = {
            "id": "custom-" + datetime.now().strftime("%H%M%S%f"),
            "name": str(name or "").strip()[:80] or self.T("rule_custom"),
            "name_key": "",
            "enabled": True,
            "condition": condition,
            "value": str(value).strip(),
            "action": action,
            "action_value": str(action_value or "").strip(),
        }
        clean = sanitize_rules([raw])
        if not clean:
            self._toast("error", "toast_rule_invalid")
            return
        self.settings.download_rules = list(self.settings.download_rules or []) + clean
        self.config.save(self.settings)
        try:
            win.destroy()
        except Exception:
            pass
        self._render_rules()
        self._toast("success", "toast_rule_saved")

    # ==================================================================
    # Groups, bandwidth, workspace & utility dialogs
    # ==================================================================
    def _group_choices(self) -> tuple[list[str], dict[str, str]]:
        groups = self.groups.groups()
        labels = [self.T("groups_unassigned")] + [g["name"] for g in groups]
        lookup: dict[str, str] = {labels[0]: ""}
        lookup.update({g["name"]: g["id"] for g in groups})
        return labels, lookup

    def _refresh_group_choices(self) -> None:
        menu = getattr(self, "group_menu", None)
        if menu is None:
            return
        labels, self.group_lookup = self._group_choices()
        current = menu.get()
        try:
            menu.configure(values=labels)
            menu.set(current if current in labels else labels[0])
        except Exception:
            pass

    def _selected_speed_limit(self) -> int:
        menu = getattr(self, "speed_menu", None)
        if menu is None:
            return 0
        try:
            return int(self.bw_values[self.bw_options.index(menu.get())])
        except (ValueError, IndexError, AttributeError):
            return 0

    def _selected_group(self) -> str:
        menu = getattr(self, "group_menu", None)
        if menu is None:
            return ""
        _, lookup = self._group_choices()
        return lookup.get(menu.get(), "")

    def _open_duplicates(self) -> None:
        self.duplicates_dialog = DuplicatesDialog(self)

    def _open_groups(self) -> None:
        self.groups_dialog = GroupsDialog(self)

    def _open_diagnostics(self) -> None:
        self.diagnostics_dialog = DiagnosticsDialog(self)

    def _open_onboarding(self) -> None:
        if not getattr(self, "_alive", False):
            return
        self.onboarding_dialog = OnboardingDialog(self)

    def _replay_onboarding(self) -> None:
        self.settings.onboarding_done = False
        self.config.save(self.settings)
        self._open_onboarding()

    def _open_speed_dialog(self, task_id: str) -> None:
        tokens = self.palette_tokens
        win = ctk.CTkToplevel(self)
        win.title(self.T("bw_menu"))
        win.geometry("300x330")
        win.resizable(False, False)
        win.configure(fg_color=tokens["bg"])
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            win, text=self.T("bw_hint"), font=self.f_small,
            text_color=tokens["muted"], anchor=self.text_anchor,
            justify=self.text_justify, wraplength=270,
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 8))
        choices = [(self.T("bw_auto"), 0), (self.T("bw_unlimited"), -1)] + [
            (self.T("bw_set", speed=value), value)
            for value in SPEED_LIMITS_KBPS if value
        ]
        for row, (label, value) in enumerate(choices, start=1):
            ctk.CTkButton(
                win, text=label, height=28, font=self.f_small, corner_radius=8,
                fg_color=tokens["soft_button"], hover_color=tokens["soft_hover"],
                text_color=tokens["soft_text"],
                command=lambda v=value: self._apply_task_speed(task_id, v, win),
            ).grid(row=row, column=0, sticky="ew", padx=16, pady=2)
        win.after(80, lambda: self._centre_dialog(win, 300, 330))

    def _apply_task_speed(self, task_id: str, value: int, win) -> None:
        if self.manager.set_task_speed_limit(task_id, value):
            self._toast("success", "bw_applied")
        try:
            win.destroy()
        except Exception:
            pass

    # ---- Media workspace (overlay, not a new sidebar item) -----------
    def _build_workspace_page(self) -> None:
        page = ctk.CTkScrollableFrame(
            self.pages_host, fg_color="transparent", corner_radius=0
        )
        self.workspace_page = page
        page.place(x=0, y=0, relwidth=1, relheight=1)
        page.lower()
        page.grid_columnconfigure(0, weight=3)
        page.grid_columnconfigure(1, weight=2)

        header = self._card(page)
        header.grid(
            row=0, column=0, columnspan=2, sticky="ew",
            padx=self._pad(10, 10), pady=(10, 10),
        )
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text=self.T("workspace_title"), font=self.f_h1,
            anchor=self.text_anchor, justify=self.text_justify,
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        ctk.CTkLabel(
            header, text=self.T("workspace_subtitle"), font=self.f_small,
            text_color=MUTED, anchor=self.text_anchor, justify=self.text_justify,
            wraplength=560,
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))
        self._button(
            header, "workspace_back", lambda: self._toggle_workspace(False),
            width=150, height=36, font=self.f_small, corner_radius=9,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
        ).grid(row=0, column=1, rowspan=2, sticky=self._end_sticky,
               padx=self._pad(0, 16), pady=14)

        ws_stats = ctk.CTkFrame(page, fg_color="transparent")
        ws_stats.grid(row=1, column=0, columnspan=2, sticky="ew",
                      padx=self._pad(10, 10))
        for i in range(4):
            ws_stats.grid_columnconfigure(i, weight=1)
        self.ws_kpis: dict[str, ctk.CTkLabel] = {}
        for i, key in enumerate(("total", "active", "completed", "size")):
            card = self._card(ws_stats)
            card.grid(row=0, column=i, sticky="ew",
                      padx=self._pad(0 if i == 0 else 5, 5 if i < 3 else 0),
                      ipady=3)
            label_key = {
                "total": "home_stats_total", "active": "home_stats_active",
                "completed": "home_stats_completed", "size": "home_stats_size",
            }[key]
            ctk.CTkLabel(
                card, text=self.T(label_key), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
            value = ctk.CTkLabel(card, text="—", font=self.f_h2,
                                 anchor=self.text_anchor)
            value.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 10))
            self.ws_kpis[key] = value

        # Left column: live tasks + recent library files.
        tasks_card = self._card(page)
        tasks_card.grid(row=2, column=0, sticky="ew",
                        padx=self._pad(10, 6), pady=(10, 6))
        tasks_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            tasks_card, text=self.T("workspace_tasks"), font=self.f_h2,
            anchor=self.text_anchor,
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        self.ws_tasks_host = ctk.CTkFrame(tasks_card, fg_color="transparent")
        self.ws_tasks_host.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.ws_tasks_host.grid_columnconfigure(0, weight=1)

        recent_card = self._card(page)
        recent_card.grid(row=3, column=0, sticky="ew",
                         padx=self._pad(10, 6), pady=(6, 12))
        recent_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            recent_card, text=self.T("workspace_recent"), font=self.f_h2,
            anchor=self.text_anchor,
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        self.ws_recent_host = ctk.CTkFrame(recent_card, fg_color="transparent")
        self.ws_recent_host.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.ws_recent_host.grid_columnconfigure(0, weight=1)

        # Right column: quick actions + tools shortcuts.
        quick_card = self._card(page)
        quick_card.grid(row=2, column=1, sticky="nsew",
                        padx=self._pad(6, 10), pady=(10, 6))
        quick_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            quick_card, text=self.T("workspace_quick"), font=self.f_h2,
            anchor=self.text_anchor,
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        for i, (key, command) in enumerate((
            ("link_inbox_title", self._open_link_inbox),
            ("dup_open", self._open_duplicates),
            ("groups_manage", self._open_groups),
            ("diag_open", self._open_diagnostics),
        )):
            self._button(
                quick_card, key, command, height=32, font=self.f_small,
                corner_radius=8, fg_color=SOFT_BUTTON,
                hover_color=SOFT_HOVER, text_color=SOFT_TEXT,
            ).grid(row=i + 1, column=0, sticky="ew", padx=14, pady=(0, 6))

        tools_card = self._card(page)
        tools_card.grid(row=3, column=1, sticky="nsew",
                        padx=self._pad(6, 10), pady=(6, 12))
        tools_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            tools_card, text=self.T("workspace_tools"), font=self.f_h2,
            anchor=self.text_anchor,
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        tool_keys = (
            "tool_extract_title", "tool_trim_title", "tool_compress_title",
            "tool_convert_title", "tool_gif_title", "tool_merge_title",
            "tool_subtitle_title", "tool_cover_title",
        )
        for i, key in enumerate(tool_keys):
            self._button(
                tools_card, key, lambda: self._switch_page(6),
                height=28, font=self.f_small, corner_radius=7,
                fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER,
                text_color=SOFT_TEXT,
            ).grid(row=i + 1, column=0, sticky="ew", padx=14, pady=(0, 4))

    def _toggle_workspace(self, show=None) -> None:
        page = getattr(self, "workspace_page", None)
        if page is None:
            return
        target = (not self.workspace_visible) if show is None else bool(show)
        if target == self.workspace_visible:
            return
        self.workspace_visible = target
        if target:
            page.place(x=0, y=0, relwidth=1, relheight=1)
            page.lift()
            self.page_title.configure(
                text=self.T("workspace_title"),
                anchor=self.text_anchor, justify=self.text_justify,
            )
            self.page_subtitle.configure(
                text=self.T("workspace_subtitle"),
                anchor=self.text_anchor, justify=self.text_justify,
            )
            self._refresh_workspace()
        else:
            page.lower()
            page.place_forget()
            title_key, subtitle_key = PAGE_HEADERS[
                max(0, min(len(PAGE_HEADERS) - 1, getattr(self, "current_tab_index", 0)))
            ]
            self.page_title.configure(
                text=self.T(title_key),
                anchor=self.text_anchor, justify=self.text_justify,
            )
            self.page_subtitle.configure(
                text=self.T(subtitle_key),
                anchor=self.text_anchor, justify=self.text_justify,
            )

    def _refresh_workspace(self) -> None:
        if not getattr(self, "workspace_visible", False):
            return
        try:
            entries = list(self.history.entries())
        except Exception:
            entries = []
        snapshots = self.manager.snapshots()
        total_size = sum(int(e.get("size") or 0) for e in entries)
        active = sum(
            1 for s in snapshots
            if s.get("status") in ("pending", "scheduled", "downloading", "paused", "processing")
        )
        completed = sum(1 for e in entries if e.get("status") == "completed")
        values = {
            "total": str(len(entries)),
            "active": str(active),
            "completed": str(completed),
            "size": format_bytes(total_size),
        }
        for key, label in self.ws_kpis.items():
            label.configure(text=values[key])

        sig = (
            tuple((s.get("id"), s.get("status"), s.get("progress")) for s in snapshots[:6]),
            tuple((e.get("id"), e.get("hash_status")) for e in entries[:5]),
        )
        if getattr(self, "_ws_sig", None) == sig:
            return
        self._ws_sig = sig

        for host in (self.ws_tasks_host, self.ws_recent_host):
            for child in list(host.winfo_children()):
                child.destroy()

        live = [s for s in snapshots if s.get("status") in (
            "pending", "scheduled", "downloading", "paused", "processing"
        )][:6]
        if not live:
            ctk.CTkLabel(
                self.ws_tasks_host, text=self.T("workspace_empty_tasks"),
                font=self.f_small, text_color=MUTED,
                anchor=self.text_anchor, justify=self.text_justify,
            ).grid(row=0, column=0, sticky="ew", pady=4)
        for index, snapshot in enumerate(live):
            row_frame = ctk.CTkFrame(
                self.ws_tasks_host, fg_color=self.palette_tokens["soft_button"],
                corner_radius=9,
            )
            row_frame.grid(row=index, column=0, sticky="ew", pady=(0, 5))
            row_frame.grid_columnconfigure(0, weight=1)
            status = str(snapshot.get("status") or "")
            ctk.CTkLabel(
                row_frame, text=str(snapshot.get("title") or "")[:54],
                font=self.f_small_bold, anchor=self.text_anchor,
                justify=self.text_justify,
            ).grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 0))
            ctk.CTkLabel(
                row_frame, text=self.T("state_" + status) if status else "",
                font=self.f_small, text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))

        for index, entry in enumerate(entries[:5]):
            row_frame = ctk.CTkFrame(
                self.ws_recent_host, fg_color=self.palette_tokens["soft_button"],
                corner_radius=9,
            )
            row_frame.grid(row=index, column=0, sticky="ew", pady=(0, 5))
            row_frame.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                row_frame, text=str(entry.get("title") or "")[:54],
                font=self.f_small, anchor=self.text_anchor,
                justify=self.text_justify,
            ).grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 0))
            badge = self.hash_badge(entry)[0]
            ctk.CTkLabel(
                row_frame, text=f"{format_bytes(entry.get('size') or 0)}  •  {badge}",
                font=self.f_small, text_color=MUTED, anchor=self.text_anchor,
            ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

    # ==================================================================
    # Navigation / theme / language
    # ==================================================================
    def _bind_shortcuts(self) -> None:
        for index in range(len(self.pages)):
            self.bind(
                f"<Control-Key-{index + 1}>",
                lambda _event, i=index: self._switch_page(i),
            )
        self.bind("<F5>", lambda _event: self.fetch_media())
        self.bind("<Control-f>", self._focus_search)
        self.bind("<Control-F>", self._focus_search)
        self.bind("<Control-v>", self._global_paste, add="+")
        self.bind("<Control-V>", self._global_paste, add="+")

    def _focus_search(self, _event=None):
        self._switch_page(5)
        try:
            self.after(120, self.history_search_entry.focus_set)
        except Exception:
            pass
        return "break"

    def _global_paste(self, event=None):
        """Ctrl+V outside an entry fills the URL field."""
        widget = getattr(event, "widget", None)
        try:
            if widget is not None and widget.winfo_class() in (
                "Entry", "TEntry", "Text", "TCombobox", "Spinbox",
            ):
                return None
        except Exception:
            pass
        self._paste_url()
        return "break"

    def _switch_page(self, index: int, animate: bool = True) -> None:
        """Switch pages instantly with Tk's stacking order.

        The previous implementation animated ``place(x=...)`` for both the
        outgoing and incoming page over 11 frames.  Every frame forced a full
        redraw of two large pages, which is the main source of the stutter.
        ``lift()`` only changes the stacking order — no geometry, no redraw
        of the hidden page, no widget rebuilding.

        Important: ``CTkScrollableFrame`` overrides ``lift()``/``lower()`` so
        they act on its outer ``_parent_frame``, but it does NOT override
        ``tkraise()``.  Using ``tkraise()`` here silently raises only the
        inner frame and leaves the scrollable page hidden behind another one.
        ``animate`` is kept for API compatibility but intentionally ignored.
        """
        index = max(0, min(len(self.pages) - 1, index))
        if getattr(self, "workspace_visible", False):
            self._toggle_workspace(False)
        new_page = self.pages[index]
        old_page = self.current_page
        if new_page is old_page:
            self._update_nav(index)
            return

        self.current_tab_index = index
        self.current_page = new_page

        title_key, subtitle_key = PAGE_HEADERS[index]
        self.page_title.configure(
            text=self.T(title_key),
            anchor=self.text_anchor,
            justify=self.text_justify,
        )
        self.page_subtitle.configure(
            text=self.T(subtitle_key),
            anchor=self.text_anchor,
            justify=self.text_justify,
        )

        if self._page_job is not None:
            try:
                self.after_cancel(self._page_job)
            except Exception:
                pass
            self._page_job = None

        if old_page is not None and old_page is not new_page:
            try:
                old_page.place_configure(x=0)
            except Exception:
                pass

        # Instant switch: lift() is overridden by CTkScrollableFrame to raise
        # its outer frame; tkraise() would only raise the inner content frame.
        if old_page is not None and old_page is not new_page:
            try:
                old_page.lower()
            except Exception:
                pass
        new_page.place_configure(x=0)
        new_page.lift()
        self._update_nav(index)
        # Deferred, cached refresh of the newly visible page only.  It runs
        # 220 ms later (off the click path) and is a no-op when data is unchanged.
        if index in (0, 2, 3, 4):
            self._schedule_dynamic_refresh()

    def _update_nav(self, index: int) -> None:
        for item_index, item in enumerate(self.nav_items):
            item.set_active(item_index == index)
        self._move_indicator()

    def _move_indicator(self, animate: bool = True) -> None:
        """Place the nav indicator once, after the layout has settled.

        The old 9-frame animation called ``update_idletasks()`` and queried
        every nav item's geometry on each step, forcing synchronous layout
        passes during navigation.  ``after_idle`` lets Tk compute geometry
        naturally, then we place the indicator a single time.
        """
        if not self.nav_items:
            return
        if self._nav_job is not None:
            try:
                self.after_cancel(self._nav_job)
            except Exception:
                pass
            self._nav_job = None
        self._nav_job = self.after_idle(self._place_nav_indicator)

    def _place_nav_indicator(self) -> None:
        self._nav_job = None
        if not self._alive or not self.nav_items:
            return
        try:
            item = self.nav_items[self.current_tab_index]
            target = (
                self.nav_frame.winfo_y()
                + item.winfo_y()
                + max(0, (item.winfo_height() - 26) // 2)
            )
            x = 4 if is_rtl(self.settings.language) else self.sidebar_width - 8
            self.nav_indicator.place(x=x, y=target)
        except Exception:
            return

    def _fade_in(self) -> None:
        if not self.animations_enabled:
            try:
                self.attributes("-alpha", 1.0)
            except Exception:
                pass
            return
        try:
            self.attributes("-alpha", 0.0)
        except Exception:
            return
        steps = 8

        def step(i: int) -> None:
            if not self._alive:
                return
            try:
                self.attributes("-alpha", min(1.0, i / steps))
            except Exception:
                return
            if i < steps:
                self.after(18, lambda: step(i + 1))

        step(0)

    def _toggle_theme(self) -> None:
        order = ("dark", "light", "system")
        try:
            nxt = order[(order.index(self.settings.theme) + 1) % len(order)]
        except ValueError:
            nxt = "dark"
        self._set_theme(nxt)

    def _set_theme(self, theme: str) -> None:
        if theme not in ("dark", "light", "system"):
            theme = "dark"
        self.settings.theme = theme
        try:
            ctk.set_appearance_mode(theme)
        except Exception:
            pass
        self.config.save(self.settings)
        try:
            index = ("dark", "light", "system").index(theme)
            self.theme_seg.set(self.theme_values[index])
        except Exception:
            pass
        self._update_header_buttons()
        self._set_status("status_settings_saved")

    def _apply_theme(self, index: int) -> None:
        theme = ("dark", "light", "system")[max(0, min(2, index))]
        self._set_theme(theme)

    def _on_theme_seg_changed(self, value: str) -> None:
        order = ("dark", "light", "system")
        index = self.theme_values.index(value) if value in self.theme_values else 0
        self._apply_theme(index)

    def _toggle_language(self) -> None:
        self.set_language("en" if self.settings.language == "ar" else "ar")

    def _on_lang_seg_changed(self, value: str) -> None:
        self.set_language("en" if value == "English" else "ar")

    def _update_header_buttons(self) -> None:
        icons = {"dark": "☀", "light": "☾", "system": "◐"}
        self.theme_btn.configure(text=icons.get(self.settings.theme, "☀"))
        self.lang_btn.configure(text="EN" if self.settings.language == "ar" else "ع")
        try:
            self.theme_tip.update_text(self.T("theme_toggle_tip"))
            self.lang_tip.update_text(self.T("lang_toggle_tip"))
        except Exception:
            pass

    def set_language(self, lang: str) -> None:
        if lang not in ("ar", "en") or lang == self.settings.language:
            return
        self.settings.language = lang
        self.config.save(self.settings)
        log.info("Language switched to %s", lang)
        self._schedule_rebuild()

    def _schedule_rebuild(self) -> None:
        if self._rebuild_job is not None:
            return
        self._rebuild_job = self.after(30, self._rebuild_ui)

    def _rebuild_ui(self) -> None:
        """Recreate every widget so RTL mirroring and palette changes apply.

        Patching dozens of widgets in place is fragile; rebuilding from the
        current language/palette keeps the layout correct by construction.
        Open queue cards, media info and the active tab are preserved.
        """
        self._rebuild_job = None
        if not self._alive:
            return

        for job in (self._page_job, self._nav_job, self._thumb_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._page_job = self._nav_job = self._thumb_job = None
        self._cancel_clipboard_watch()
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
            self._search_job = None

        if self._toast_widget is not None:
            try:
                self._toast_widget.destroy()
            except Exception:
                pass
            self._toast_widget = None

        card_ids = list(self.task_cards)
        snapshots = {snap["id"]: snap for snap in self.manager.snapshots()}
        tab = self.current_tab_index
        key, kwargs, error = self._status_state

        apply_palette(self.settings.palette)
        self.configure(fg_color=BG)
        self.title(translate(self.settings.language, "app_title"))

        for child in self.winfo_children():
            child.destroy()

        self.task_cards = {}
        self.history_rows = {}
        self._static_bindings = []
        self.palette_chips = []
        self.pages = []
        self.nav_items = []
        self.current_page = None

        self._scale_spacings.clear()
        self._history_columns = 0
        self._build_sidebar()
        self._build_content()
        self._build_pages()
        self._collect_spacings()

        if self._fetching:
            self.fetch_btn.configure(state="disabled", text=self.T("fetching"))

        self._render_info()
        self.mode_seg.set(self.mode_values[self.current_mode_index])
        self._refresh_quality_menu(preserve=True)
        self.download_btn.configure(
            text=self.T("download_audio_mp3" if self.current_mode_index == 1 else "download")
        )
        self._refresh_history()

        for task_id in card_ids:
            snapshot = snapshots.get(task_id)
            if snapshot:
                self._add_task_card(snapshot)
        self._update_queue_count()

        self._update_header_buttons()
        self._set_status(key, error=error, **kwargs)
        self._switch_page(tab, animate=False)
        self._move_indicator(animate=False)
        self._update_dynamic_stats()
        # --- new widget re-init ---
        self._show_info_skeleton(self._fetching)
        self._install_dnd()
        self._update_notification_badge()
        self._update_nav_badge()
        self._start_clipboard_watch()
        self._collect_spacings()

    def _on_palette_changed(self, value: str) -> None:
        try:
            key = PALETTE_KEYS[self.palette_values.index(value)]
        except (ValueError, IndexError):
            return
        if key == self.settings.palette:
            return
        self.settings.palette = key
        self.config.save(self.settings)
        apply_palette(key)
        self._status_state = ("status_settings_saved", {}, False)
        log.info("Palette switched to %s", key)
        self._schedule_rebuild()

    # ==================================================================
    # Toast notifications
    # ==================================================================
    def _toast(self, kind: str, key: str, **kwargs) -> None:
        if not self._alive:
            return
        if self._toast_widget is not None:
            try:
                self._toast_widget.dismiss()
            except Exception:
                pass
            self._toast_widget = None
        try:
            text = self.T(key, **kwargs)
            self._toast_widget = Toast(self, text, kind)
        except Exception:
            log.debug("Could not show toast", exc_info=True)

    # ==================================================================
    # Notification centre helpers
    # ==================================================================
    def _open_notifications(self) -> None:
        self._notif_seen = len(self.notifications)
        self._update_notification_badge()
        dlg = NotificationsDialog(self)
        self._set_status("status_opened_notifications")

    def _open_about(self) -> None:
        dlg = AboutDialog(self)
        self._set_status("status_opened_about")

    def _update_notification_badge(self) -> None:
        count = len(self.notifications) - self._notif_seen
        if count > 0:
            self.bell_badge.configure(text=str(min(99, count)))
            self.bell_badge.place(relx=0.9, rely=0.12, anchor="center")
            self.bell_badge.place_forget()
            self.bell_badge.place(relx=0.9, rely=0.12, anchor="center")
        else:
            self.bell_badge.place_forget()

    def clear_notifications(self) -> None:
        self.notifications.clear()
        self._notif_seen = 0
        self._update_notification_badge()

    def _push_notification(self, kind: str, key: str, **kwargs) -> None:
        """Store a notification for the centre and show a live toast."""
        try:
            from datetime import datetime

            text = self.T(key, **kwargs)
            self.notifications.append(
                {
                    "kind": kind,
                    "text": text,
                    "time": datetime.now().strftime("%H:%M"),
                }
            )
            del self.notifications[:-100]  # keep the most recent 100
            self._update_notification_badge()
        except Exception:
            log.debug("Could not store notification", exc_info=True)
        self._toast(kind, key, **kwargs)

    # ==================================================================
    # Context menus
    # ==================================================================
    def _show_task_menu(self, event, task_id: str) -> None:
        menu = ctk.CTkToplevel(self)
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.configure(fg_color=self.palette_tokens["bg"])
        try:
            x = self.winfo_rootx() + event.x
            y = self.winfo_rooty() + event.y
        except Exception:
            x = y = 0
        menu.geometry(f"+{x}+{y}")

        card = self.task_cards.get(task_id)
        if not card:
            menu.destroy()
            return

        snapshot = card.snapshot
        status = snapshot.get("status", "pending")

        items = [
            (self.T("ctx_open_file"), lambda: self.open_task_file(task_id)),
            (self.T("ctx_open_folder"), lambda: self.open_history_file(snapshot)),
            (self.T("ctx_copy_link"), lambda: self._copy_link(task_id)),
        ]
        if status in ("pending", "scheduled", "downloading", "paused"):
            items.append((self.T("ctx_pause"), lambda: self.toggle_pause(task_id)))
        if status in ("downloading", "paused"):
            items.append((self.T("ctx_resume"), lambda: self.toggle_pause(task_id)))
        if status in ("pending", "scheduled", "downloading", "paused"):
            items.append((self.T("bw_menu"), lambda: self._open_speed_dialog(task_id)))
        if status == "downloading":
            items.append((self.T("ctx_cancel"), lambda: self.cancel_task(task_id)))
        if status in ("error", "cancelled"):
            items.extend([
                (self.T("ctx_retry"), lambda: self.retry_task(task_id)),
                (self.T("ctx_remove"), lambda: self.remove_task_card(task_id)),
            ])

        for i, (label, cmd) in enumerate(items):
            btn = ctk.CTkButton(
                menu,
                text=label,
                height=28,
                font=self.f_small,
                fg_color=self.palette_tokens["soft_button"],
                hover_color=self.palette_tokens["soft_hover"],
                text_color=self.palette_tokens["soft_text"],
                command=cmd,
            )
            btn.grid(row=i, column=0, sticky="ew", padx=4, pady=2)

        menu.lift()
        self.after(2000, menu.destroy)

    def _show_history_menu(self, event, entry: dict) -> None:
        menu = ctk.CTkToplevel(self)
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.configure(fg_color=self.palette_tokens["bg"])
        try:
            x = self.winfo_rootx() + event.x
            y = self.winfo_rooty() + event.y
        except Exception:
            x = y = 0
        menu.geometry(f"+{x}+{y}")

        fav_key = "ctx_remove_favorite" if entry.get("favorite") else "ctx_add_favorite"
        items = [
            (self.T(fav_key), lambda: self.toggle_history_favorite(entry)),
            (self.T("ctx_edit_tags"), lambda: self._edit_history_tags(entry)),
            (self.T("ctx_verify_hash"), lambda: self.verify_history_hash(entry)),
            (self.T("ctx_set_expected_hash"), lambda: self._set_expected_history_hash(entry)),
            (self.T("ctx_open_file"), lambda: self.open_history_file(entry)),
            (self.T("ctx_open_folder"), lambda: self.open_history_file(entry)),
        ]
        if entry.get("filepath"):
            items.append((self.T("ctx_copy_link"), lambda: self._copy_link_url(entry.get("url", ""))))
        tags = entry.get("tags") or []
        if tags:
            items.append((
                self.T("tags_current", tags=", ".join(str(tag) for tag in tags)),
                lambda: self._edit_history_tags(entry),
            ))

        for i, (label, cmd) in enumerate(items):
            btn = ctk.CTkButton(
                menu,
                text=label,
                height=28,
                font=self.f_small,
                fg_color=self.palette_tokens["soft_button"],
                hover_color=self.palette_tokens["soft_hover"],
                text_color=self.palette_tokens["soft_text"],
                command=cmd,
            )
            btn.grid(row=i, column=0, sticky="ew", padx=4, pady=2)

        menu.lift()
        self.after(2000, menu.destroy)

    def _copy_link(self, task_id: str) -> None:
        card = self.task_cards.get(task_id)
        if not card:
            return
        url = card.snapshot.get("request", {}).get("url", "")
        self._set_status("status_copied")
        try:
            self.clipboard_clear()
            self.clipboard_append(url)
        except Exception:
            pass

    def _copy_link_url(self, url: str) -> None:
        self._set_status("status_copied")
        try:
            self.clipboard_clear()
            self.clipboard_append(url)
        except Exception:
            pass

    # ==================================================================
    # Drag & drop (optional tkinterdnd2)
    # ==================================================================
    def _install_dnd(self) -> None:
        if DND_AVAILABLE and not self._dnd_ready:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<Drop>>", self._on_dnd_drop)
                self._dnd_ready = True
            except Exception:
                pass
        elif not DND_AVAILABLE:
            # graceful fallback: show a hint label
            if not hasattr(self, "_dnd_fallback_label"):
                self._dnd_fallback_label = ctk.CTkLabel(
                    self.content,
                    text=self.T("drop_hint"),
                    font=self.f_small,
                    text_color=MUTED,
                )
                self._dnd_fallback_label.place(relx=0.5, rely=0.5, anchor="center")
        # always ensure the paste btn works
        try:
            self.paste_btn.configure(state="normal")
        except Exception:
            pass

    def _on_dnd_drop(self, event) -> None:
        try:
            text = self.tk.splitlist(event.data)
            for item in text:
                url = normalize_url(item)
                if url and is_valid_url(url):
                    self.url_entry.delete(0, "end")
                    self.url_entry.insert(0, url)
                    self._paste_url()
                    break
        except Exception:
            pass

    # ==================================================================
    # History rendering rewrite (KPI + grid/list/empty + date grouping)
    # ==================================================================
    def _set_library_view(self, view: str) -> None:
        self.library_view = view
        self.settings.library_view = view
        self.config.save(self.settings)
        # update button selection
        self.grid_view_btn.configure(fg_color=ACCENT if view == "grid" else SOFT_BUTTON)
        self.list_view_btn.configure(fg_color=ACCENT if view == "list" else SOFT_BUTTON)
        # rebuild history rows
        self._refresh_history()

    def _style_history_chips(self) -> None:
        for kind, chip in self.history_chip_buttons.items():
            is_active = kind == self.history_kind
            chip.configure(
                fg_color=ACCENT if is_active else SOFT_BUTTON,
                text_color=("#FFFFFF", "#101014") if is_active else SOFT_TEXT,
            )
        fav_chip = getattr(self, "favorite_chip", None)
        if fav_chip is not None:
            fav_chip.configure(
                fg_color=ACCENT if self.favorites_only else SOFT_BUTTON,
                text_color=("#FFFFFF", "#101014") if self.favorites_only else SOFT_TEXT,
            )

    def _style_view_buttons(self) -> None:
        # ensure initial state matches saved view
        self._set_library_view(self.settings.library_view or "grid")

    def _on_history_chip(self, kind: str) -> None:
        self.history_kind = kind
        self._style_history_chips()
        self._refresh_history()

    def _on_favorite_chip(self) -> None:
        self.favorites_only = not self.favorites_only
        self._style_history_chips()
        self._refresh_history()

    # -- library sorting ---------------------------------------------------
    def _sort_button_text(self) -> str:
        for mode, key in LIBRARY_SORTS:
            if mode == self.library_sort:
                return self.T(key)
        return self.T("sort_date_desc")

    def _show_sort_menu(self) -> None:
        self._close_sort_menu()
        menu = ctk.CTkToplevel(self)
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.configure(fg_color=self.palette_tokens["bg"])
        try:
            x = self.sort_btn.winfo_rootx()
            y = self.sort_btn.winfo_rooty() + self.sort_btn.winfo_height()
        except Exception:
            x = y = 0
        menu.geometry(f"+{x}+{y}")
        tokens = self.palette_tokens
        for i, (mode, key) in enumerate(LIBRARY_SORTS):
            active = mode == self.library_sort
            btn = ctk.CTkButton(
                menu,
                text=self.T(key),
                height=28,
                width=160,
                font=self.f_small,
                fg_color=tokens["accent"] if active else tokens["soft_button"],
                hover_color=tokens["soft_hover"],
                text_color="#FFFFFF" if active else tokens["soft_text"],
                command=lambda m=mode: self._set_library_sort(m),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=4, pady=2)
        self._sort_menu = menu
        menu.lift()
        self.after(3000, self._close_sort_menu)

    def _close_sort_menu(self) -> None:
        menu = self._sort_menu
        self._sort_menu = None
        if menu is not None:
            try:
                if menu.winfo_exists():
                    menu.destroy()
            except Exception:
                pass

    def _set_library_sort(self, mode: str) -> None:
        self.library_sort = mode
        self.settings.library_sort = mode
        self.config.save(self.settings)
        self._close_sort_menu()
        try:
            self.sort_btn.configure(text=self._sort_button_text())
        except Exception:
            pass
        self._refresh_history()

    def _sort_history_entries(self, entries: list[dict]) -> list[dict]:
        mode = self.library_sort
        if mode == "date_asc":
            return sorted(entries, key=lambda e: str(e.get("timestamp") or ""))
        if mode == "date_desc":
            return sorted(entries, key=lambda e: str(e.get("timestamp") or ""), reverse=True)
        if mode == "size_desc":
            return sorted(entries, key=lambda e: int(e.get("size") or 0), reverse=True)
        if mode == "size_asc":
            return sorted(entries, key=lambda e: int(e.get("size") or 0))
        if mode == "name_asc":
            return sorted(entries, key=lambda e: str(e.get("title") or "").casefold())
        if mode == "name_desc":
            return sorted(entries, key=lambda e: str(e.get("title") or "").casefold(), reverse=True)
        if mode == "type":
            return sorted(
                entries,
                key=lambda e: (
                    media_kind(e.get("filepath") or ""),
                    str(e.get("title") or "").casefold(),
                ),
            )
        return entries

    # -- favorites / tags --------------------------------------------------
    def toggle_history_favorite(self, entry: dict) -> None:
        new_state = self.history.toggle_favorite(entry.get("id", ""))
        if new_state is None:
            return
        entry["favorite"] = new_state
        key = "toast_fav_added" if new_state else "toast_fav_removed"
        self._toast("success" if new_state else "info", key)
        self._refresh_history()

    def _edit_history_tags(self, entry: dict) -> None:
        tokens = self.palette_tokens
        win = ctk.CTkToplevel(self)
        self.tag_dialog = win
        win.title(self.T("tags_dialog_title"))
        win.geometry("440x230")
        win.resizable(False, False)
        win.configure(fg_color=tokens["bg"])
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            win, text=self.T("tags_dialog_title"), font=self.f_h2,
            anchor=self.text_anchor, justify=self.text_justify,
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            win, text=self.T("tags_dialog_hint"), font=self.f_small,
            text_color=tokens["muted"], anchor=self.text_anchor,
            justify=self.text_justify, wraplength=400,
        ).grid(row=1, column=0, sticky="ew", padx=18)

        raw = ", ".join(str(tag) for tag in (entry.get("tags") or []))
        tag_var = tk.StringVar(value=raw)
        tag_entry = ctk.CTkEntry(
            win, textvariable=tag_var, height=36, font=self.f_small, corner_radius=10
        )
        tag_entry.grid(row=2, column=0, sticky="ew", padx=18, pady=12)
        tag_entry.focus_set()
        ctk.CTkButton(
            win,
            text=self.T("tags_dialog_save"),
            height=36,
            corner_radius=10,
            font=self.f_small,
            fg_color=tokens["accent"],
            hover_color=tokens["accent_hover"],
            command=lambda: self._save_history_tags(entry, tag_var.get(), win),
        ).grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 16))
        win.after(80, lambda: self._centre_dialog(win, 440, 230))

    def _save_history_tags(self, entry: dict, raw: str, win: ctk.CTkToplevel) -> None:
        parts = (raw or "").replace("،", ",").split(",")
        tags = [part.strip().lstrip("#") for part in parts if part.strip()][:12]
        self.history.set_tags(entry.get("id", ""), tags)
        entry["tags"] = tags
        self._toast("success", "toast_tags_saved")
        try:
            win.destroy()
        except Exception:
            pass
        self._refresh_history()

    def _centre_dialog(self, win: ctk.CTkToplevel, width: int, height: int) -> None:
        try:
            win.update_idletasks()
            px, py = self.winfo_rootx(), self.winfo_rooty()
            pw, ph = self.winfo_width(), self.winfo_height()
            x = max(0, px + (pw - width) // 2)
            y = max(0, py + (ph - height) // 2)
            win.geometry(f"+{x}+{y}")
            win.lift()
            win.focus_force()
            win.grab_set()
        except Exception:
            pass

    def _clear_history_search(self) -> None:
        self.history_query = ""
        self.history_search_var.set("")
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
            self._search_job = None
        self._finish_history_search()

    def _on_history_resize(self, event=None) -> None:
        """Kept for compatibility; resizing no longer rebuilds history rows."""
        return

    def _reflow_history(self) -> None:
        """Kept for compatibility; layout is handled natively by pack/grid."""
        return

    def _empty_state_action(self) -> None:
        self._switch_page(1)  # switch to download page

    # ==================================================================
    # Skeleton / action bar / status bar
    # ==================================================================
    def _show_info_skeleton(self, fetching: bool) -> None:
        if fetching:
            self.thumb_skeleton.grid()
            self.info_skeleton.grid()
        else:
            self.thumb_skeleton.grid_remove()
            self.info_skeleton.grid_remove()

    def _update_action_bar(self) -> None:
        active = sum(
            1 for c in self.task_cards.values()
            if c.snapshot.get("status") in ("pending", "scheduled", "downloading", "processing")
        )
        self.action_status_label.configure(text=self.T("download_status_idle"))
        if active:
            self.action_progress.set(active / max(1, len(self.task_cards)))
            self.action_progress.grid()
            self.download_btn.grid_remove()
            # Add pulse effect when active
            try:
                self.action_progress.configure(progress_color=ACCENT)
            except Exception:
                pass
        else:
            self.action_progress.grid_remove()
            self.download_btn.grid()

    def _update_status_bar(self) -> None:
        # connection dot
        if self._connection_online:
            self.conn_label.configure(text="● " + self.T("status_connection_online"), text_color=SUCCESS)
        else:
            self.conn_label.configure(text="● " + self.T("status_connection_offline"), text_color=WARN)
        # total speed
        speed = sum(
            float(c.snapshot.get("speed") or 0)
            for c in self.task_cards.values()
            if c.snapshot.get("status") == "downloading"
        )
        self.total_speed_label.configure(text=self.T("status_total_speed", speed=format_speed(speed) if speed else "—"))
        # Free space is computed off-thread by _check_disk_space_async(); this
        # method must stay free of blocking disk I/O on the UI thread.

    def _check_disk_space_async(self) -> None:
        """Query disk usage on a worker thread, never on the UI thread."""
        if getattr(self, "_disk_busy", False):
            return
        self._disk_busy = True

        def worker() -> None:
            value = "—"
            try:
                total, used = shutil.disk_usage(self.settings.download_dir)
                value = format_bytes(total - used)
            except Exception:
                pass
            if self._alive:
                try:
                    self.after(0, lambda v=value: self._apply_disk_space(v))
                except Exception:
                    pass
            self._disk_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _apply_disk_space(self, value: str) -> None:
        try:
            self.space_label.configure(text=self.T("status_space", free=value))
        except Exception:
            pass
        try:
            home_label = getattr(self, "home_space_label", None)
            if home_label is not None:
                home_label.configure(text=value)
        except Exception:
            pass

    def _check_connection_async(self) -> None:
        """Probe connectivity off-thread so the UI never blocks."""

        def worker() -> None:
            online = False
            try:
                import socket

                with socket.create_connection(("1.1.1.1", 53), timeout=1.5):
                    online = True
            except OSError:
                pass
            if self._alive:
                try:
                    self.after(0, lambda: self._apply_connection(online))
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _apply_connection(self, online: bool) -> None:
        self._connection_online = online
        try:
            if online:
                self.conn_label.configure(
                    text="● " + self.T("status_connection_online"), text_color=SUCCESS
                )
            else:
                self.conn_label.configure(
                    text="● " + self.T("status_connection_offline"), text_color=WARN
                )
            side = getattr(self, "side_conn_label", None)
            if side is not None:
                side.configure(
                    text="● " + self.T(
                        "status_connection_online" if online else "status_connection_offline"
                    ),
                    text_color=SUCCESS if online else WARN,
                )
        except Exception:
            pass

    def _tick_status_bar(self) -> None:
        self._check_connection_async()
        self._check_disk_space_async()
        self._update_status_bar()
        # Refresh the visible dynamic page independently of navigation, roughly
        # every 5.2 s.  Event-driven refreshes still use the debounced path.
        self._dyn_tick = getattr(self, "_dyn_tick", 0) + 1
        if self._dyn_tick % 2 == 0 and getattr(self, "_dyn_job", None) is None:
            self._refresh_dynamic_pages()
        self._status_job = self.after(2600, self._tick_status_bar)

    def _update_nav_badge(self) -> None:
        # active-download badge on sidebar nav
        active = sum(
            1 for c in self.task_cards.values()
            if c.snapshot.get("status") in ("pending", "scheduled", "downloading", "processing")
        )
        for item_index, item in enumerate(self.nav_items):
            item.set_badge(active if item_index in (1, 2) else 0)

    def _flash_saved(self) -> None:
        # transient badge on settings-saved
        self.saved_badge.grid()
        self.after(1500, lambda: self.saved_badge.grid_remove())

    # ==================================================================
    # Accessibility handlers
    # ==================================================================
    def _on_ui_scale_changed(self, value: str) -> None:
        self.settings.ui_scale = value
        self.config.save(self.settings)
        apply_palette(self.settings.palette)
        # Every registered font follows the saved preference in place; no
        # widget rebuild is needed for a font-size change.
        self._refresh_registered_sizes()

    def _on_reduce_motion_changed(self, value: bool) -> None:
        self.settings.reduce_motion = bool(value)
        self.config.save(self.settings)
        self._schedule_rebuild()
    def _on_fetch_shortcut(self, _event=None) -> None:
        self.fetch_media()

    def _paste_url(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            self._set_status("status_paste_empty", error=True)
            return
        url = normalize_url(text) or text.strip()
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url)
        self.url_entry.focus_set()

    def _clear_url(self) -> None:
        """Clear the URL entry field and reset status."""
        self.url_entry.delete(0, "end")
        self._set_status("status_ready")

    def _preview_current(self) -> None:
        url = normalize_url(self.url_entry.get())
        if not url or not is_valid_url(url):
            self._show_error("err_invalid_url")
            return
        try:
            webbrowser.open(url)
            self._set_status("status_fetched")
        except Exception:
            self._show_error("err_generic")

    def _show_qr(self) -> None:
        url = normalize_url(self.url_entry.get()) or self.url_entry.get().strip()
        if not url or not is_valid_url(url):
            self._show_error("err_qr_empty")
            return
        QRDialog(self, url)

    # ------------------------------------------------------------------
    # Automatic clipboard detection
    # ------------------------------------------------------------------
    def _start_clipboard_watch(self) -> None:
        self._cancel_clipboard_watch()
        if self.settings.auto_clipboard:
            self._clipboard_job = self.after(1200, self._watch_clipboard)

    def _cancel_clipboard_watch(self) -> None:
        if self._clipboard_job is not None:
            try:
                self.after_cancel(self._clipboard_job)
            except Exception:
                pass
            self._clipboard_job = None

    def _window_active(self) -> bool:
        try:
            return self.focus_displayof() is not None
        except Exception:
            return True

    def _watch_clipboard(self) -> None:
        self._clipboard_job = None
        if not self._alive:
            return
        try:
            if self.settings.auto_clipboard and self._window_active():
                text = self.clipboard_get()
                url = normalize_url(text)
                if url and is_valid_url(url) and url != self._clipboard_last:
                    self._clipboard_last = url
                    current = self.url_entry.get().strip()
                    if not current or current == self._auto_url:
                        self.url_entry.delete(0, "end")
                        self.url_entry.insert(0, url)
                        self._auto_url = url
                        self._set_status("status_clipboard_detected")
                        self._toast("info", "status_clipboard_detected")
                        if bool(getattr(self.settings, "auto_fetch_clipboard", False)):
                            answer = messagebox.askyesno(
                                self.T("clipboard_prompt_title"),
                                self.T("clipboard_download_prompt"),
                                parent=self,
                            )
                            if answer:
                                self.after(80, self.fetch_media)
        except tk.TclError:
            pass
        except Exception:  # pragma: no cover - clipboard is best effort
            log.debug("Clipboard watch failed", exc_info=True)
        finally:
            if self._alive:
                self._clipboard_job = self.after(1500, self._watch_clipboard)

    def fetch_media(self) -> None:
        if self._fetching:
            return
        url = normalize_url(self.url_entry.get())
        if not url:
            self._show_error("err_empty_url")
            return
        if not is_valid_url(url):
            self._show_error("err_invalid_url")
            return

        self._fetching = True
        self._show_info_skeleton(True)
        self.fetch_btn.configure(state="disabled", text=self.T("fetching"))
        self._set_status("status_fetching")
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url: str) -> None:
        extractor = MediaExtractor(
            self.ffmpeg.directory if self.ffmpeg else None,
            self.js_runtimes,
        )
        try:
            info = extractor.fetch(url)
            self.events.put(("info_loaded", info))
        except TaskFailed as exc:
            self.events.put(("info_error", (exc.key, exc.detail)))
        except Exception as exc:  # pragma: no cover - defensive
            key, detail = friendly_error(exc)
            self.events.put(("info_error", (key, detail)))

    def _on_info_loaded(self, info: MediaInfo) -> None:
        self._fetching = False
        self._show_info_skeleton(False)
        self.fetch_btn.configure(state="normal", text=self.T("fetch"))
        self.current_info = info
        self._render_info()
        self._refresh_quality_menu(preserve=False)
        self._set_status("status_playlist_loaded" if info.is_playlist else "status_fetched")

    def _on_info_error(self, payload: tuple[str, str]) -> None:
        key, detail = payload
        self._fetching = False
        self._show_info_skeleton(False)
        self.fetch_btn.configure(state="normal", text=self.T("fetch"))
        self.current_info = None
        self._render_info()
        self._set_status(key, error=True)
        log.error("Fetch failed: %s | %s", key, detail)
        messagebox.showerror(
            translate(self.settings.language, "error_title"),
            translate(self.settings.language, key),
            parent=self,
        )

    def _render_info(self) -> None:
        info = self.current_info
        self.info_title.configure(anchor=self.text_anchor, justify=self.text_justify)
        self.info_meta.configure(anchor=self.text_anchor, justify=self.text_justify)
        self.playlist_label.configure(anchor=self.text_anchor, justify=self.text_justify)

        if not info:
            self.info_title.configure(text=self.T("info_empty_title"))
            self.info_meta.configure(text=self.T("info_empty_hint"))
            self.thumb_label.configure(image=None, text="🎬")
            self._thumb_image = None
            self.playlist_frame.grid_remove()
            self.info_actions.grid_remove()
            self.quality_choices = build_video_choices([])
            return

        self.info_title.configure(text=self.S(info.title))

        parts: list[str] = []
        if info.uploader:
            parts.append(info.uploader)
        if info.platform:
            parts.append(info.platform)
        if info.duration:
            parts.append(
                f"{translate(self.settings.language, 'info_duration')} {format_duration(info.duration)}"
            )
        if info.is_playlist:
            parts.append(translate(self.settings.language, "info_entries", count=info.entry_count))
        approx_size = str(getattr(info, "approx_size", "") or "")
        if approx_size:
            parts.append(self.T("info_size", size=approx_size))
        suggested = (
            "MP3" if self.current_mode_index == 1
            else str(getattr(self.settings, "video_container", "mp4") or "mp4").upper()
        )
        parts.append(self.T("info_suggest_format", format=suggested))
        self.info_meta.configure(text=self.S("  •  ".join(parts)))

        if info.thumbnail_path and Path(info.thumbnail_path).exists():
            try:
                image = Image.open(info.thumbnail_path).convert("RGB")
                image = ImageOps.fit(image, THUMB_SIZE, Image.LANCZOS)
                self._animate_thumbnail(image)
            except Exception as exc:
                log.debug("Could not render thumbnail: %s", exc)
                self.thumb_label.configure(image=None, text="🎬")
                self._thumb_image = None
        else:
            self.thumb_label.configure(image=None, text="🎬")
            self._thumb_image = None

        if info.is_playlist and info.entries:
            self.playlist_label.configure(
                text=f"{self.T('info_playlist')}  •  {self.T('info_entries', count=info.entry_count)}"
            )
            self.choose_btn.configure(text=self.T("choose_items"))
            self.playlist_frame.grid()
        else:
            self.playlist_frame.grid_remove()

        if info.url and is_valid_url(info.url):
            self.info_actions.grid()
        else:
            self.info_actions.grid_remove()

    def _animate_thumbnail(self, image: Image.Image) -> None:
        if self._thumb_job is not None:
            try:
                self.after_cancel(self._thumb_job)
            except Exception:
                pass
            self._thumb_job = None
        frames = (0.82, 0.89, 0.95, 0.98, 1.0)

        def step(index: int) -> None:
            if not self._alive or not self.thumb_label.winfo_exists():
                return
            scale = frames[index]
            self._thumb_frame_scale = scale
            size = self._thumb_display_size(scale)
            frame = ImageOps.fit(image, size, Image.LANCZOS)
            self._thumb_image = ctk.CTkImage(
                light_image=frame, dark_image=frame, size=size
            )
            self.thumb_label.configure(image=self._thumb_image, text="")
            if index < len(frames) - 1:
                self._thumb_job = self.after(36, lambda: step(index + 1))
            else:
                self._thumb_job = None

        step(0)

    # ==================================================================
    # Quality / options
    # ==================================================================
    def _choice_label(self, choice: FormatChoice) -> str:
        if choice.kind == "audio":
            if choice.codec == "m4a":
                return self.T("audio_m4a_best")
            return f"MP3 {choice.bitrate} kbps"
        if choice.height is None:
            return self.T("quality_best")
        tag = VIDEO_HEIGHT_TAGS.get(choice.height)
        return f"{choice.height}p ({tag})" if tag else f"{choice.height}p"

    def _refresh_quality_menu(self, preserve: bool = True) -> None:
        if self.current_mode_index == 1:
            choices = build_audio_choices()
            default_id = f"audio-mp3-{self.settings.audio_quality}"
        else:
            heights = self.current_info.heights if self.current_info else []
            choices = build_video_choices(heights)
            default_id = "video-best"

        previous_id = None
        if preserve and self.quality_choices:
            index = min(self.quality_index, len(self.quality_choices) - 1)
            previous_id = self.quality_choices[index].id

        self.quality_choices = choices
        labels = [self._choice_label(choice) for choice in choices]
        self.quality_menu.configure(values=labels)

        target = previous_id if previous_id and any(c.id == previous_id for c in choices) else default_id
        index = next((i for i, choice in enumerate(choices) if choice.id == target), 0)
        self.quality_index = index
        self.quality_menu.set(labels[index])

    def _selected_choice(self) -> FormatChoice:
        if not self.quality_choices:
            return FormatChoice(id="video-best", kind="video")
        index = max(0, min(self.quality_index, len(self.quality_choices) - 1))
        return self.quality_choices[index]

    def _on_quality_changed(self, value: str) -> None:
        labels = [self._choice_label(choice) for choice in self.quality_choices]
        if value in labels:
            self.quality_index = labels.index(value)

    def _on_mode_changed(self, value: str) -> None:
        self.current_mode_index = 1 if value == self.mode_values[1] else 0
        self._refresh_quality_menu(preserve=False)
        self.download_btn.configure(
            text=self.T("download_audio_mp3" if self.current_mode_index == 1 else "download")
        )

    def _choose_download_dir(self) -> None:
        folder = filedialog.askdirectory(
            parent=self,
            initialdir=self.settings.download_dir,
            title=translate(self.settings.language, "choose_folder_title"),
        )
        if not folder:
            return
        self.settings.download_dir = folder
        self.settings = self.settings.sanitized()
        self.config.save(self.settings)
        self.dest_var.set(self.settings.download_dir)
        self._set_status("status_settings_saved")

    # ==================================================================
    # Download flow
    # ==================================================================
    def _priority_name(self, value: int) -> str:
        labels = getattr(self, "priority_labels", [])
        if len(labels) == 3:
            return labels[max(0, min(2, value + 1))]
        return str(value)

    def _selected_priority(self) -> int:
        menu = getattr(self, "priority_menu", None)
        if menu is None:
            return 0
        try:
            index = self.priority_labels.index(menu.get())
        except (ValueError, AttributeError):
            return 0
        return int(self.priority_values[index])

    def _current_speed_kbps(self) -> float:
        """Current download speed in KB/s, used by the slow-connection rule."""
        try:
            snapshots = self.manager.snapshots()
        except Exception:
            return 0.0
        total = 0.0
        for snapshot in snapshots:
            if snapshot.get("status") != "downloading":
                continue
            try:
                total += float(snapshot.get("speed") or 0)
            except (TypeError, ValueError):
                continue
        return total / 1024

    def _make_request(self, url: str, title: str, platform: str, thumbnail: str) -> DownloadRequest:
        mode = "audio" if self.current_mode_index == 1 else "video"
        choice = self._selected_choice()
        request = DownloadRequest(
            url=url,
            title=title,
            mode=mode,
            height=choice.height if mode == "video" else None,
            audio_codec=choice.codec if mode == "audio" and choice.codec else "mp3",
            audio_bitrate=choice.bitrate if mode == "audio" else None,
            dest_dir=self.settings.download_dir,
            platform=platform,
            thumbnail_path=thumbnail,
            speed_limit_kbps=self._selected_speed_limit(),
            group=self._selected_group(),
        )
        approx_bytes = (
            parse_size_text(getattr(self.current_info, "approx_size", ""))
            if self.current_info else 0
        )
        request, applied = apply_rules(
            request,
            list(getattr(self.settings, "download_rules", []) or []),
            approx_bytes=approx_bytes,
            speed_kbps=self._current_speed_kbps(),
        )
        if applied:
            self._set_status("status_rules_applied", names=", ".join(applied))
        return request

    def _find_active_duplicate(self, url: str) -> bool:
        """Return True when *url* is already queued or downloading."""
        if not url:
            return False
        active = ("pending", "scheduled", "downloading", "paused", "processing")
        for snapshot in self.manager.snapshots():
            if snapshot.get("status") not in active:
                continue
            request = snapshot.get("request") or {}
            if request.get("url") == url:
                return True
        return False

    def _open_link_inbox(self) -> None:
        """Open (or focus) the batch-link inbox dialog."""
        dialog = getattr(self, "_link_inbox_dialog", None)
        if dialog is not None:
            try:
                if dialog.winfo_exists():
                    dialog.lift()
                    dialog.focus_force()
                    return
            except Exception:
                pass
        self._link_inbox_dialog = LinkInboxDialog(self, self._add_link_batch)

    def _add_link_batch(self, urls: list[str]) -> tuple[int, int]:
        """Enqueue a validated batch of URLs; return ``(added, skipped)``."""
        delay = self.settings.schedule_minutes * 60
        priority = self._selected_priority()
        added = 0
        skipped = 0
        for url in urls:
            if self._find_active_duplicate(url) or self.history.find_by_url(url):
                skipped += 1
                continue
            request = self._make_request(url, "", "", "")
            try:
                self.manager.enqueue(request, priority=priority, delay_seconds=delay)
            except Exception:
                log.debug("Could not enqueue inbox link %s", url, exc_info=True)
                skipped += 1
                continue
            added += 1
        if added:
            self._schedule_dynamic_refresh()
        return added, skipped

    def _start_download(self) -> None:
        url = normalize_url(self.url_entry.get())
        if not url:
            self._show_error("err_empty_url")
            return
        if not is_valid_url(url):
            self._show_error("err_invalid_url")
            return
        if self._find_active_duplicate(url):
            self._set_status("err_duplicate", error=True)
            self._toast("info", "status_duplicate_skipped")
            return

        info = self.current_info
        if info and info.url == url and info.is_playlist:
            self._open_playlist_dialog()
            return

        existing = self.history.find_by_url(url)
        if existing:
            answer = messagebox.askyesno(
                translate(self.settings.language, "history_duplicate_title"),
                translate(self.settings.language, "history_duplicate_confirm"),
                parent=self,
            )
            if not answer:
                self._set_status("status_duplicate_skipped")
                return

        title = info.title if info and info.url == url else ""
        platform = info.platform if info and info.url == url else ""
        thumbnail = info.thumbnail_path if info and info.url == url else ""
        request = self._make_request(url, title, platform, thumbnail)
        delay = self.settings.schedule_minutes * 60
        self.manager.enqueue(request, priority=self._selected_priority(), delay_seconds=delay)
        if delay:
            self._set_status("state_scheduled")
        else:
            self._set_status("status_added", count=1)
            self._toast("info", "toast_added")

    def _open_playlist_dialog(self) -> None:
        info = self.current_info
        if not info or not info.is_playlist:
            return
        PlaylistDialog(self, info, self._enqueue_playlist_entries)

    def _enqueue_playlist_entries(self, entries: list[MediaEntry]) -> None:
        if not entries:
            self._show_error("err_choose_items")
            return
        info = self.current_info
        platform = info.platform if info else ""
        delay = self.settings.schedule_minutes * 60
        added = 0
        skipped = 0
        for entry in entries:
            if self._find_active_duplicate(entry.url) or self.history.find_by_url(entry.url):
                skipped += 1
                continue
            request = self._make_request(entry.url, entry.title, platform, "")
            self.manager.enqueue(request, priority=self._selected_priority(), delay_seconds=delay)
            added += 1
        if skipped:
            self._set_status("status_added_skipped", count=added, skipped=skipped)
        elif delay:
            self._set_status("state_scheduled")
        else:
            self._set_status("status_added", count=added)
        if added:
            self._toast("info", "toast_added")

    # ==================================================================
    # Mini mode
    # ==================================================================
    def _open_mini_mode(self) -> None:
        win = getattr(self, "_mini_window", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    return
            except Exception:
                pass
        win = ctk.CTkToplevel(self)
        win.title(self.T("mini_mode_title"))
        win.geometry("330x270")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self._close_mini_mode(w))
        ctk.CTkLabel(
            win, text=self.T("mini_mode_title"),
            font=self.f_h2, anchor=self.text_anchor,
        ).pack(fill="x", padx=14, pady=(12, 6))
        host = ctk.CTkScrollableFrame(win, fg_color="transparent")
        host.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._mini_window = win
        self._mini_host = host
        self._refresh_mini_mode()
        self._mini_job = self.after(700, self._tick_mini_mode)

    def _tick_mini_mode(self) -> None:
        if not getattr(self, "_alive", False):
            return
        win = getattr(self, "_mini_window", None)
        if win is None:
            self._mini_job = None
            return
        try:
            if not win.winfo_exists():
                self._mini_window = None
                self._mini_job = None
                return
        except Exception:
            self._mini_window = None
            self._mini_job = None
            return
        self._refresh_mini_mode()
        self._mini_job = self.after(700, self._tick_mini_mode)

    def _close_mini_mode(self, window=None) -> None:
        job = getattr(self, "_mini_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._mini_job = None
        target = window or getattr(self, "_mini_window", None)
        if target is not None:
            try:
                target.destroy()
            except Exception:
                pass
        self._mini_window = None
        self._mini_host = None

    def _refresh_mini_mode(self) -> None:
        host = getattr(self, "_mini_host", None)
        if host is None:
            return
        for child in host.winfo_children():
            child.destroy()
        active = [
            (task_id, card) for task_id, card in self.task_cards.items()
            if card.snapshot.get("status")
            in ("pending", "scheduled", "downloading", "paused", "processing")
        ]
        if not active:
            ctk.CTkLabel(
                host, text=self.T("mini_mode_empty"), font=self.f_small,
                text_color=MUTED, anchor=self.text_anchor,
            ).pack(pady=30)
            return
        for _task_id, card in active[:14]:
            snap = card.snapshot
            row = ctk.CTkFrame(host, fg_color=SOFT_BUTTON, corner_radius=8)
            row.pack(fill="x", pady=3)
            title = str(snap.get("title") or "—")
            ctk.CTkLabel(
                row,
                text=(title[:34] + "…") if len(title) > 35 else title,
                font=self.f_small, anchor=self.text_anchor,
            ).pack(fill="x", padx=9, pady=(7, 0))
            bar = ctk.CTkProgressBar(row, height=6, corner_radius=3, progress_color=ACCENT)
            bar.pack(fill="x", padx=9, pady=5)
            try:
                bar.set(float(snap.get("progress") or 0) / 100.0)
            except Exception:
                bar.set(0)

    # ==================================================================
    # Auto shutdown
    # ==================================================================
    def _on_all_complete(self) -> None:
        """Called from the manager thread when the last download finishes."""
        if not getattr(self, "_alive", False):
            return
        try:
            self.after(0, self._handle_all_complete)
        except Exception:
            pass

    def _handle_all_complete(self) -> None:
        if not bool(getattr(self.settings, "auto_shutdown", False)):
            return
        self._push_notification("info", "auto_shutdown_toast")
        self._offer_auto_shutdown()

    def _offer_auto_shutdown(self, seconds: int = 30) -> None:
        existing = getattr(self, "_shutdown_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    return
            except Exception:
                pass
        window = ctk.CTkToplevel(self)
        window.title(self.T("auto_shutdown_title"))
        window.resizable(False, False)
        window.transient(self)
        window.attributes("-topmost", True)
        window.geometry(f"420x170+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 120}")
        label = ctk.CTkLabel(
            window,
            text=self.T("auto_shutdown_message", seconds=seconds),
            font=self.f_body,
            wraplength=380,
            justify="center",
        )
        label.pack(padx=20, pady=(26, 14))
        ctk.CTkButton(
            window,
            text=self.T("auto_shutdown_cancel"),
            font=self.f_small_bold,
            fg_color=DANGER,
            hover_color=DANGER,
            command=lambda w=window: self._cancel_auto_shutdown(w),
        ).pack(pady=(0, 18))
        self._shutdown_dialog = window
        self._shutdown_job = None

        def tick(remaining: int) -> None:
            if not self._alive:
                return
            try:
                if not window.winfo_exists():
                    return
                label.configure(
                    text=self.T("auto_shutdown_message", seconds=max(0, remaining))
                )
            except Exception:
                return
            if remaining <= 0:
                self._do_shutdown(window)
                return
            self._shutdown_job = self.after(1000, lambda: tick(remaining - 1))

        tick(seconds)

    def _cancel_auto_shutdown(self, window) -> None:
        job = getattr(self, "_shutdown_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._shutdown_job = None
        try:
            window.destroy()
        except Exception:
            pass
        self._shutdown_dialog = None

    def _do_shutdown(self, window) -> None:
        try:
            window.destroy()
        except Exception:
            pass
        self._shutdown_dialog = None
        self._shutdown_job = None
        try:
            if os.name == "nt":
                subprocess.Popen(["shutdown", "/s", "/t", "0", "/f"])
            else:
                subprocess.Popen(["shutdown", "-h", "now"])
        except Exception:
            log.debug("Could not start system shutdown", exc_info=True)

    # ==================================================================
    # Queue callbacks
    # ==================================================================
    def _on_manager_event(self, name: str, payload: dict) -> None:
        self.events.put((name, payload))

    def _poll_events(self) -> None:
        if not self._alive:
            return
        try:
            for _ in range(300):
                name, payload = self.events.get_nowait()
                self._handle_event(name, payload)
        except queue.Empty:
            pass
        except Exception:  # pragma: no cover - keep the UI alive
            log.exception("Event handling failed")
        # Drain media-tool results on the main thread (workers enqueue them).
        try:
            while True:
                tool, ok, output, detail = self.tool_results.get_nowait()
                self._tool_finished(tool, ok, output, detail)
        except queue.Empty:
            pass
        except Exception:  # pragma: no cover - keep the UI alive
            log.exception("Media-tool result handling failed")
        finally:
            if self._alive:
                self._poll_job = self.after(100, self._poll_events)

    def _handle_event(self, name: str, payload) -> None:
        if name == "info_loaded":
            self._on_info_loaded(payload)  # type: ignore[arg-type]
            return
        if name == "info_error":
            self._on_info_error(payload)  # type: ignore[arg-type]
            return
        if name == "update_result":
            self._on_update_result(payload)  # type: ignore[arg-type]
            return
        if not isinstance(payload, dict):
            return

        task_id = payload.get("id", "")
        if name == "added":
            self._add_task_card(payload)
        else:
            card = self.task_cards.get(task_id)
            if card:
                card.update_snapshot(payload)
        self._update_dynamic_stats()
        self._update_nav_badge()
        if name in ("added", "completed", "failed", "cancelled", "paused", "resumed", "started"):
            self._schedule_dynamic_refresh()

        if name == "completed":
            self._record_history(payload)
            self.failures.remove_by_url((payload.get("request") or {}).get("url", ""))
            self._update_failed_badge()
            title = str(payload.get("title", ""))
            self._set_status("status_completed", title=title)
            self._push_notification("success", "toast_completed", title=title[:42])
            self._update_nav_badge()
        elif name == "failed":
            key = payload.get("error_key") or "err_generic"
            self._record_failure(payload)
            self._set_status(key, error=True)
            self._push_notification("error", "toast_failed", reason=translate(self.settings.language, key))
            self._maybe_auto_retry(payload)
            self._update_nav_badge()
        elif name == "cancelled":
            self._set_status("status_cancelled")
            self._push_notification("info", "toast_cancelled")
            self._update_nav_badge()

    def _add_task_card(self, snapshot: dict) -> None:
        self.queue_empty.grid_remove()
        card = TaskCard(self.queue_scroll, snapshot, self)
        card.pack(fill="x", padx=6, pady=4)
        self.task_cards[snapshot["id"]] = card
        self._update_queue_count()

    def _update_queue_count(self) -> None:
        self.queue_count.configure(text=str(len(self.task_cards)))
        if self.task_cards:
            self.queue_empty.grid_remove()
        else:
            self.queue_empty.grid()
        self._update_dynamic_stats()

    def _update_dynamic_stats(self) -> None:
        """Refresh the live counters shown in the media library summary."""
        active_states = ("pending", "scheduled", "downloading", "processing")
        active = 0
        speed = 0.0
        for card in self.task_cards.values():
            snapshot = card.snapshot
            status = snapshot.get("status")
            if status in active_states:
                active += 1
            if status == "downloading":
                try:
                    speed += float(snapshot.get("speed") or 0)
                except (TypeError, ValueError):
                    pass
        try:
            self.stat_active_value.configure(text=str(active))
            self.stat_speed_value.configure(text=format_speed(speed) if speed else "—")
        except Exception:  # labels may not exist yet during rebuilds
            pass

    def toggle_pause(self, task_id: str) -> None:
        card = self.task_cards.get(task_id)
        if not card:
            return
        if card.snapshot.get("status") == "paused":
            self.manager.resume(task_id)
            self._set_status("status_resumed")
        else:
            self.manager.pause(task_id)
            self._set_status("status_paused")

    def cancel_task(self, task_id: str) -> None:
        self.manager.cancel(task_id)

    def retry_task(self, task_id: str) -> None:
        card = self.task_cards.get(task_id)
        url = ((card.snapshot.get("request") or {}).get("url") if card else "") or ""
        new_task = self.manager.retry(task_id)
        if new_task:
            if url:
                self.failures.remove_by_url(url)
                self._update_failed_badge()
            self._set_status("status_added", count=1)

    # ==================================================================
    # Failed Downloads Center
    # ==================================================================
    @staticmethod
    def _request_from_dict(data: dict) -> DownloadRequest:
        return DownloadRequest(
            **{k: v for k, v in (data or {}).items() if k in DownloadRequest.__dataclass_fields__}
        )

    def _update_failed_badge(self) -> None:
        label = getattr(self, "failed_count_label", None)
        if label is None:
            return
        try:
            count = len(self.failures.entries())
        except Exception:
            count = 0
        label.configure(text=str(count) if count else "")
        try:
            self.failed_center_btn.configure(
                fg_color=DANGER if count else SOFT_BUTTON,
                hover_color=DANGER if count else SOFT_HOVER,
                text_color="#FFFFFF" if count else SOFT_TEXT,
            )
        except Exception:
            pass

    def _open_failed_center(self) -> None:
        dialog = getattr(self, "_failed_center_dialog", None)
        if dialog is not None:
            try:
                if dialog.winfo_exists():
                    dialog._refresh()
                    dialog.lift()
                    dialog.focus_force()
                    return
            except Exception:
                pass
        self._failed_center_dialog = FailedCenterDialog(self)

    def _record_failure(self, payload: dict) -> None:
        request = payload.get("request") or {}
        url = request.get("url") or ""
        if not url:
            return
        try:
            self.failures.add(
                title=str(payload.get("title") or ""),
                url=url,
                error_key=str(payload.get("error_key") or "err_generic"),
                error_detail=str(payload.get("error_detail") or ""),
                request=request,
                attempt=int(payload.get("attempt") or 1),
                platform=str(request.get("platform") or payload.get("platform") or ""),
                priority=int(payload.get("priority") or 0),
            )
            self._update_failed_badge()
        except Exception:
            log.debug("Could not record failure", exc_info=True)

    def _maybe_auto_retry(self, payload: dict) -> None:
        if not bool(getattr(self.settings, "auto_retry_failed", False)):
            return
        key = str(payload.get("error_key") or "err_generic")
        if key not in TRANSIENT_ERROR_KEYS:
            return
        attempt = int(payload.get("attempt") or 1)
        if attempt > len(AUTO_RETRY_DELAYS):
            return
        request = payload.get("request") or {}
        if not request.get("url"):
            return
        try:
            self.manager.enqueue(
                self._request_from_dict(request),
                priority=int(payload.get("priority") or 0),
                delay_seconds=AUTO_RETRY_DELAYS[attempt - 1],
                attempt=attempt + 1,
            )
            self._toast("info", "toast_auto_retry", count=attempt + 1)
        except Exception:
            log.debug("Could not auto-retry failure", exc_info=True)

    def retry_failure(self, entry_id: str, quiet: bool = False) -> bool:
        entry = next(
            (item for item in self.failures.entries() if item.get("id") == entry_id), None
        )
        if not entry:
            return False
        request = entry.get("request") or {}
        if not request.get("url"):
            self.failures.remove(entry_id)
            self._update_failed_badge()
            return False
        try:
            self.manager.enqueue(
                self._request_from_dict(request),
                priority=int(entry.get("priority") or 0),
                attempt=int(entry.get("attempt") or 1) + 1,
            )
        except Exception:
            log.debug("Could not retry failure", exc_info=True)
            return False
        self.failures.remove(entry_id)
        self._update_failed_badge()
        self._schedule_dynamic_refresh()
        if not quiet:
            self._toast("info", "failed_center_retrying")
        return True

    def retry_all_failures(self) -> int:
        return sum(
            1 for entry in self.failures.entries()
            if self.retry_failure(str(entry.get("id") or ""), quiet=True)
        )

    def remove_failure(self, entry_id: str) -> None:
        self.failures.remove(entry_id)
        self._update_failed_badge()
        self._toast("info", "toast_failure_removed")

    def clear_failures(self) -> None:
        self.failures.clear()
        self._update_failed_badge()

    def open_task_file(self, task_id: str) -> None:
        card = self.task_cards.get(task_id)
        if not card:
            return
        path = card.snapshot.get("filepath")
        if not path:
            return
        if not reveal_in_folder(path):
            self._set_status("history_open_failed", error=True)

    def remove_task_card(self, task_id: str) -> None:
        card = self.task_cards.pop(task_id, None)
        if card:
            card.destroy()
        self._update_queue_count()

    def _clear_finished_tasks(self) -> None:
        finished = [
            task_id
            for task_id, card in self.task_cards.items()
            if card.snapshot.get("status") in ("completed", "error", "cancelled")
        ]
        for task_id in finished:
            self.remove_task_card(task_id)
        self._set_status("status_cleared_finished")

    # ==================================================================
    # History
    # ==================================================================
    # -- SHA-256 integrity ---------------------------------------------
    _HASH_TOASTS = {
        "verified": ("success", "hash_toast_verified"),
        "match": ("success", "hash_toast_match"),
        "mismatch": ("error", "hash_toast_mismatch"),
        "missing": ("error", "hash_toast_missing"),
        "error": ("error", "hash_toast_error"),
    }

    def hash_badge(self, entry: dict) -> tuple[str, tuple[str, str]]:
        """Return the short integrity label and its colour for a history entry."""
        status = entry.get("hash_status") or "unchecked"
        if status == "match":
            return self.T("hash_match"), SUCCESS
        if status == "mismatch":
            return self.T("hash_mismatch"), WARN
        if status == "verified":
            return self.T("hash_verified"), SUCCESS
        if status == "pending":
            return self.T("hash_pending"), MUTED
        if status == "missing":
            return self.T("hash_missing"), WARN
        if status == "error":
            return self.T("hash_error"), WARN
        return self.T("hash_unchecked"), MUTED

    def _hash_ui_refresh(self) -> None:
        if self._alive:
            try:
                self.after(0, self._refresh_history)
            except Exception:
                pass

    def _notify_hash_result(self, status: str) -> None:
        kind, key = self._HASH_TOASTS.get(status, ("info", "hash_toast_verified"))
        self._toast(kind, key)

    def verify_history_hash(self, entry: dict, toast: bool = True) -> None:
        """Compute SHA-256 for *entry* on a worker and persist the result."""
        entry_id = str(entry.get("id") or "")
        filepath = str(entry.get("filepath") or "")
        expected = normalize_sha256(entry.get("hash_expected") or "")
        if not entry_id:
            return
        if not filepath or not Path(filepath).is_file():
            self.history.update_hash(entry_id, status="missing")
            entry["hash_status"] = "missing"
            self._hash_ui_refresh()
            if toast:
                self._notify_hash_result("missing")
            return

        def worker() -> None:
            try:
                digest = sha256_file(filepath)
            except (OSError, ValueError):
                self.history.update_hash(entry_id, status="error")
                status = "error"
            else:
                self.history.update_hash(entry_id, digest=digest)
                status = (
                    "match" if expected and digest == expected
                    else "mismatch" if expected
                    else "verified"
                )
                entry["sha256"] = digest
            entry["hash_status"] = status
            self._hash_ui_refresh()
            if toast and self._alive:
                try:
                    self.after(0, lambda s=status: self._notify_hash_result(s))
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _set_expected_history_hash(self, entry: dict) -> None:
        tokens = self.palette_tokens
        win = ctk.CTkToplevel(self)
        self.hash_dialog = win
        win.title(self.T("hash_dialog_title"))
        win.geometry("470x250")
        win.resizable(False, False)
        win.configure(fg_color=tokens["bg"])
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            win, text=self.T("hash_dialog_title"), font=self.f_h2,
            anchor=self.text_anchor, justify=self.text_justify,
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            win, text=self.T("hash_dialog_hint"), font=self.f_small,
            text_color=tokens["muted"], anchor=self.text_anchor,
            justify=self.text_justify, wraplength=430,
        ).grid(row=1, column=0, sticky="ew", padx=18)

        hash_var = tk.StringVar(value=str(entry.get("hash_expected") or ""))
        hash_entry = ctk.CTkEntry(
            win, textvariable=hash_var, height=36, font=self.f_small,
            corner_radius=10,
        )
        hash_entry.grid(row=2, column=0, sticky="ew", padx=18, pady=12)
        hash_entry.focus_set()
        ctk.CTkButton(
            win,
            text=self.T("hash_dialog_save"),
            height=36,
            corner_radius=10,
            font=self.f_small,
            fg_color=tokens["accent"],
            hover_color=tokens["accent_hover"],
            command=lambda: self._save_expected_history_hash(
                entry, hash_var.get(), win
            ),
        ).grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 16))
        win.after(80, lambda: self._centre_dialog(win, 470, 250))

    def _save_expected_history_hash(
        self, entry: dict, raw: str, win: ctk.CTkToplevel
    ) -> None:
        digest = normalize_sha256(raw)
        if not digest:
            self._toast("error", "hash_invalid")
            return
        self.history.update_hash(str(entry.get("id") or ""), expected=digest)
        entry["hash_expected"] = digest
        try:
            win.destroy()
        except Exception:
            pass
        self._refresh_history()
        self.verify_history_hash(entry)

    def _record_history(self, snapshot: dict) -> None:
        """Persist a finished download without blocking the UI thread.

        HistoryStore is guarded by an RLock, so the write can safely happen on
        a worker.  The UI refresh is marshalled back through ``after``.
        """
        request = snapshot.get("request") or {}
        data = dict(
            title=snapshot.get("title", ""),
            url=request.get("url", ""),
            filepath=snapshot.get("filepath", ""),
            size=snapshot.get("size", 0),
            platform=snapshot.get("platform", ""),
            thumbnail=request.get("thumbnail_path", ""),
        )

        def worker() -> None:
            try:
                added = self.history.add(**data)
            except Exception:
                log.exception("Could not record history")
                return
            entry_id = str(added.get("id") or "")
            auto_verify = bool(getattr(self.settings, "verify_hashes", True))
            if auto_verify and entry_id:
                self.history.update_hash(entry_id, status="pending")
            self._hash_ui_refresh()

            if not auto_verify or not entry_id:
                return
            filepath = str(data.get("filepath") or "")
            if not filepath or not Path(filepath).is_file():
                self.history.update_hash(entry_id, status="missing")
            else:
                try:
                    digest = sha256_file(filepath)
                except (OSError, ValueError):
                    log.warning("SHA-256 failed for %s", filepath, exc_info=True)
                    self.history.update_hash(entry_id, status="error")
                else:
                    self.history.update_hash(entry_id, digest=digest)
            self._hash_ui_refresh()

        threading.Thread(target=worker, daemon=True).start()

    def _filtered_history(self) -> tuple[list[dict], list[dict]]:
        """Return ``(all_entries, visible_entries)`` after every library filter."""
        entries = self.history.entries()
        query = self.history_query.strip().lower()
        kind = self.history_kind
        visible: list[dict] = []
        for entry in entries:
            if kind != "all" and media_kind(entry.get("filepath") or "") != kind:
                continue
            if self.favorites_only and not entry.get("favorite"):
                continue
            if query:
                haystack = " ".join(
                    str(entry.get(key, "")) for key in ("title", "url", "platform")
                )
                haystack += " " + " ".join(str(tag) for tag in (entry.get("tags") or []))
                if query not in haystack.lower():
                    continue
            visible.append(entry)
        return entries, self._sort_history_entries(visible)

    def _refresh_history(self) -> None:
        # Rebuild KPI cards from the same filtered/sorted set used by the grid.
        _, all_entries = self._filtered_history()

        # Date grouping
        from datetime import datetime, date
        today_str = date.today().isoformat()
        entries_by_group: dict[str, list[dict]] = {"Today": [], "Yesterday": [], "Earlier": []}
        for entry in all_entries:
            ts = entry.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts) if ts else None
                if dt:
                    if dt.date().isoformat() == today_str:
                        group = "Today"
                    elif (date.today() - dt.date()).days == 1:
                        group = "Yesterday"
                    else:
                        group = "Earlier"
                else:
                    group = "Earlier"
            except Exception:
                group = "Earlier"
            entries_by_group[group].append(entry)

        # Update KPI cards
        total_count = len(all_entries)
        total_size = sum(int(e.get("size") or 0) for e in all_entries)
        # "last" = most recent entry across all groups
        all_timestamps = [e.get("timestamp", "") for e in all_entries if e.get("timestamp")]
        if all_timestamps:
            latest = max(all_timestamps, key=lambda t: datetime.fromisoformat(t) if datetime.fromisoformat(t) else datetime.min)
            last_date = str(datetime.fromisoformat(latest).isoformat()[:16].replace("T", " "))
        else:
            last_date = "—"
        active_count = sum(1 for e in all_entries if e.get("status") in ("pending", "scheduled", "downloading", "processing"))
        downloading_speed = sum(float(e.get("speed") or 0) for e in all_entries if e.get("status") == "downloading")

        self.stat_count_value.configure(text=str(total_count))
        self.stat_size_value.configure(text=format_bytes(total_size) if total_size else "—")
        self.stat_last_value.configure(text=self.S(last_date or "—"))
        self.stat_active_value.configure(text=str(active_count))
        self.stat_speed_value.configure(text=format_speed(downloading_speed) if downloading_speed else "—")

        # Update shown label
        try:
            self.history_shown_label.configure(
                text=self.T("history_shown", shown=len(all_entries), total=len(self.history.entries()))
            )
        except Exception:
            pass

        # Clear old rows
        for row in self.history_rows.values():
            row.destroy()
        self.history_rows.clear()

        # Render rows in the current view
        view = getattr(self, "library_view", "grid")
        if view == "grid":
            self._render_history_grid(all_entries)
        else:
            self._render_history_list(all_entries)

        # Show empty state if nothing visible
        if not all_entries:
            self.history_empty_title.configure(text=self.T("history_empty_title"))
            self.history_empty_hint.configure(text=self.T("history_empty_hint"))
            self.history_empty_action.configure(command=self._empty_state_action)
            self.history_empty.grid()
            self.history_scroll.grid_remove()
        else:
            self.history_empty.grid_remove()
            self.history_scroll.grid(row=3, column=0, sticky="nsew")

    def _render_history_grid(self, entries: list[dict]) -> None:
        # rebuild grid cards in the scroll frame
        # clear existing
        for child in self.history_scroll.winfo_children():
            if child != self.history_empty:
                child.destroy()
        # grid cards
        for index, entry in enumerate(entries):
            card = MediaCard(self.history_scroll, entry, self)
            self.history_rows[entry.get("id", "")] = card
        self._history_columns = 0
        self._apply_history_columns(force=True)

    def _render_history_list(self, entries: list[dict]) -> None:
        # rebuild list rows
        for child in self.history_scroll.winfo_children():
            if child != self.history_empty:
                child.destroy()
        for entry in entries:
            row = HistoryRow(self.history_scroll, entry, self)
            row.pack(fill="x", padx=6, pady=4)
            self.history_rows[entry.get("id", "")] = row

        # show/hide empty state
        if not entries:
            self.history_empty.grid()
            self.history_scroll.grid_remove()
        else:
            self.history_empty.grid_remove()
            self.history_scroll.grid(row=3, column=0, sticky="nsew")

    def _update_history_stats(self, entries: list[dict]) -> None:
        total_size = sum(int(entry.get("size") or 0) for entry in entries)
        self.stat_count_value.configure(text=str(len(entries)))
        self.stat_size_value.configure(text=format_bytes(total_size) if entries else "—")
        if entries:
            stamp = str(entries[0].get("timestamp", ""))[:16].replace("T", " ")
            self.stat_last_value.configure(text=self.S(stamp or "—"))
        else:
            self.stat_last_value.configure(text="—")
        # active + speed
        active = sum(1 for e in entries if e.get("status") in ("pending", "scheduled", "downloading", "processing"))
        speed = sum(float(e.get("speed") or 0) for e in entries if e.get("status") == "downloading")
        self.stat_active_value.configure(text=str(active))
        self.stat_speed_value.configure(text=format_speed(speed) if speed else "—")
        self._update_dynamic_stats()

    def _on_history_search_changed(self, _event=None) -> None:
        self.history_query = self.history_search_var.get()
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(220, self._finish_history_search)

    def _finish_history_search(self) -> None:
        self._search_job = None
        if self._alive:
            self._refresh_history()

    def _on_history_filter_changed(self, value: str) -> None:
        try:
            self.history_kind = self.history_filter_values[
                self.history_filter_labels.index(value)
            ]
        except (ValueError, AttributeError):
            self.history_kind = "all"
        self._refresh_history()

    def _open_download_dir(self) -> None:
        if not open_path(self.settings.download_dir):
            self._set_status("history_open_failed", error=True)

    def open_history_file(self, entry: dict) -> None:
        filepath = entry.get("filepath", "")
        if filepath and Path(filepath).exists():
            if not reveal_in_folder(filepath):
                self._set_status("history_open_failed", error=True)
        else:
            parent = str(Path(filepath).parent) if filepath else str(self.settings.download_dir)
            if not open_path(parent):
                self._set_status("history_open_failed", error=True)

    def remove_history_entry(self, entry: dict) -> None:
        self.history.remove(entry.get("id", ""))
        self._refresh_history()

    def _clear_history(self) -> None:
        answer = messagebox.askyesno(
            translate(self.settings.language, "history_clear"),
            translate(self.settings.language, "history_clear_confirm"),
            parent=self,
        )
        if not answer:
            return
        self.history.clear()
        self._refresh_history()
        self._set_status("status_cleared")

    # ==================================================================
    # Settings callbacks
    # ==================================================================
    def _on_concurrency_changed(self, value: str) -> None:
        try:
            self.settings.max_concurrent = max(1, min(4, int(value)))
        except ValueError:
            return
        self.config.save(self.settings)
        self._set_status("status_settings_saved")

    def _on_bitrate_changed(self, value: str) -> None:
        bitrate = value.split()[0]
        if bitrate in ("320", "256", "192", "128"):
            self.settings.audio_quality = bitrate
            self.config.save(self.settings)
            self._refresh_quality_menu(preserve=False)
            self._set_status("status_settings_saved")

    def _on_switches_changed(self) -> None:
        self.settings.embed_metadata = bool(self.embed_meta_switch.get())
        self.settings.embed_thumbnail = bool(self.embed_thumb_switch.get())
        self.config.save(self.settings)
        self._set_status("status_settings_saved")

    def _on_pro_switches_changed(self) -> None:
        for attr, switch in getattr(self, "pro_switches", {}).items():
            setattr(self.settings, attr, bool(switch.get()))
        self.config.save(self.settings)
        self._set_status("status_settings_saved")
        self._schedule_dynamic_refresh()

    def _on_schedule_changed(self, value: str) -> None:
        try:
            index = self.schedule_values.index(value)
        except ValueError:
            index = 0
        self.settings.schedule_minutes = self.schedule_options[index]
        self.config.save(self.settings)
        self._set_status("status_settings_saved")

    def _on_speed_limit_changed(self, value: str) -> None:
        try:
            index = self.speed_labels.index(value)
        except ValueError:
            index = 0
        self.settings.speed_limit_kbps = self.speed_values[index]
        self.config.save(self.settings)
        self._set_status("status_settings_saved")

    def _on_container_changed(self, value: str) -> None:
        container = value.strip().lower()
        if container not in self.container_values:
            return
        self.settings.video_container = container
        self.config.save(self.settings)
        self._refresh_quality_menu(preserve=True)
        self._set_status("status_settings_saved")

    def _on_subtitle_switch_changed(self) -> None:
        self.settings.embed_subtitles = bool(self.subtitle_switch.get())
        self.config.save(self.settings)
        self._set_status("status_settings_saved")

    def _on_auto_clipboard_changed(self) -> None:
        self.settings.auto_clipboard = bool(self.clipboard_switch.get())
        self.config.save(self.settings)
        self._start_clipboard_watch()
        self._set_status("status_settings_saved")

    def _on_network_entries_changed(self, _event=None) -> None:
        """Persist the free-text advanced fields when they lose focus."""
        try:
            self.settings.proxy = self.proxy_var.get().strip()
            self.settings.subtitle_langs = self.subtitle_var.get().strip() or "ar,en"
            self.settings.update_url = self.update_url_var.get().strip()
        except Exception:
            return
        self.settings = self.settings.sanitized()
        self.config.save(self.settings)
        try:
            self.proxy_var.set(self.settings.proxy)
            self.subtitle_var.set(self.settings.subtitle_langs)
            self.update_url_var.set(self.settings.update_url)
        except Exception:
            pass
        self._set_status("status_settings_saved")

    # ------------------------------------------------------------------
    # Update check (read-only: opens the download page, never patches).
    # ------------------------------------------------------------------
    def _check_updates(self) -> None:
        self._on_network_entries_changed()
        url = self.settings.update_url
        if not url:
            self._set_status("status_update_unset", error=True)
            return
        try:
            self.check_updates_btn.configure(state="disabled")
        except Exception:
            pass
        self._manual_update = True
        self._set_status("status_update_checking")
        threading.Thread(
            target=self._update_worker, args=(url,), name="update-check", daemon=True
        ).start()

    def _auto_check_updates(self) -> None:
        if not self._alive:
            return
        url = self.settings.update_url.strip()
        if not url:
            return
        self._manual_update = False
        threading.Thread(
            target=self._update_worker, args=(url,), name="update-check-auto", daemon=True
        ).start()

    def _update_worker(self, url: str) -> None:
        try:
            result = check_for_update(url)
        except Exception as exc:  # defensive: never let the thread die loudly
            log.warning("Update worker failed: %s", exc)
            result = None
        if result is not None:
            self.events.put(("update_result", result))

    def _on_update_result(self, result) -> None:
        manual = self._manual_update
        self._manual_update = False
        try:
            self.check_updates_btn.configure(state="normal")
        except Exception:
            pass
        status = getattr(result, "status", "error")
        if status == "unset":
            if manual:
                self._set_status("status_update_unset", error=True)
        elif status == "error":
            if manual:
                self._set_status("status_update_failed", error=True)
        elif status == "latest":
            if manual:
                self._set_status("status_update_latest", version=result.version)
        elif status == "available":
            self._set_status("status_update_available", version=result.version)
            self._toast("info", "status_update_available", version=result.version)
            url = getattr(result, "url", "")
            if manual and url:
                answer = messagebox.askyesno(
                    translate(self.settings.language, "update_available_title"),
                    translate(
                        self.settings.language, "update_open_confirm",
                        version=result.version,
                    ),
                    parent=self,
                )
                if answer:
                    try:
                        webbrowser.open(url)
                    except Exception:
                        self._set_status("status_update_failed", error=True)

    def _open_config_folder(self) -> None:
        open_path(APP_DIR)

    # ==================================================================
    # Status / errors
    # ==================================================================
    def _set_status(self, key: str = "status_ready", error: bool = False, **kwargs) -> None:
        self._status_state = (key, kwargs, error)
        text = translate(self.settings.language, key, **kwargs)
        try:
            self.status_label.configure(text=self.S(text))
        except Exception:
            pass
        # Toasts are emitted explicitly by _handle_event / _push_notification,
        # so every status change does not spam the screen.

    def _show_error(self, key: str) -> None:
        self._set_status(key, error=True)
        messagebox.showerror(
            translate(self.settings.language, "error_title"),
            translate(self.settings.language, key),
            parent=self,
        )

    # ==================================================================
    # Lifecycle
    # ==================================================================
    def _on_close(self) -> None:
        if self.manager.has_active():
            answer = messagebox.askyesno(
                translate(self.settings.language, "confirm_exit_title"),
                translate(self.settings.language, "confirm_exit"),
                parent=self,
            )
            if not answer:
                return
        self._alive = False
        for job in (
            self._page_job,
            self._nav_job,
            self._thumb_job,
            self._rebuild_job,
            self._clipboard_job,
            self._search_job,
            self._update_job,
            self._dyn_job,
            self._status_job,
            self._mini_job,
            self._shutdown_job,
            self._history_layout_job,
            self._resize_job,
        ):
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        try:
            self.settings.window_geometry = self.geometry()
            self.config.save(self.settings)
        except Exception:
            pass
        self.manager.shutdown()
        self.destroy()


def run_app() -> None:
    """Entry point used by main.py."""
    try:
        ctk.ThemeManager.theme["CTkFont"]["family"] = "Segoe UI"
    except Exception:
        pass
    app = MediaDownloaderApp()
    app.mainloop()
