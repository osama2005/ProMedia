"""Modal dialog for pasting a batch of links and adding them to the queue.

The dialog is intentionally self-contained: it only extracts/validates URLs
and hands them back to the app through ``on_add``.  All download policy
(mode, quality, priority, schedule, duplicate checks) stays in the app.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.i18n import is_rtl
from app.utils.helpers import extract_urls


class LinkInboxDialog(ctk.CTkToplevel):
    """A persistent, multi-line inbox for links waiting to be downloaded."""

    def __init__(self, master, on_add) -> None:
        super().__init__(master)
        self.app = master
        self.on_add = on_add
        self._rtl = is_rtl(master.settings.language)
        tokens = master.palette_tokens

        self.title(master.T("link_inbox_title"))
        self.geometry("660x540")
        self.minsize(520, 420)
        self.resizable(True, True)
        self.configure(fg_color=tokens["bg"])
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda _event: self._on_close())

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ---- header ----------------------------------------------------
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text=master.T("link_inbox_title"),
            font=master.f_h1,
            anchor=master.text_anchor,
            justify=master.text_justify,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header,
            text=master.T("link_inbox_hint"),
            font=master.f_small,
            text_color=tokens["muted"],
            anchor=master.text_anchor,
            justify=master.text_justify,
            wraplength=600,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

        # ---- text box --------------------------------------------------
        self.textbox = ctk.CTkTextbox(
            self,
            font=master.f_body,
            wrap="word",
            corner_radius=10,
            fg_color=tokens["card"],
            border_width=1,
            border_color=tokens["border"],
        )
        self.textbox.grid(row=2, column=0, sticky="nsew", padx=18, pady=8)
        self.textbox.insert("1.0", master.settings.link_inbox)

        # Live counter, updated on text changes and after paste/clear.
        self.count_label = ctk.CTkLabel(
            self,
            text="",
            font=master.f_small_bold,
            text_color=tokens["accent"],
            anchor=master.text_anchor,
            justify=master.text_justify,
        )
        self.count_label.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 6))
        try:
            inner = self.textbox._textbox
            inner.bind("<KeyRelease>", lambda _event: self._update_count(), add="+")
            inner.bind("<ButtonRelease-2>", lambda _event: self._update_count(), add="+")
        except Exception:
            pass

        # ---- actions ---------------------------------------------------
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 16))
        actions.grid_columnconfigure(0, weight=1)
        side = master._start_side()

        self.add_btn = ctk.CTkButton(
            actions,
            text=master.T("link_inbox_add"),
            width=140,
            height=38,
            corner_radius=10,
            font=master.f_small_bold,
            fg_color=tokens["accent"],
            hover_color=tokens["accent_hover"],
            command=self._add,
        )
        self.add_btn.pack(side=side, padx=(0, 8))

        self.paste_btn = ctk.CTkButton(
            actions,
            text=master.T("link_inbox_paste"),
            width=140,
            height=38,
            corner_radius=10,
            font=master.f_small,
            fg_color=tokens["soft_button"],
            hover_color=tokens["soft_hover"],
            text_color=tokens["soft_text"],
            command=self._paste,
        )
        self.paste_btn.pack(side=side, padx=(0, 8))

        self.clear_btn = ctk.CTkButton(
            actions,
            text=master.T("link_inbox_clear"),
            width=110,
            height=38,
            corner_radius=10,
            font=master.f_small,
            fg_color=tokens["soft_button"],
            hover_color=tokens["soft_hover"],
            text_color=tokens["soft_text"],
            command=self._clear,
        )
        self.clear_btn.pack(side=side)

        self._update_count()
        self.after(80, self._centre)

    # ------------------------------------------------------------------
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

    def _text(self) -> str:
        return self.textbox.get("1.0", "end-1c")

    def _update_count(self) -> None:
        count = len(extract_urls(self._text()))
        if count:
            text = self.app.T("link_inbox_count", count=count)
        else:
            text = self.app.T("link_inbox_empty")
        self.count_label.configure(text=text)

    def _paste(self) -> None:
        try:
            text = self.master.clipboard_get()
        except tk.TclError:
            return
        if not text:
            return
        current = self._text().strip()
        merged = (current + "\n" + text.strip()) if current else text.strip()
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", merged)
        self._update_count()

    def _clear(self) -> None:
        self.textbox.delete("1.0", "end")
        self._persist("")
        self._update_count()

    def _add(self) -> None:
        urls = extract_urls(self._text())
        if not urls:
            self.app._toast("error", "link_inbox_no_valid")
            return
        added, skipped = self.on_add(urls)
        if added:
            self.textbox.delete("1.0", "end")
            self._persist("")
            self.app._toast("success", "link_inbox_added", count=added)
            if skipped:
                self.app._toast("info", "link_inbox_skipped", count=skipped)
        elif skipped:
            self.app._toast("info", "link_inbox_skipped", count=skipped)
        else:
            self.app._toast("error", "link_inbox_no_valid")
        self._update_count()

    def _persist(self, text: str) -> None:
        self.app.settings.link_inbox = text
        self.app.config.save(self.app.settings)

    def _on_close(self) -> None:
        try:
            self._persist(self._text())
        except Exception:
            pass
        self.destroy()
