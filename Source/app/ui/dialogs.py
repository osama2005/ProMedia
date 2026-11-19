"""Extra modal dialogs: About and the in-app notification centre."""

from __future__ import annotations

import customtkinter as ctk

from app.i18n import is_rtl
from app.paths import APP_VERSION

_KIND_COLORS = {
    "success": "success",
    "error": "danger",
    "info": "accent",
}
_KIND_SYMBOLS = {"success": "✓", "error": "!", "info": "i"}


class _BaseDialog(ctk.CTkToplevel):
    """Shared behaviour: theming, RTL grid and centring over the parent."""

    def __init__(self, master, title_key: str, width: int, height: int) -> None:
        super().__init__(master)
        self.app = master
        self._rtl = is_rtl(master.settings.language)
        self.title(master.T(title_key))
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self.configure(fg_color=master.palette_tokens["bg"])
        self.transient(master)
        self.grid_columnconfigure(0, weight=1)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.after(80, self._centre)

    def _centre(self) -> None:
        try:
            self.update_idletasks()
            parent = self.master
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            width, height = self.winfo_width(), self.winfo_height()
            x = max(0, px + (pw - width) // 2)
            y = max(0, py + (ph - height) // 2)
            self.geometry(f"+{x}+{y}")
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass


class AboutDialog(_BaseDialog):
    """Branding, version and credits."""

    def __init__(self, master) -> None:
        super().__init__(master, "about_title", 460, 470)
        app = self.app
        tokens = app.palette_tokens

        logo = app._load_logo(76)
        if logo is not None:
            self._logo = logo
            ctk.CTkLabel(self, text="", image=logo, width=76).pack(pady=(26, 8))
        else:
            ctk.CTkLabel(
                self,
                text="⇩",
                width=76,
                height=76,
                corner_radius=20,
                fg_color=tokens["accent"],
                text_color="#FFFFFF",
                font=app.f_logo,
            ).pack(pady=(26, 8))

        ctk.CTkLabel(
            self,
            text=app.T("app_title"),
            font=app.f_h1,
            anchor=app.text_anchor,
            justify=app.text_justify,
        ).pack(fill="x", padx=26)

        ctk.CTkLabel(
            self,
            text=app.T("about_tagline"),
            font=app.f_small,
            text_color=app.color_muted,
            anchor=app.text_anchor,
            justify=app.text_justify,
        ).pack(fill="x", padx=26, pady=(2, 10))

        chip = ctk.CTkLabel(
            self,
            text=f"{app.T('about_version')} {APP_VERSION}",
            font=app.f_small_bold,
            corner_radius=9,
            height=26,
            padx=12,
            fg_color=tokens["accent_soft"],
            text_color=tokens["accent"],
        )
        chip.pack(anchor=app.text_anchor, padx=26)

        for key in ("about_made_with", "about_license", "about_shortcuts"):
            ctk.CTkLabel(
                self,
                text=app.T(key),
                font=app.f_small,
                text_color=app.color_muted,
                wraplength=400,
                anchor=app.text_anchor,
                justify=app.text_justify,
            ).pack(fill="x", padx=26, pady=(12, 0))

        ctk.CTkButton(
            self,
            text=app.T("btn_close"),
            height=38,
            font=app.f_body,
            fg_color=tokens["accent"],
            hover_color=tokens["accent_hover"],
            command=self.destroy,
        ).pack(fill="x", padx=26, pady=(22, 22), side="bottom")


class NotificationsDialog(_BaseDialog):
    """A scrollable history of in-app notifications."""

    def __init__(self, master) -> None:
        super().__init__(master, "notifications_title", 460, 520)
        app = self.app
        tokens = app.palette_tokens

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))
        ctk.CTkLabel(
            header,
            text=app.T("notifications_title"),
            font=app.f_h1,
            anchor=app.text_anchor,
            justify=app.text_justify,
        ).pack(side="right" if self._rtl else "left")
        ctk.CTkButton(
            header,
            text=app.T("notifications_clear"),
            width=96,
            height=28,
            font=app.f_small,
            fg_color=tokens["soft_button"],
            hover_color=tokens["soft_hover"],
            text_color=tokens["soft_text"],
            command=self._clear,
        ).pack(side="left" if self._rtl else "right")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.scroll.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            self,
            text=app.T("btn_close"),
            height=36,
            font=app.f_body,
            fg_color=tokens["accent"],
            hover_color=tokens["accent_hover"],
            command=self.destroy,
        ).pack(fill="x", padx=20, pady=(0, 18))

        self._render()

    def _render(self) -> None:
        for child in self.scroll.winfo_children():
            child.destroy()
        items = list(self.app.notifications)
        if not items:
            ctk.CTkLabel(
                self.scroll,
                text=self.app.T("notifications_empty"),
                font=self.app.f_body,
                text_color=self.app.color_muted,
            ).grid(row=0, column=0, pady=60)
            return

        tokens = self.app.palette_tokens
        for index, item in enumerate(items):
            kind = str(item.get("kind", "info"))
            colour = tokens[_KIND_COLORS.get(kind, "accent")]
            row = ctk.CTkFrame(
                self.scroll,
                fg_color=tokens["row_bg"],
                corner_radius=10,
                border_width=1,
                border_color=tokens["row_border"],
            )
            row.grid(row=index, column=0, sticky="ew", padx=4, pady=4)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                row,
                text=_KIND_SYMBOLS.get(kind, "i"),
                width=24,
                height=24,
                corner_radius=12,
                fg_color=colour,
                text_color="#FFFFFF",
                font=self.app.f_small_bold,
            ).grid(row=0, column=0, padx=(10, 8), pady=10)

            ctk.CTkLabel(
                row,
                text=str(item.get("text", "")),
                font=self.app.f_small,
                wraplength=300,
                anchor=self.app.text_anchor,
                justify=self.app.text_justify,
            ).grid(row=0, column=1, sticky="ew", pady=10)

            ctk.CTkLabel(
                row,
                text=str(item.get("time", "")),
                font=self.app.f_small,
                text_color=self.app.color_muted,
            ).grid(row=0, column=2, padx=(6, 10), pady=10)

    def _clear(self) -> None:
        self.app.clear_notifications()
        self._render()
