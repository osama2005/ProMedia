"""A small dialog that renders a QR code for the current media URL."""

from __future__ import annotations

import customtkinter as ctk

from app.i18n import is_rtl, translate
from app.utils.logger import log


class QRDialog(ctk.CTkToplevel):
    """Shows a QR code image for *text* (usually the URL in the entry)."""

    def __init__(self, master, text: str, title_key: str = "qr_title") -> None:
        super().__init__(master)
        self.app = master
        self.text = text
        self._rtl = is_rtl(master.settings.language)
        self._image = None

        self.title(translate(master.settings.language, title_key))
        self.geometry("420x500")
        self.resizable(False, False)
        self.configure(fg_color=master.palette_tokens["bg"])
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self,
            text=master.T(title_key),
            font=master.f_h1,
            anchor=master.text_anchor,
            justify=master.text_justify,
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 4))

        self.url_label = ctk.CTkLabel(
            self,
            text=master.S(text if len(text) <= 90 else text[:88] + "…"),
            font=master.f_small,
            text_color=master.color_muted,
            wraplength=360,
            anchor=master.text_anchor,
            justify=master.text_justify,
        )
        self.url_label.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))

        self.holder = ctk.CTkFrame(
            self,
            fg_color=("#FFFFFF", "#FFFFFF"),
            corner_radius=14,
            width=320,
            height=320,
        )
        self.holder.grid(row=2, column=0, padx=20, pady=6)
        self.holder.grid_propagate(False)

        self.hint = ctk.CTkLabel(
            self,
            text="",
            font=master.f_small,
            text_color=master.palette_tokens["muted"],
            wraplength=360,
            anchor=master.text_anchor,
            justify=master.text_justify,
        )
        self.hint.grid(row=3, column=0, sticky="ew", padx=20, pady=(6, 0))

        ctk.CTkButton(
            self,
            text=master.T("close"),
            height=38,
            font=master.f_body,
            fg_color=master.palette_tokens["accent"],
            hover_color=master.palette_tokens["accent_hover"],
            command=self.destroy,
        ).grid(row=4, column=0, sticky="ew", padx=20, pady=(10, 18))

        self._render()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.after(80, self._activate)

    # ------------------------------------------------------------------
    def _render(self) -> None:
        try:
            import qrcode
            from PIL import Image

            qr = qrcode.QRCode(box_size=8, border=2)
            qr.add_data(self.text)
            qr.make(fit=True)
            image = qr.make_image(fill_color="#000000", back_color="#FFFFFF")
            image = image.convert("RGB")
            image = image.resize((300, 300), Image.LANCZOS)
            self._image = ctk.CTkImage(
                light_image=image, dark_image=image, size=(300, 300)
            )
            ctk.CTkLabel(self.holder, text="", image=self._image).place(
                relx=0.5, rely=0.5, anchor="center"
            )
        except Exception as exc:  # optional dependency or bad data
            log.warning("Could not render QR code: %s", exc)
            self.hint.configure(text=self.app.T("qr_unavailable"))

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
