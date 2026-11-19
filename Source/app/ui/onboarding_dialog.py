"""First-run guided tour shown once after installation."""

from __future__ import annotations

import customtkinter as ctk

ONBOARDING_STEPS = 4


class OnboardingDialog(ctk.CTkToplevel):
    """A small four-card tour; completion is persisted in settings."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.app = master
        tokens = master.palette_tokens
        self.step = 0
        self.title(master.T("onb_title"))
        self.geometry("520x380")
        self.resizable(False, False)
        self.configure(fg_color=tokens["bg"])
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._finish)
        self.bind("<Escape>", lambda _event: self._finish())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self, text=master.T("onb_title"), font=master.f_h2,
            anchor=master.text_anchor, justify=master.text_justify,
        ).grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 10))

        self.card = ctk.CTkFrame(
            self, fg_color=tokens["card"], corner_radius=14
        )
        self.card.grid(row=1, column=0, sticky="nsew", padx=22, pady=4)
        self.card.grid_columnconfigure(0, weight=1)

        self.step_label = ctk.CTkLabel(
            self, text="", font=master.f_small_bold,
            text_color=tokens["muted"], anchor=master.text_anchor,
        )
        self.step_label.grid(row=2, column=0, sticky="ew", padx=22, pady=(4, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=22, pady=(6, 18))
        actions.grid_columnconfigure(0, weight=1)
        side = master._start_side()
        self.skip_btn = ctk.CTkButton(
            actions, text=master.T("onb_skip"), width=80, height=34,
            font=master.f_small, corner_radius=9,
            fg_color=tokens["soft_button"], hover_color=tokens["soft_hover"],
            text_color=tokens["soft_text"], command=self._finish,
        )
        self.skip_btn.pack(side=side, padx=(0, 8))
        self.back_btn = ctk.CTkButton(
            actions, text=master.T("onb_back"), width=90, height=34,
            font=master.f_small, corner_radius=9,
            fg_color=tokens["soft_button"], hover_color=tokens["soft_hover"],
            text_color=tokens["soft_text"], command=self._back,
        )
        self.back_btn.pack(side=side, padx=(0, 8))
        self.next_btn = ctk.CTkButton(
            actions, text=master.T("onb_next"), width=110, height=34,
            font=master.f_small_bold, corner_radius=9,
            fg_color=tokens["accent"], hover_color=tokens["accent_hover"],
            command=self._next,
        )
        self.next_btn.pack(side=side)

        self._render()
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

    def _render(self) -> None:
        app = self.app
        for child in list(self.card.winfo_children()):
            child.destroy()
        number = self.step + 1
        ctk.CTkLabel(
            self.card, text=app.T(f"onb_{number}_title"),
            font=app.f_h2, anchor=app.text_anchor, justify=app.text_justify,
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 8))
        ctk.CTkLabel(
            self.card, text=app.T(f"onb_{number}_body"),
            font=app.f_body, text_color=app.palette_tokens["muted"],
            anchor=app.text_anchor, justify=app.text_justify, wraplength=440,
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))
        self.step_label.configure(text=f"{number} / {ONBOARDING_STEPS}")
        self.back_btn.configure(state="normal" if self.step else "disabled")
        self.next_btn.configure(
            text=app.T("onb_finish") if self.step == ONBOARDING_STEPS - 1 else app.T("onb_next")
        )

    def _next(self) -> None:
        if self.step >= ONBOARDING_STEPS - 1:
            self._finish()
            return
        self.step += 1
        self._render()

    def _back(self) -> None:
        if self.step:
            self.step -= 1
            self._render()

    def _finish(self) -> None:
        self.app.settings.onboarding_done = True
        self.app.config.save(self.app.settings)
        self.destroy()
