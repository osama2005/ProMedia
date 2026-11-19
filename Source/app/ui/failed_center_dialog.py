"""Failed Downloads Center: inspect, retry or remove failed downloads."""

from __future__ import annotations

import customtkinter as ctk

from app.i18n import is_rtl, translate


class FailedCenterDialog(ctk.CTkToplevel):
    """A read-only view of persisted failures with retry/remove controls."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.app = master
        self._rtl = is_rtl(master.settings.language)
        tokens = master.palette_tokens

        self.title(master.T("failed_center_title"))
        self.geometry("720x560")
        self.minsize(560, 400)
        self.resizable(True, True)
        self.configure(fg_color=tokens["bg"])
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ---- header ----------------------------------------------------
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text=master.T("failed_center_title"),
            font=master.f_h1,
            anchor=master.text_anchor,
            justify=master.text_justify,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header,
            text=master.T("failed_center_subtitle"),
            font=master.f_small,
            text_color=tokens["muted"],
            anchor=master.text_anchor,
            justify=master.text_justify,
            wraplength=620,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=18, pady=(6, 2))
        side = master._start_side()
        self.retry_all_btn = ctk.CTkButton(
            actions,
            text=master.T("failed_center_retry_all"),
            width=140,
            height=32,
            corner_radius=8,
            font=master.f_small,
            fg_color=tokens["accent"],
            hover_color=tokens["accent_hover"],
            command=self._retry_all,
        )
        self.retry_all_btn.pack(side=side, padx=(0, 8))
        self.clear_btn = ctk.CTkButton(
            actions,
            text=master.T("failed_center_clear"),
            width=110,
            height=32,
            corner_radius=8,
            font=master.f_small,
            fg_color=tokens["soft_button"],
            hover_color=tokens["soft_hover"],
            text_color=tokens["soft_text"],
            command=self._clear,
        )
        self.clear_btn.pack(side=side)

        # ---- list ------------------------------------------------------
        self.scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0
        )
        self.scroll.grid(row=2, column=0, sticky="nsew", padx=12, pady=(4, 14))
        self.scroll.grid_columnconfigure(0, weight=1)

        self._refresh()
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

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        for child in self.scroll.winfo_children():
            child.destroy()
        entries = self.app.failures.entries()
        tokens = self.app.palette_tokens
        if not entries:
            ctk.CTkLabel(
                self.scroll,
                text=self.app.T("failed_center_empty"),
                font=self.app.f_small,
                text_color=tokens["muted"],
                anchor=self.app.text_anchor,
                justify=self.app.text_justify,
            ).grid(row=0, column=0, sticky="ew", pady=40)
            self.retry_all_btn.configure(state="disabled")
            self.clear_btn.configure(state="disabled")
            return
        self.retry_all_btn.configure(state="normal")
        self.clear_btn.configure(state="normal")

        for index, entry in enumerate(entries):
            row = ctk.CTkFrame(
                self.scroll,
                corner_radius=12,
                fg_color=tokens["card"],
                border_width=1,
                border_color=tokens["border"],
            )
            row.grid(row=index, column=0, sticky="ew", pady=4)
            row.grid_columnconfigure(0, weight=1)

            title = str(entry.get("title") or entry.get("url") or "—")
            if len(title) > 58:
                title = title[:57] + "…"
            ctk.CTkLabel(
                row,
                text=self.app.S(title),
                font=self.app.f_body_bold,
                anchor=self.app.text_anchor,
                justify=self.app.text_justify,
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=(9, 0))

            reason_key = str(entry.get("error_key") or "err_generic")
            reason = translate(self.app.settings.language, reason_key)
            detail = str(entry.get("error_detail") or "")
            reason_text = self.app.T("failed_center_reason", reason=reason)
            ctk.CTkLabel(
                row,
                text=self.app.S(reason_text),
                font=self.app.f_small,
                text_color=tokens["muted"],
                anchor=self.app.text_anchor,
                justify=self.app.text_justify,
            ).grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 0))
            if detail:
                ctk.CTkLabel(
                    row,
                    text=self.app.S(detail[:120]),
                    font=self.app.f_small,
                    text_color=tokens["muted"],
                    anchor=self.app.text_anchor,
                    justify=self.app.text_justify,
                ).grid(row=2, column=0, sticky="ew", padx=12)

            attempt = int(entry.get("attempt") or 1)
            stamp = str(entry.get("timestamp") or "")[:16].replace("T", " ")
            meta = f"{self.app.T('failed_center_attempts', count=attempt)}  ·  {stamp}"
            ctk.CTkLabel(
                row,
                text=meta,
                font=self.app.f_small,
                text_color=tokens["accent"],
                anchor=self.app.text_anchor,
                justify=self.app.text_justify,
            ).grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 0))

            entry_id = str(entry.get("id") or "")
            buttons = ctk.CTkFrame(row, fg_color="transparent")
            buttons.grid(row=4, column=0, sticky="ew", padx=12, pady=(4, 10))
            side = self.app._start_side()
            ctk.CTkButton(
                buttons,
                text=self.app.T("failed_center_retry"),
                width=120,
                height=28,
                corner_radius=8,
                font=self.app.f_small,
                fg_color=tokens["accent"],
                hover_color=tokens["accent_hover"],
                command=lambda e=entry_id: self._retry(e),
            ).pack(side=side, padx=self.app._pad(0, 6))
            ctk.CTkButton(
                buttons,
                text=self.app.T("failed_center_remove"),
                width=90,
                height=28,
                corner_radius=8,
                font=self.app.f_small,
                fg_color=tokens["soft_button"],
                hover_color=tokens["soft_hover"],
                text_color=tokens["soft_text"],
                command=lambda e=entry_id: self._remove(e),
            ).pack(side=side)

    # ------------------------------------------------------------------
    def _retry(self, entry_id: str) -> None:
        if self.app.retry_failure(entry_id):
            self._refresh()

    def _retry_all(self) -> None:
        count = self.app.retry_all_failures()
        if count:
            self.app._toast("success", "toast_failures_retried", count=count)
        self._refresh()

    def _remove(self, entry_id: str) -> None:
        self.app.remove_failure(entry_id)
        self._refresh()

    def _clear(self) -> None:
        self.app.clear_failures()
        self.app._toast("info", "toast_failed_cleared")
        self._refresh()
