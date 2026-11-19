"""Reusable CustomTkinter widgets (download card, media cards, toasts).

The module also provides the small building blocks used by the refreshed UI:
tooltips, a shimmering skeleton placeholder and 16:9 media cards with a
gradient caption overlay.
"""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageOps

from app.i18n import is_rtl
from app.ui.theme import DEFAULT_PALETTE, tokens as palette_tokens
from app.utils.helpers import (
    format_bytes,
    format_clock,
    format_eta,
    format_speed,
    media_kind,
    truncate,
)

_TOKENS = palette_tokens(DEFAULT_PALETTE)

CARD_BG: tuple[str, str] = _TOKENS["row_bg"]
CARD_BORDER: tuple[str, str] = _TOKENS["row_border"]
CARD_HOVER: tuple[str, str] = _TOKENS["row_hover"]
CARD_SOFT: tuple[str, str] = ("#F9FAFB", "#121216")  # default (light, dark)

# Token globals - set by apply_palette() at runtime
CARD_SHADOW: tuple[str, str] = ("#000000", "#14201A")
CARD_ELEVATED: tuple[str, str] = ("#F5F5F5", "#202025")
SHIMMER: tuple[str, str] = _TOKENS["shimmer"]
SOFT_BUTTON: tuple[str, str] = _TOKENS["soft_button"]
SOFT_HOVER: tuple[str, str] = _TOKENS["soft_hover"]
SOFT_TEXT: tuple[str, str] = _TOKENS["soft_text"]
ACCENT: tuple[str, str] = _TOKENS["accent"]
ACCENT_HOVER: tuple[str, str] = _TOKENS["accent_hover"]
ACCENT_SOFT: tuple[str, str] = _TOKENS["accent_soft"]
DANGER: tuple[str, str] = _TOKENS["danger"]
MUTED: tuple[str, str] = _TOKENS["muted"]

STATUS_COLORS: dict[str, tuple[str, str]] = {}
PROGRESS_COLORS: dict[str, tuple[str, str]] = {}

KIND_SYMBOLS = {
    "video": "🎬",
    "audio": "🎵",
    "image": "🖼",
    "other": "📄",
}


def apply_palette(key: str) -> None:
    """Refresh every module-level colour used by the reusable widgets."""
    global CARD_BG, CARD_BORDER, CARD_HOVER, CARD_SOFT, SHIMMER
    global CARD_SHADOW, CARD_ELEVATED, SOFT_BUTTON, SOFT_HOVER, SOFT_TEXT, ACCENT, ACCENT_HOVER, ACCENT_SOFT
    global DANGER, MUTED

    tokens = palette_tokens(key)
    CARD_BG = tokens["row_bg"]
    CARD_BORDER = tokens["row_border"]
    CARD_HOVER = tokens["row_hover"]
    CARD_SOFT = tokens["card_soft"]
    CARD_SHADOW = tokens["card_shadow"]      # New: enhanced shadow
    CARD_ELEVATED = tokens["card_elevated"] # New: elevated card bg
    SHIMMER = tokens["shimmer"]
    SOFT_BUTTON = tokens["soft_button"]
    SOFT_HOVER = tokens["soft_hover"]
    SOFT_TEXT = tokens["soft_text"]
    ACCENT = tokens["accent"]
    ACCENT_HOVER = tokens["accent_hover"]
    ACCENT_SOFT = tokens["accent_soft"]
    DANGER = tokens["danger"]
    MUTED = tokens["muted"]

    STATUS_COLORS.clear()
    STATUS_COLORS.update(
        {
            "pending": tokens["muted"],
            "scheduled": tokens["muted"],
            "downloading": tokens["accent"],
            "paused": tokens["warn"],
            "processing": tokens["warn"],
            "completed": tokens["success"],
            "error": tokens["danger"],
            "cancelled": tokens["muted"],
        }
    )
    PROGRESS_COLORS.clear()
    PROGRESS_COLORS.update(
        {
            "pending": tokens["row_border"],
            "scheduled": tokens["row_border"],
            "downloading": tokens["accent"],
            "paused": tokens["warn"],
            "processing": tokens["warn"],
            "completed": tokens["success"],
            "error": tokens["danger"],
            "cancelled": tokens["muted"],
        }
    )


apply_palette(DEFAULT_PALETTE)


def ease_out_cubic(t: float) -> float:
    """Smooth deceleration curve used by the small UI animations."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
def with_gradient(
    image: Image.Image,
    size: tuple[int, int],
    *,
    ratio: float = 0.52,
    max_alpha: int = 205,
) -> Image.Image:
    """Fit *image* to *size* and paint a dark bottom gradient for captions."""
    fitted = ImageOps.fit(image.convert("RGB"), size, Image.LANCZOS).convert("RGBA")
    width, height = fitted.size
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    start = int(height * (1.0 - max(0.05, min(0.95, ratio))))
    span = max(1, height - start)
    for y in range(start, height):
        t = (y - start) / span
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, int(max_alpha * (t ** 1.35))))
    return Image.alpha_composite(fitted, overlay).convert("RGB")


def make_image(path: str, size: tuple[int, int], *, gradient: bool = True) -> ctk.CTkImage | None:
    """Load *path* into a CTkImage, returning ``None`` when it cannot be read."""
    if not path:
        return None
    try:
        if not Path(path).exists():
            return None
        image = Image.open(path)
        frame = with_gradient(image, size) if gradient else ImageOps.fit(
            image.convert("RGB"), size, Image.LANCZOS
        )
        return ctk.CTkImage(light_image=frame, dark_image=frame, size=size)
    except Exception:
        return None


def _placeholder_colour(token: tuple[str, str]) -> tuple[str, str]:
    return token


def _app_of(widget):
    """Find the main app from any widget so reusable widgets can share scaling."""
    node = widget
    while node is not None:
        app = getattr(node, "app", None)
        if app is not None and hasattr(app, "_font"):
            return app
        node = getattr(node, "master", None)
    return None


# ---------------------------------------------------------------------------
# Tooltip
# ---------------------------------------------------------------------------
class Tooltip:
    """A lightweight hover tooltip for any Tk widget."""

    def __init__(self, widget, text: str, delay: int = 420) -> None:
        self.widget = widget
        self.text = text
        self.delay = max(0, delay)
        self._job: str | None = None
        self._window: ctk.CTkToplevel | None = None
        try:
            widget.bind("<Enter>", self._schedule, add="+")
            widget.bind("<Leave>", self._hide, add="+")
            widget.bind("<ButtonPress>", self._hide, add="+")
        except Exception:
            pass

    def update_text(self, text: str) -> None:
        self.text = text

    def _schedule(self, _event=None) -> None:
        self._cancel()
        try:
            self._job = self.widget.after(self.delay, self._show)
        except Exception:
            self._job = None

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _show(self) -> None:
        self._job = None
        if not self.text or self._window is not None:
            return
        try:
            if not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + max(8, self.widget.winfo_width() // 2)
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except Exception:
            return
        try:
            window = ctk.CTkToplevel(self.widget)
            window.overrideredirect(True)
            window.attributes("-topmost", True)
            window.configure(fg_color=SOFT_TEXT)
            app = _app_of(self.widget)
            label = ctk.CTkLabel(
                window,
                text=self.text,
                font=app._font(11) if app else ctk.CTkFont(family="Segoe UI", size=11),
                text_color=("#FFFFFF", "#101014"),
                padx=10,
                pady=5,
            )
            label.pack()
            window.update_idletasks()
            width = max(40, window.winfo_reqwidth())
            window.geometry(f"+{max(0, x - width // 2)}+{y}")
            self._window = window
        except Exception:
            self._window = None

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None

    def destroy(self) -> None:
        self._hide()


# ---------------------------------------------------------------------------
# Skeleton
# ---------------------------------------------------------------------------
class SkeletonBox(ctk.CTkFrame):
    """A soft placeholder with an indeterminate shimmer line."""

    def __init__(self, master, width: int, height: int, app, text_key: str = "skeleton_loading") -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            corner_radius=12,
            fg_color=SHIMMER,
            border_width=0,
        )
        self.grid_propagate(False)
        self.pack_propagate(False)
        self.app = app
        self.label = ctk.CTkLabel(
            self,
            text=app.T(text_key),
            font=app.f_small,
            text_color=MUTED,
        )
        self.label.place(relx=0.5, rely=0.44, anchor="center")
        self.bar = ctk.CTkProgressBar(
            self,
            mode="indeterminate",
            height=4,
            corner_radius=2,
            progress_color=ACCENT,
        )
        self.bar.place(relx=0.08, rely=0.82, relwidth=0.84)
        try:
            self.bar.start()
        except Exception:
            pass

    def stop(self) -> None:
        try:
            self.bar.stop()
        except Exception:
            pass

    def destroy(self) -> None:
        self.stop()
        super().destroy()


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------
class AnimatedProgressBar(ctk.CTkProgressBar):
    """Progress bar that eases towards its target instead of jumping."""

    def __init__(self, master, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._shown = 0.0
        self._target = 0.0
        self._job: str | None = None
        self.reduce_motion = False
        self.set(0)

    def animate_to(self, value: float) -> None:
        self._target = max(0.0, min(1.0, float(value)))
        if self.reduce_motion:
            self.set_now(self._target)
            return
        if self._job is None:
            self._tick()

    def set_now(self, value: float) -> None:
        self._cancel()
        self._shown = self._target = max(0.0, min(1.0, float(value)))
        self.set(self._shown)

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _tick(self) -> None:
        if not self.winfo_exists():
            return
        delta = self._target - self._shown
        if abs(delta) < 0.004:
            self._shown = self._target
            self.set(self._shown)
            self._job = None
            return
        self._shown += delta * 0.38
        self.set(max(0.0, min(1.0, self._shown)))
        self._job = self.after(28, self._tick)

    def destroy(self) -> None:
        self._cancel()
        super().destroy()




# ---------------------------------------------------------------------------
# Download task card
# ---------------------------------------------------------------------------
class TaskCard(ctk.CTkFrame):
    """A compact card showing one download and its controls."""

    def __init__(self, master, snapshot: dict, app) -> None:
        super().__init__(
            master,
            corner_radius=14,
            fg_color=CARD_SOFT,      # Softer card background for task cards
            border_width=1,
            border_color=CARD_BORDER,
        )
        self.app = app
        self.task_id = snapshot["id"]
        self.snapshot = snapshot
        self._hover = False
        self._rtl = is_rtl(app.settings.language)
        # Softer card appearance
        self.configure(fg_color=CARD_SOFT)

        thumb_path = str(snapshot.get("thumbnail") or "")
        self._show_thumb = bool(getattr(app.settings, "show_task_thumbnails", True)) and bool(thumb_path)
        if self._show_thumb:
            thumb_column = self._column(0, 3)
            text_column = self._column(1, 3)
            badge_column = self._column(2, 3)
            self.grid_columnconfigure(thumb_column, weight=0)
            self._build_thumbnail(thumb_column, thumb_path)
            self._total_columns = 3
        else:
            text_column = self._column(0, 2)
            badge_column = self._column(1, 2)
            self._total_columns = 2
        self.grid_columnconfigure(text_column, weight=1)
        self.grid_columnconfigure(badge_column, weight=0)

        self.title_label = ctk.CTkLabel(
            self,
            text="",
            font=app.f_body_bold,
            anchor=app.text_anchor,
            justify=app.text_justify,
        )
        self.title_label.grid(
            row=0, column=text_column, sticky="ew",
            padx=self._pad(14, 8), pady=(10, 2),
        )

        self.badge = ctk.CTkLabel(
            self,
            text="",
            font=app.f_small_bold,
            corner_radius=8,
            width=88,
            height=24,
            text_color="#FFFFFF",
        )
        self.badge.grid(
            row=0, column=badge_column, sticky=self._end_sticky,
            padx=self._pad(0, 12), pady=(10, 2),
        )

        self.bar = AnimatedProgressBar(self, height=8, corner_radius=4)
        self.bar.reduce_motion = bool(app.settings.reduce_motion)
        self.bar.grid(
            row=1, column=0, columnspan=self._total_columns,
            sticky="ew", padx=14, pady=(2, 6),
        )
        self.bar.set_now(float(snapshot.get("progress", 0) or 0) / 100.0)

        self.stats_label = ctk.CTkLabel(
            self,
            text="",
            font=app.f_small,
            anchor=app.text_anchor,
            justify=app.text_justify,
            text_color=app.color_muted,
        )
        self.stats_label.grid(
            row=2, column=text_column, sticky="ew",
            padx=self._pad(14, 8), pady=(0, 10),
        )

        self.actions = ctk.CTkFrame(self, fg_color="transparent")
        self.actions.grid(
            row=2, column=badge_column, sticky=self._end_sticky,
            padx=self._pad(0, 10), pady=(0, 8),
        )

        self.btn_pause = ctk.CTkButton(
            self.actions, width=80, height=26, font=app.f_small,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda: app.toggle_pause(self.task_id),
        )
        self.btn_cancel = ctk.CTkButton(
            self.actions, width=62, height=26, font=app.f_small,
            fg_color=DANGER, hover_color=ACCENT_HOVER,
            command=lambda: app.cancel_task(self.task_id),
        )
        self.btn_open = ctk.CTkButton(
            self.actions, width=92, height=26, font=app.f_small,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda: app.open_task_file(self.task_id),
        )
        self.btn_retry = ctk.CTkButton(
            self.actions, width=96, height=26, font=app.f_small,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda: app.retry_task(self.task_id),
        )
        self.btn_remove = ctk.CTkButton(
            self.actions, width=60, height=26, font=app.f_small,
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=lambda: app.remove_task_card(self.task_id),
        )
        self._layout_actions()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-3>", self._context_menu)
        self.bind("<Control-Button-1>", self._context_menu)
        self.update_snapshot(snapshot)

    # ------------------------------------------------------------------
    def _build_thumbnail(self, column: int, path: str) -> None:
        holder = ctk.CTkFrame(
            self, width=104, height=58, corner_radius=8, fg_color=SOFT_BUTTON
        )
        holder.grid(
            row=0, column=column, rowspan=3,
            padx=self._pad(12, 8), pady=10,
        )
        holder.grid_propagate(False)
        self.app._register_shape(holder, width=104, height=58)
        image = make_image(path, (104, 58))
        if image is not None:
            self._thumb_image = image
            self.app._register_image(image, (104, 58))
            ctk.CTkLabel(holder, text="", image=image, corner_radius=8).place(
                relx=0, rely=0, relwidth=1, relheight=1
            )
        else:
            ctk.CTkLabel(
                holder, text="🎬", fg_color="transparent",
                font=self.app._font(22),
            ).place(relx=0.5, rely=0.5, anchor="center")

    def _column(self, logical: int, total: int) -> int:
        return total - 1 - logical if self._rtl else logical

    def _pad(self, start: int, end: int) -> tuple[int, int]:
        return (end, start) if self._rtl else (start, end)

    @property
    def _end_sticky(self) -> str:
        return "w" if self._rtl else "e"

    def _layout_actions(self) -> None:
        buttons = (
            self.btn_pause, self.btn_cancel, self.btn_open,
            self.btn_retry, self.btn_remove,
        )
        gap = 2
        for logical, button in enumerate(buttons):
            button.grid(
                row=0, column=self._column(logical, len(buttons)),
                padx=gap,
            )

    def _on_enter(self, _event=None) -> None:
        self._hover = True
        self.configure(border_color=CARD_HOVER)

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self.configure(border_color=CARD_BORDER)

    def _context_menu(self, event):
        handler = getattr(self.app, "_show_task_menu", None)
        if handler is not None:
            handler(event, self.task_id)
        return "break"

    def update_snapshot(self, snapshot: dict) -> None:
        self.snapshot = snapshot
        app = self.app
        status = snapshot.get("status", "pending")
        color = STATUS_COLORS.get(status, STATUS_COLORS["pending"])
        progress_color = PROGRESS_COLORS.get(status, PROGRESS_COLORS["pending"])

        self.title_label.configure(
            text=app.S(truncate(snapshot.get("title", ""), 88)),
            anchor=app.text_anchor,
            justify=app.text_justify,
        )
        self.stats_label.configure(anchor=app.text_anchor, justify=app.text_justify)

        self.badge.configure(text=app.T(f"state_{status}"), fg_color=color)
        self.bar.configure(progress_color=progress_color)
        self.bar.animate_to(float(snapshot.get("progress", 0) or 0) / 100.0)

        percent = f"{int(snapshot.get('progress', 0) or 0)}%"
        speed = format_speed(snapshot.get("speed"))
        eta = format_eta(snapshot.get("eta"))
        size = format_bytes(snapshot.get("size"))
        if status == "scheduled":
            stats = app.T(
                "stats_scheduled", time=format_clock(snapshot.get("scheduled_for"))
            )
        elif status == "downloading":
            stats = app.T("stats_line", percent=percent, speed=speed, eta=eta)
        elif status == "paused":
            stats = app.T("stats_paused", percent=percent)
        elif status == "processing":
            stats = app.T("stats_processing")
        elif status == "completed":
            stats = app.T("stats_done", percent="100", size=size)
        elif status == "error":
            stats = app.T(snapshot.get("error_key") or "err_generic")
        elif status == "cancelled":
            stats = app.T("state_cancelled")
        else:
            stats = percent
        self.stats_label.configure(text=stats)

        self._button_text(self.btn_pause, "btn_resume" if status == "paused" else "btn_pause")
        self._button_text(self.btn_cancel, "btn_cancel")
        self._button_text(self.btn_open, "btn_open")
        self._button_text(self.btn_retry, "btn_retry")
        self._button_text(self.btn_remove, "btn_remove")

        self._show(self.btn_pause, status in ("downloading", "paused"))
        self._show(self.btn_cancel, status in ("pending", "scheduled", "downloading", "paused"))
        self._show(self.btn_open, status == "completed" and bool(snapshot.get("filepath")))
        self._show(self.btn_retry, status in ("error", "cancelled"))
        self._show(self.btn_remove, status in ("completed", "error", "cancelled"))

    def _button_text(self, button: ctk.CTkButton, key: str) -> None:
        button.configure(text=self.app.T(key))

    @staticmethod
    def _show(widget: ctk.CTkBaseClass, visible: bool) -> None:
        if visible:
            if not widget.winfo_ismapped():
                widget.grid()
        else:
            widget.grid_remove()


# ---------------------------------------------------------------------------
# Media library list row
# ---------------------------------------------------------------------------
class HistoryRow(ctk.CTkFrame):
    """One list row in the media library / history tab.

    Shows a 16:9 thumbnail when one is available, a media-type badge overlay,
    plus the title, metadata and the open/remove actions.
    """

    THUMB_SIZE = (128, 72)

    def __init__(self, master, entry: dict, app) -> None:
        super().__init__(
            master,
            corner_radius=14,
            fg_color=CARD_SOFT,      # Softer card background
            border_width=1,
            border_color=CARD_BORDER,
        )
        self.entry = entry
        self.app = app
        self._rtl = is_rtl(app.settings.language)
        self._thumb_image = None
        # Softer card appearance
        self.configure(fg_color=CARD_SOFT)

        thumb_column = self._column(0, 3)
        text_column = self._column(1, 3)
        actions_column = self._column(2, 3)
        self.grid_columnconfigure(text_column, weight=1)

        self._build_thumbnail(thumb_column)

        title_text = truncate(entry.get("title", ""), 110)
        if entry.get("favorite"):
            title_text = "★ " + title_text
        title = app.S(title_text)
        self.title_label = ctk.CTkLabel(
            self, text=title, font=app.f_body_bold,
            anchor=app.text_anchor, justify=app.text_justify,
        )
        self.title_label.grid(
            row=0, column=text_column, sticky="ew",
            padx=self._pad(4, 8), pady=(12, 2),
        )

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(
            row=0, column=actions_column, rowspan=2, sticky=self._end_sticky,
            padx=self._pad(0, 10), pady=8,
        )

        self.open_btn = ctk.CTkButton(
            actions, width=100, height=28, font=app.f_small,
            text=app.T("btn_open"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda: app.open_history_file(self.entry),
        )
        self.remove_btn = ctk.CTkButton(
            actions, width=62, height=28, font=app.f_small,
            text=app.T("btn_remove"),
            fg_color=SOFT_BUTTON, hover_color=SOFT_HOVER,
            text_color=SOFT_TEXT,
            command=lambda: app.remove_history_entry(self.entry),
        )
        self.favorite_btn = ctk.CTkButton(
            actions, width=32, height=28, font=app._font(15),
            text="★" if entry.get("favorite") else "☆",
            fg_color=SOFT_BUTTON, hover_color=ACCENT,
            text_color=SOFT_TEXT,
            command=lambda: app.toggle_history_favorite(self.entry),
        )
        self.open_btn.grid(row=0, column=self._column(0, 3), padx=3)
        self.remove_btn.grid(row=0, column=self._column(1, 3), padx=3)
        self.favorite_btn.grid(row=0, column=self._column(2, 3), padx=3)

        exists = bool(entry.get("filepath")) and Path(entry["filepath"]).exists()
        meta = app.T(
            "history_item_meta",
            platform=entry.get("platform") or "—",
            date=str(entry.get("timestamp", ""))[:16].replace("T", " "),
            size=format_bytes(entry.get("size")),
        )
        if not exists:
            meta = f"{meta} • {app.T('history_missing_file')}"
        tags = entry.get("tags") or []
        if tags:
            meta += "  •  " + " ".join("#" + str(tag) for tag in tags[:3])
        meta += "  •  " + app.hash_badge(entry)[0]

        self.meta_label = ctk.CTkLabel(
            self, text=app.S(meta), font=app.f_small,
            text_color=app.color_muted,
            anchor=app.text_anchor, justify=app.text_justify,
        )
        self.meta_label.grid(
            row=1, column=text_column, sticky="ew",
            padx=self._pad(4, 8), pady=(0, 12),
        )

        self.bind("<Enter>", lambda _e: self.configure(border_color=CARD_HOVER))
        self.bind("<Leave>", lambda _e: self.configure(border_color=CARD_BORDER))
        self.bind("<Double-Button-1>", lambda _e: app.open_history_file(self.entry))
        self.bind("<Button-3>", self._context_menu)
        self.bind("<Control-Button-1>", self._context_menu)

    # ------------------------------------------------------------------
    def _context_menu(self, event):
        handler = getattr(self.app, "_show_history_menu", None)
        if handler is not None:
            handler(event, self.entry)
        return "break"

    def _build_thumbnail(self, column: int) -> None:
        path = self.entry.get("thumbnail") or self.entry.get("filepath") or ""
        kind = media_kind(path)
        holder = ctk.CTkFrame(
            self,
            width=self.THUMB_SIZE[0],
            height=self.THUMB_SIZE[1],
            corner_radius=10,
            fg_color=SOFT_BUTTON,
        )
        holder.grid(
            row=0, column=column, rowspan=2,
            padx=self._pad(12, 8), pady=10,
        )
        holder.grid_propagate(False)
        holder.pack_propagate(False)

        self.app._register_shape(holder, width=self.THUMB_SIZE[0], height=self.THUMB_SIZE[1])
        image = make_image(path, self.THUMB_SIZE) if kind in ("video", "image") else None
        if image is not None:
            self._thumb_image = image
            self.app._register_image(image, self.THUMB_SIZE)
            ctk.CTkLabel(holder, text="", image=image, corner_radius=10).place(
                relx=0, rely=0, relwidth=1, relheight=1
            )
        else:
            ctk.CTkLabel(
                holder,
                text=KIND_SYMBOLS.get(kind, "📄"),
                fg_color="transparent",
                font=self.app._font(26),
            ).place(relx=0.5, rely=0.5, anchor="center")

        badge = ctk.CTkLabel(
            holder,
            text=self.app.T(f"kind_{kind}"),
            font=self.app._font(9, weight="bold"),
            fg_color=ACCENT,
            text_color="#FFFFFF",
            corner_radius=6,
            height=18,
            padx=6,
        )
        if self._rtl:
            badge.place(x=6, y=6)
        else:
            badge.place(relx=1.0, x=-6, y=6, anchor="ne")

    def _column(self, logical: int, total: int) -> int:
        return total - 1 - logical if self._rtl else logical

    def _pad(self, start: int, end: int) -> tuple[int, int]:
        return (end, start) if self._rtl else (start, end)

    @property
    def _end_sticky(self) -> str:
        return "w" if self._rtl else "e"

    def refresh_texts(self) -> None:
        self.open_btn.configure(text=self.app.T("btn_open"))
        self.remove_btn.configure(text=self.app.T("btn_remove"))


# ---------------------------------------------------------------------------
# Media library grid card
# ---------------------------------------------------------------------------
class MediaCard(ctk.CTkFrame):
    """A 16:9 library card with a gradient caption and hover actions."""

    WIDTH = 240
    THUMB_HEIGHT = 135

    def __init__(self, master, entry: dict, app) -> None:
        super().__init__(
            master,
            width=self.WIDTH,
            corner_radius=16,
            fg_color=CARD_SOFT,      # Use card_soft for softer card background
            border_width=1,
            border_color=CARD_BORDER,
        )
        self.entry = entry
        self.app = app
        self._rtl = is_rtl(app.settings.language)
        self._thumb_image = None
        # Add subtle inner shadow effect using background color
        self.configure(fg_color=CARD_SOFT)
        self._hide_job: str | None = None
        self.grid_propagate(False)

        # --- Hover effect setup ---
        self._default_border_color = CARD_BORDER
        self._hover_border_color = ACCENT_HOVER
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

        kind = media_kind(entry.get("filepath") or "")
        path = entry.get("thumbnail") or entry.get("filepath") or ""

        thumb = ctk.CTkFrame(
            self,
            width=self.WIDTH - 16,
            height=self.THUMB_HEIGHT,
            corner_radius=12,
            fg_color=SOFT_BUTTON,
        )
        thumb.pack(fill="x", padx=8, pady=(8, 0))
        thumb.pack_propagate(False)
        self.thumb = thumb
        self.app._register_shape(
            thumb, width=self.WIDTH - 16, height=self.THUMB_HEIGHT
        )

        image = make_image(path, (self.WIDTH - 16, self.THUMB_HEIGHT)) if kind in ("video", "image") else None
        if image is not None:
            self._thumb_image = image
            self.app._register_image(image, (self.WIDTH - 16, self.THUMB_HEIGHT))
            self.thumb_image = ctk.CTkLabel(thumb, text="", image=image, corner_radius=12)
            self.thumb_image.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.thumb_image.bind("<Double-Button-1>", self._open)
            self.thumb_image.bind("<Button-3>", self._context_menu)
            self.thumb_image.bind("<Control-Button-1>", self._context_menu)
        else:
            self.thumb_image = ctk.CTkLabel(
                thumb,
                text=KIND_SYMBOLS.get(kind, "📄"),
                fg_color="transparent",
                font=app._font(36),
            )
            self.thumb_image.place(relx=0.5, rely=0.5, anchor="center")

        # Type badge (top corner) and extension badge (bottom corner).
        type_badge = ctk.CTkLabel(
            thumb,
            text=app.T(f"kind_{kind}"),
            font=app._font(10, weight="bold"),
            fg_color=ACCENT,
            text_color="#FFFFFF",
            corner_radius=7,
            height=20,
            padx=7,
        )
        suffix = Path(entry.get("filepath") or "").suffix.lstrip(".").upper()[:5]
        quality_badge = ctk.CTkLabel(
            thumb,
            text=suffix or "FILE",
            font=app._font(9, weight="bold"),
            fg_color="#101014",
            text_color="#FFFFFF",
            corner_radius=6,
            height=18,
            padx=6,
        )
        if self._rtl:
            type_badge.place(x=7, y=7)
            quality_badge.place(relx=1.0, x=-7, rely=1.0, y=-7, anchor="se")
        else:
            type_badge.place(relx=1.0, x=-7, y=7, anchor="ne")
            quality_badge.place(x=7, rely=1.0, y=-7, anchor="sw")

        # Hover action strip sits over the gradient.
        self.hover_actions = ctk.CTkFrame(thumb, fg_color="transparent")
        open_btn = ctk.CTkButton(
            self.hover_actions,
            text=app.T("btn_open"),
            width=86,
            height=26,
            corner_radius=8,
            font=app.f_small,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=lambda: app.open_history_file(self.entry),
        )
        remove_btn = ctk.CTkButton(
            self.hover_actions,
            text="✕",
            width=28,
            height=26,
            corner_radius=8,
            font=app.f_small_bold,
            fg_color="#101014",
            hover_color=DANGER,
            command=lambda: app.remove_history_entry(self.entry),
        )
        fav_btn = ctk.CTkButton(
            self.hover_actions,
            text="★" if entry.get("favorite") else "☆",
            width=28,
            height=26,
            corner_radius=8,
            font=app._font(15),
            fg_color="#101014",
            hover_color=ACCENT,
            command=lambda: app.toggle_history_favorite(self.entry),
        )
        action_side = "left" if not self._rtl else "right"
        action_gap = (0, 4) if not self._rtl else (4, 0)
        fav_btn.pack(side=action_side, padx=action_gap)
        open_btn.pack(side=action_side, padx=action_gap)
        remove_btn.pack(side=action_side)

        title_text = truncate(entry.get("title", ""), 64)
        if entry.get("favorite"):
            title_text = "★ " + title_text
        self.title_label = ctk.CTkLabel(
            self,
            text=app.S(title_text),
            font=app.f_body_bold,
            anchor=app.text_anchor,
            justify=app.text_justify,
            wraplength=self.WIDTH - 28,
        )
        self.title_label.pack(fill="x", padx=12, pady=(10, 2))

        exists = bool(entry.get("filepath")) and Path(entry["filepath"]).exists()
        meta = app.T(
            "history_item_meta",
            platform=entry.get("platform") or "—",
            date=str(entry.get("timestamp", ""))[:10],
            size=format_bytes(entry.get("size")),
        )
        if not exists:
            meta = f"{meta} • {app.T('history_missing_file')}"
        tags = entry.get("tags") or []
        if tags:
            meta += "  •  " + " ".join("#" + str(tag) for tag in tags[:3])
        meta += "  •  " + app.hash_badge(entry)[0]
        self.meta_label = ctk.CTkLabel(
            self,
            text=app.S(meta),
            font=app.f_small,
            text_color=app.color_muted,
            anchor=app.text_anchor,
            justify=app.text_justify,
            wraplength=self.WIDTH - 28,
        )
        self.meta_label.pack(fill="x", padx=12, pady=(0, 10))

        for widget in (self, self.title_label, self.meta_label, thumb):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Double-Button-1>", self._open)
            widget.bind("<Button-3>", self._context_menu)
            widget.bind("<Control-Button-1>", self._context_menu)

    # ------------------------------------------------------------------
    def _open(self, _event=None):
        self.app.open_history_file(self.entry)
        return "break"

    def _context_menu(self, event):
        handler = getattr(self.app, "_show_history_menu", None)
        if handler is not None:
            handler(event, self.entry)
        return "break"

    def _on_enter(self, _event=None) -> None:
        if self._hide_job is not None:
            try:
                self.after_cancel(self._hide_job)
            except Exception:
                pass
            self._hide_job = None
        self.configure(border_color=ACCENT)
        self.hover_actions.place(relx=0.5, rely=1.0, y=-9, anchor="s")

    def _on_leave(self, _event=None) -> None:
        self.configure(border_color=CARD_BORDER)
        self._hide_job = self.after(110, self._maybe_hide_actions)

    def _maybe_hide_actions(self) -> None:
        self._hide_job = None
        try:
            x, y = self.winfo_pointerxy()
            widget = self.winfo_containing(x, y)
        except Exception:
            widget = None
        if widget is not None and (widget is self.hover_actions or self._is_descendant(widget)):
            return
        self.hover_actions.place_forget()

    def _is_descendant(self, widget) -> bool:
        try:
            parent = widget.master
            while parent is not None:
                if parent is self.hover_actions:
                    return True
                parent = getattr(parent, "master", None)
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Toasts
# ---------------------------------------------------------------------------
class Toast(ctk.CTkFrame):
    """A small notification that slides up from the bottom of the window."""

    WIDTH = 340
    HEIGHT = 66

    KINDS = {
        "success": {"symbol": "✓"},
        "error": {"symbol": "!"},
        "info": {"symbol": "i"},
    }

    def __init__(self, app, text: str, kind: str = "info", duration: int = 3200) -> None:
        style = self.KINDS.get(kind, self.KINDS["info"])
        tokens = app.palette_tokens
        border = tokens["success"] if kind == "success" else (
            tokens["danger"] if kind == "error" else tokens["accent"]
        )
        super().__init__(
            app,
            width=self.WIDTH,
            height=self.HEIGHT,
            corner_radius=14,
            fg_color=tokens["toast_bg"],
            border_width=1,
            border_color=border,
        )
        self.app = app
        self._rtl = is_rtl(app.settings.language)
        self._job: str | None = None
        self._duration = max(1200, duration)
        self.grid_propagate(False)

        text_column = 1 if not self._rtl else 0
        icon_column = 0 if not self._rtl else 1
        self.grid_columnconfigure(text_column, weight=1)

        icon = ctk.CTkLabel(
            self,
            text=style["symbol"],
            width=26,
            height=26,
            corner_radius=13,
            fg_color=border,
            text_color="#FFFFFF",
            font=app.f_small_bold,
        )
        icon.grid(
            row=0, column=icon_column,
            padx=(10, 14) if self._rtl else (14, 10), pady=18,
        )

        label = ctk.CTkLabel(
            self,
            text=text,
            font=app.f_small_bold,
            anchor=app.text_anchor,
            justify=app.text_justify,
            wraplength=250,
        )
        label.grid(
            row=0, column=text_column, sticky="ew",
            padx=(16, 0) if self._rtl else (0, 16), pady=12,
        )

        self._target_y = max(20, app.winfo_height() - self.HEIGHT - 52)
        self._start_y = app.winfo_height() + 10
        self.place(x=self._x(), y=self._start_y, width=self.WIDTH, height=self.HEIGHT)
        self.lift()
        if app.animations_enabled:
            self._slide(self._start_y, self._target_y, on_done=self._schedule_hide)
        else:
            self.place_configure(y=self._target_y)
            self._schedule_hide()

    def _x(self) -> int:
        width = max(self.app.winfo_width(), 640)
        # Sit on the trailing side: right in LTR, left in RTL.
        if self._rtl:
            return 26
        return max(26, width - self.WIDTH - 26)

    def _slide(self, start: int, end: int, on_done=None, steps: int = 10) -> None:
        if not self.winfo_exists():
            return

        def step(index: int) -> None:
            if not self.winfo_exists():
                return
            t = ease_out_cubic(index / steps)
            self.place_configure(x=self._x(), y=int(start + (end - start) * t))
            if index < steps:
                self._job = self.after(16, lambda: step(index + 1))
            else:
                self._job = None
                if on_done:
                    on_done()

        step(0)

    def _schedule_hide(self) -> None:
        self._job = self.after(self._duration, self._hide)

    def _hide(self) -> None:
        if not self.winfo_exists():
            return
        if not self.app.animations_enabled:
            self.destroy()
            return
        start = self._target_y
        end = self.app.winfo_height() + 10

        def step(index: int) -> None:
            if not self.winfo_exists():
                return
            t = index / 8
            self.place_configure(x=self._x(), y=int(start + (end - start) * (t * t)))
            if index < 8:
                self._job = self.after(14, lambda: step(index + 1))
            else:
                self._job = None
                self.destroy()

        step(0)

    def dismiss(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        if self.winfo_exists():
            self._hide()

    def destroy(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        super().destroy()
