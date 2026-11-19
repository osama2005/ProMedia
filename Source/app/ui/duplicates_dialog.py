"""Dialog for finding and safely removing duplicate library files."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox

from app.core.duplicates import DuplicateGroup, cleanup_duplicates, find_duplicates
from app.utils.helpers import format_bytes


class DuplicatesDialog(ctk.CTkToplevel):
    """Scan cached library metadata for duplicates and clean them up."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.app = master
        tokens = master.palette_tokens
        self.groups: list[DuplicateGroup] = []
        self._vars: dict[str, tk.BooleanVar] = {}

        self.title(master.T("dup_title"))
        self.geometry("720x620")
        self.minsize(600, 480)
        self.configure(fg_color=tokens["bg"])
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header, text=master.T("dup_title"), font=master.f_h1,
            anchor=master.text_anchor, justify=master.text_justify,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header, text=master.T("dup_hint"), font=master.f_small,
            text_color=tokens["muted"], anchor=master.text_anchor,
            justify=master.text_justify, wraplength=660,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=1, column=0, sticky="ew", padx=18, pady=(6, 4))
        controls.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            controls, text=master.T("dup_min_size"), font=master.f_small,
            text_color=tokens["muted"], anchor=master.text_anchor,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.size_var = tk.StringVar(
            value=str(getattr(master.settings, "duplicate_min_size_mb", 5))
        )
        ctk.CTkEntry(
            controls, textvariable=self.size_var, width=70, height=30,
            font=master.f_small, corner_radius=8,
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkButton(
            controls, text=master.T("dup_scan"), height=32,
            font=master.f_small_bold, corner_radius=9, width=130,
            fg_color=tokens["accent"], hover_color=tokens["accent_hover"],
            command=self._scan,
        ).grid(row=0, column=2, sticky="e", padx=(10, 0))

        self.summary = ctk.CTkLabel(
            self, text="", font=master.f_small_bold,
            text_color=tokens["accent"], anchor=master.text_anchor,
            justify=master.text_justify,
        )
        self.summary.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 4))

        self.scroll = ctk.CTkScrollableFrame(
            self, fg_color=tokens["card"], corner_radius=12
        )
        self.scroll.grid(row=3, column=0, sticky="nsew", padx=18, pady=4)
        self.scroll.grid_columnconfigure(0, weight=1)

        self.cleanup_btn = ctk.CTkButton(
            self, text=master.T("dup_cleanup"), height=38,
            font=master.f_small_bold, corner_radius=10,
            fg_color=tokens.get("danger", "#D64B54"),
            hover_color=tokens.get("danger", "#D64B54"),
            command=self._cleanup,
        )
        self.cleanup_btn.grid(row=4, column=0, sticky="ew", padx=18, pady=(4, 16))

        self._scan()
        self.after(80, self._centre)

    # ------------------------------------------------------------------
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

    def _scan(self) -> None:
        app = self.app
        try:
            min_mb = max(1, min(1000, int(self.size_var.get())))
        except (TypeError, ValueError):
            min_mb = 5
        app.settings.duplicate_min_size_mb = min_mb
        app.config.save(app.settings)
        self.groups = find_duplicates(app.history.entries(), min_size=min_mb * 1024 * 1024)
        self._vars = {}
        for child in list(self.scroll.winfo_children()):
            child.destroy()

        if not self.groups:
            ctk.CTkLabel(
                self.scroll, text=app.T("dup_empty"), font=app.f_body,
                text_color=self.app.palette_tokens["muted"],
                anchor=app.text_anchor, justify=app.text_justify,
            ).grid(row=0, column=0, sticky="ew", padx=16, pady=30)
            self.summary.configure(text="")
            self.cleanup_btn.configure(state="disabled")
            return

        wasted = sum(group.wasted_bytes for group in self.groups)
        self.summary.configure(text=app.T("dup_found", count=len(self.groups)) +
                               "  •  " + app.T("dup_wasted", size=format_bytes(wasted)))
        self.cleanup_btn.configure(state="normal")

        for index, group in enumerate(self.groups):
            card = ctk.CTkFrame(
                self.scroll, fg_color=self.app.palette_tokens["soft_button"],
                corner_radius=10,
            )
            card.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            card.grid_columnconfigure(0, weight=1)
            reason_key = "dup_reason_hash" if group.reason == "hash" else "dup_reason_name_size"
            ctk.CTkLabel(
                card, text=f"{app.T(reason_key)}  •  {format_bytes(group.wasted_bytes)}",
                font=app.f_small_bold, anchor=app.text_anchor,
                justify=app.text_justify,
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))

            for row, entry in enumerate(group.entries, start=1):
                entry_id = str(entry.get("id") or "")
                is_keep = entry_id == group.keep_id
                line = ctk.CTkFrame(card, fg_color="transparent")
                line.grid(row=row, column=0, sticky="ew", padx=12, pady=2)
                line.grid_columnconfigure(0, weight=1)
                title = str(entry.get("title") or Path(str(entry.get("filepath") or "")).name)
                detail = f"{title[:52]}  •  {format_bytes(entry.get('size') or 0)}"
                ctk.CTkLabel(
                    line, text=detail, font=app.f_small,
                    text_color=app.palette_tokens["muted"],
                    anchor=app.text_anchor, justify=app.text_justify,
                ).grid(row=0, column=0, sticky="ew")
                if is_keep:
                    ctk.CTkLabel(
                        line, text=app.T("dup_keep"), font=app.f_small_bold,
                        text_color=app.palette_tokens.get("success", "#3FCB87"),
                    ).grid(row=0, column=1, padx=(8, 0))
                else:
                    var = tk.BooleanVar(value=False)
                    self._vars[entry_id] = var
                    ctk.CTkCheckBox(
                        line, text=app.T("dup_remove"), variable=var,
                        font=app.f_small, width=90, corner_radius=7,
                    ).grid(row=0, column=1, padx=(8, 0))

    def _cleanup(self) -> None:
        app = self.app
        selected = {entry_id for entry_id, var in self._vars.items() if var.get()}
        if not selected:
            app._toast("error", "dup_no_selection")
            return
        if not messagebox.askyesno(app.T("dup_title"), app.T("dup_confirm", count=len(selected))):
            return
        trimmed: list[DuplicateGroup] = []
        for group in self.groups:
            entries = [
                entry for entry in group.entries
                if str(entry.get("id") or "") == group.keep_id
                or str(entry.get("id") or "") in selected
            ]
            trimmed.append(DuplicateGroup(
                key=group.key, reason=group.reason, entries=entries,
                wasted_bytes=group.wasted_bytes, keep_id=group.keep_id,
            ))
        result = cleanup_duplicates(trimmed, app.history, delete_files=True)
        freed = sum(
            int(entry.get("size") or 0)
            for group in trimmed for entry in group.entries
            if str(entry.get("id") or "") in selected
        )
        app._refresh_history()
        app._update_dynamic_stats()
        app._toast("success", "dup_done", count=result["history"], size=format_bytes(freed))
        self._scan()
