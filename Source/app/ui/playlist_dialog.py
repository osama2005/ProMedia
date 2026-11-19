"""Modal dialog used to pick specific videos from a playlist."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.core.models import MediaEntry, MediaInfo
from app.i18n import is_rtl, translate
from app.utils.helpers import format_duration, truncate


class PlaylistDialog(ctk.CTkToplevel):
    """Checkbox list of playlist entries with select-all / select-none."""

    def __init__(self, master, info: MediaInfo, on_start) -> None:
        super().__init__(master)
        self.app = master
        self.info = info
        self.on_start = on_start
        self.vars: list[tuple[tk.BooleanVar, MediaEntry]] = []
        self._rtl = is_rtl(master.settings.language)

        # Raw title: the OS draws Arabic in the title bar correctly.
        self.title(translate(master.settings.language, "playlist_dialog_title"))
        self.geometry("700x620")
        self.minsize(560, 440)
        self.configure(fg_color=master.palette_tokens["bg"])
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=master.T("playlist_dialog_title"),
            font=master.f_h1,
            anchor=master.text_anchor,
            justify=master.text_justify,
        ).grid(row=0, column=0, sticky="ew")
        self.subtitle = ctk.CTkLabel(
            header,
            text=master.T("playlist_dialog_subtitle", count=len(info.entries)),
            font=master.f_small,
            text_color=master.color_muted,
            anchor=master.text_anchor,
            justify=master.text_justify,
        )
        self.subtitle.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.playlist_title = ctk.CTkLabel(
            header,
            text=master.S(truncate(info.title, 90)),
            font=master.f_body_bold,
            anchor=master.text_anchor,
            justify=master.text_justify,
        )
        self.playlist_title.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 6))
        toolbar.grid_columnconfigure(self._column(2, 3), weight=1)

        self.select_all_btn = ctk.CTkButton(
            toolbar, text=master.T("select_all"), width=110, height=30,
            font=master.f_small,
            fg_color=master.palette_tokens["accent"],
            hover_color=master.palette_tokens["accent_hover"],
            command=lambda: self._set_all(True),
        )
        self.select_all_btn.grid(
            row=0, column=self._column(0, 3), padx=self._pad(0, 6)
        )
        self.select_none_btn = ctk.CTkButton(
            toolbar, text=master.T("select_none"), width=110, height=30,
            font=master.f_small,
            fg_color=master.palette_tokens["soft_button"],
            hover_color=master.palette_tokens["soft_hover"],
            text_color=master.palette_tokens["soft_text"],
            command=lambda: self._set_all(False),
        )
        self.select_none_btn.grid(
            row=0, column=self._column(1, 3), padx=self._pad(6, 0)
        )

        self.count_label = ctk.CTkLabel(
            toolbar, text="", font=master.f_small,
            text_color=master.color_muted,
            anchor=master.text_anchor,
            justify=master.text_justify,
        )
        self.count_label.grid(
            row=0, column=self._column(2, 3), sticky="ew"
        )

        self.list_frame = ctk.CTkScrollableFrame(
            self, fg_color=master.palette_tokens["card"], corner_radius=12
        )
        self.list_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 10))
        self.list_frame.grid_columnconfigure(0, weight=1)

        for index, entry in enumerate(info.entries):
            variable = tk.BooleanVar(value=True)
            label = f"{index + 1}. {truncate(entry.title, 78)}"
            if entry.duration:
                label += f"  ·  {format_duration(entry.duration)}"

            row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row.grid(row=index, column=0, sticky="ew", padx=10, pady=3)
            text_column = self._column(0, 2)
            check_column = self._column(1, 2)
            row.grid_columnconfigure(text_column, weight=1)

            checkbox = ctk.CTkCheckBox(
                row,
                text="",
                variable=variable,
                width=24,
                checkbox_width=20,
                checkbox_height=20,
                fg_color=master.palette_tokens["accent"],
                hover_color=master.palette_tokens["accent_hover"],
                border_color=master.palette_tokens["muted"],
                command=self._update_count,
            )
            checkbox.grid(row=0, column=check_column, padx=self._pad(0, 8))

            text = ctk.CTkLabel(
                row,
                text=master.S(label),
                font=master.f_small,
                anchor=master.text_anchor,
                justify=master.text_justify,
                wraplength=520,
            )
            text.grid(row=0, column=text_column, sticky="ew", padx=self._pad(8, 0))
            text.bind(
                "<Button-1>",
                lambda _event, var=variable: self._toggle_variable(var),
            )
            self.vars.append((variable, entry))

        if len(info.entries) >= 300:
            note = ctk.CTkLabel(
                self,
                text=master.T("playlist_limited", count=len(info.entries)),
                font=master.f_small,
                text_color=master.palette_tokens["warn"],
                anchor=master.text_anchor,
                justify=master.text_justify,
            )
            note.grid(row=3, column=0, sticky="ew", padx=20)

        self.hint = ctk.CTkLabel(
            self, text="", font=master.f_small,
            text_color=master.palette_tokens["danger"],
            anchor=master.text_anchor,
            justify=master.text_justify,
        )
        self.hint.grid(row=4, column=0, sticky="ew", padx=20, pady=(4, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=5, column=0, sticky="ew", padx=20, pady=(6, 16))
        footer.grid_columnconfigure(self._column(0, 3), weight=1)

        self.start_btn = ctk.CTkButton(
            footer,
            text=master.T("start_download"),
            height=40,
            font=master.f_body_bold,
            fg_color=master.palette_tokens["accent"],
            hover_color=master.palette_tokens["accent_hover"],
            command=self._start,
        )
        self.start_btn.grid(
            row=0, column=self._column(1, 3), padx=self._pad(0, 6)
        )
        self.cancel_btn = ctk.CTkButton(
            footer,
            text=master.T("cancel"),
            height=40,
            font=master.f_body,
            fg_color=master.palette_tokens["soft_button"],
            hover_color=master.palette_tokens["soft_hover"],
            text_color=master.palette_tokens["soft_text"],
            command=self.destroy,
        )
        self.cancel_btn.grid(
            row=0, column=self._column(2, 3), padx=self._pad(6, 0)
        )

        self._update_count()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.after(80, self._activate)

    # ------------------------------------------------------------------
    def _column(self, logical: int, total: int) -> int:
        return total - 1 - logical if self._rtl else logical

    def _pad(self, start: int, end: int) -> tuple[int, int]:
        return (end, start) if self._rtl else (start, end)

    def _activate(self) -> None:
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

    def _toggle_variable(self, variable: tk.BooleanVar) -> None:
        variable.set(not variable.get())
        self._update_count()

    def _set_all(self, value: bool) -> None:
        for variable, _entry in self.vars:
            variable.set(value)
        self._update_count()

    def _update_count(self) -> None:
        selected = sum(1 for variable, _entry in self.vars if variable.get())
        self.count_label.configure(
            text=self.app.T("selected_count", count=selected)
        )
        if selected:
            self.hint.configure(text="")

    def _start(self) -> None:
        selected = [entry for variable, entry in self.vars if variable.get()]
        if not selected:
            self.hint.configure(text=self.app.T("err_choose_items"))
            return
        self.destroy()
        self.on_start(selected)
