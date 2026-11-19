"""Read-only diagnostics results dialog."""

from __future__ import annotations

import customtkinter as ctk

from app.core.diagnostics import run_diagnostics


class DiagnosticsDialog(ctk.CTkToplevel):
    """Display a fresh diagnostics report."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.app = master
        tokens = master.palette_tokens
        self.title(master.T("diag_title"))
        self.geometry("640x560")
        self.minsize(540, 420)
        self.configure(fg_color=tokens["bg"])
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text=master.T("diag_title"), font=master.f_h1,
            anchor=master.text_anchor, justify=master.text_justify,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header, text=master.T("diag_hint"), font=master.f_small,
            text_color=tokens["muted"], anchor=master.text_anchor,
            justify=master.text_justify, wraplength=590,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))
        ctk.CTkButton(
            header, text=master.T("diag_run"), height=30, width=110,
            font=master.f_small, corner_radius=8,
            fg_color=tokens["soft_button"], hover_color=tokens["soft_hover"],
            text_color=tokens["soft_text"], command=self.refresh,
        ).grid(row=0, column=1, rowspan=2, padx=(10, 0))

        self.summary = ctk.CTkLabel(
            self, text="", font=master.f_small_bold,
            text_color=tokens["accent"], anchor=master.text_anchor,
            justify=master.text_justify,
        )
        self.summary.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 4))

        self.scroll = ctk.CTkScrollableFrame(
            self, fg_color=tokens["card"], corner_radius=12
        )
        self.scroll.grid(row=2, column=0, sticky="nsew", padx=18, pady=4)
        self.scroll.grid_columnconfigure(0, weight=1)

        self.refresh()
        self.after(80, self._centre)

    def _centre(self) -> None:
        try:
            self.update_idletasks()
            parent = self.master
            width, height = self.winfo_width(), self.winfo_height()
            x = max(0, parent.winfo_rootx() + (parent.winfo_width() - width) // 2)
            y = max(0, parent.winfo_rooty() + (parent.winfo_height() - height) // 2)
            self.geometry(f"+{x}+{y}")
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass

    def refresh(self) -> None:
        app = self.app
        for child in list(self.scroll.winfo_children()):
            child.destroy()
        results = run_diagnostics(
            app.settings, app.ffmpeg,
            history_count=len(app.history.entries()),
        )
        ok_count = sum(1 for result in results if result.ok)
        self.summary.configure(text=f"{ok_count} / {len(results)}")

        severity_colour = {
            "ok": app.palette_tokens.get("success", "#3FCB87"),
            "warn": app.palette_tokens.get("warn", "#F3A531"),
            "error": app.palette_tokens.get("danger", "#D64B54"),
        }
        for index, result in enumerate(results):
            row = ctk.CTkFrame(
                self.scroll, fg_color=app.palette_tokens["soft_button"],
                corner_radius=10,
            )
            row.grid(row=index, column=0, sticky="ew", pady=(0, 6))
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row, text=result.icon, font=app.f_h2, width=28,
                text_color=severity_colour.get(result.severity, app.palette_tokens["muted"]),
                anchor=app.text_anchor,
            ).grid(row=0, column=0, padx=(12, 4), pady=9)
            ctk.CTkLabel(
                row, text=app.T(result.label_key), font=app.f_small_bold,
                anchor=app.text_anchor, justify=app.text_justify,
            ).grid(row=0, column=1, sticky="ew", pady=(8, 0))
            ctk.CTkLabel(
                row, text=result.detail, font=app.f_small,
                text_color=app.palette_tokens["muted"],
                anchor=app.text_anchor, justify=app.text_justify, wraplength=360,
            ).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 8))
            ctk.CTkLabel(
                row, text=app.T("diag_" + result.severity), font=app.f_small,
                text_color=severity_colour.get(result.severity, app.palette_tokens["muted"]),
            ).grid(row=0, column=2, padx=(4, 12), pady=(8, 0))
