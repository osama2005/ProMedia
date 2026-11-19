"""Dialog for creating download groups and controlling group membership."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
from tkinter import messagebox

from app.core.groups import GROUP_COLORS


class GroupsDialog(ctk.CTkToplevel):
    """Manage groups; membership is matched by download URL."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.app = master
        tokens = master.palette_tokens
        self._colour = tk.StringVar(value=GROUP_COLORS[0])

        self.title(master.T("groups_title"))
        self.geometry("660x580")
        self.minsize(560, 460)
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
            header, text=master.T("groups_title"), font=master.f_h1,
            anchor=master.text_anchor, justify=master.text_justify,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            header, text=master.T("groups_hint"), font=master.f_small,
            text_color=tokens["muted"], anchor=master.text_anchor,
            justify=master.text_justify, wraplength=610,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

        create = ctk.CTkFrame(self, fg_color="transparent")
        create.grid(row=1, column=0, sticky="ew", padx=18, pady=(6, 4))
        create.grid_columnconfigure(0, weight=1)
        self.name_var = tk.StringVar(value="")
        ctk.CTkEntry(
            create, textvariable=self.name_var,
            placeholder_text=master.T("groups_name"), height=34,
            font=master.f_small, corner_radius=9,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkOptionMenu(
            create, variable=self._colour, values=list(GROUP_COLORS),
            width=64, height=34, font=master.f_small, corner_radius=9,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            create, text=master.T("groups_add"), width=110, height=34,
            font=master.f_small_bold, corner_radius=9,
            fg_color=tokens["accent"], hover_color=tokens["accent_hover"],
            command=self._add_group,
        ).grid(row=0, column=2, sticky="e")

        assign = ctk.CTkFrame(self, fg_color="transparent")
        assign.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 4))
        assign.grid_columnconfigure(0, weight=1)
        self.url_var = tk.StringVar(value="")
        ctk.CTkEntry(
            assign, textvariable=self.url_var,
            placeholder_text="https://…", height=30,
            font=master.f_small, corner_radius=8,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.group_menu = ctk.CTkOptionMenu(
            assign, values=[master.T("groups_unassigned")],
            width=150, height=30, font=master.f_small, corner_radius=8,
        )
        self.group_menu.grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            assign, text=master.T("groups_assign"), width=100, height=30,
            font=master.f_small, corner_radius=8,
            fg_color=tokens["soft_button"], hover_color=tokens["soft_hover"],
            text_color=tokens["soft_text"], command=self._assign,
        ).grid(row=0, column=2, sticky="e")

        self.scroll = ctk.CTkScrollableFrame(
            self, fg_color=tokens["card"], corner_radius=12
        )
        self.scroll.grid(row=3, column=0, sticky="nsew", padx=18, pady=4)
        self.scroll.grid_columnconfigure(0, weight=1)

        self.refresh()
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

    def _group_choices(self) -> tuple[list[str], dict[str, str]]:
        groups = self.app.groups.groups()
        labels = [self.app.T("groups_unassigned")] + [g["name"] for g in groups]
        lookup = {self.app.T("groups_unassigned"): ""}
        lookup.update({g["name"]: g["id"] for g in groups})
        return labels, lookup

    def refresh(self) -> None:
        app = self.app
        for child in list(self.scroll.winfo_children()):
            child.destroy()
        groups = app.groups.groups()
        labels, self._lookup = self._group_choices()
        current = self.group_menu.get()
        self.group_menu.configure(values=labels)
        self.group_menu.set(current if current in labels else labels[0])

        if not groups:
            ctk.CTkLabel(
                self.scroll, text=app.T("groups_empty"), font=app.f_body,
                text_color=app.palette_tokens["muted"],
                anchor=app.text_anchor, justify=app.text_justify,
            ).grid(row=0, column=0, sticky="ew", padx=16, pady=30)
            return

        summaries = app.groups.summary(app.manager.snapshots())
        for index, item in enumerate(summaries):
            card = ctk.CTkFrame(
                self.scroll, fg_color=app.palette_tokens["soft_button"],
                corner_radius=10,
            )
            card.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                card, text="", fg_color=item["color"], width=10, height=10,
                corner_radius=5,
            ).grid(row=0, column=0, sticky="w", padx=(12, 6), pady=(10, 0))
            ctk.CTkLabel(
                card, text=item["name"], font=app.f_small_bold,
                anchor=app.text_anchor, justify=app.text_justify,
            ).grid(row=0, column=1, sticky="ew", pady=(8, 0))
            ctk.CTkLabel(
                card, text=app.T("groups_summary", done=item["done"], total=item["total"]),
                font=app.f_small, text_color=app.palette_tokens["muted"],
            ).grid(row=0, column=2, padx=(6, 12), pady=(8, 0))

            bar = ctk.CTkProgressBar(card, height=8, corner_radius=4)
            bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=12, pady=(4, 2))
            bar.set(item["progress"] / 100)

            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=(2, 10))
            for col, (key, command) in enumerate((
                ("groups_start", lambda gid=item["id"]: self._group_action(gid, "start")),
                ("groups_pause", lambda gid=item["id"]: self._group_action(gid, "pause")),
                ("groups_rename", lambda gid=item["id"], name=item["name"]: self._rename(gid, name)),
                ("groups_remove", lambda gid=item["id"]: self._remove(gid)),
            )):
                ctk.CTkButton(
                    actions, text=app.T(key), height=26, width=90,
                    font=app.f_small, corner_radius=7,
                    fg_color=app.palette_tokens["soft_button"],
                    hover_color=app.palette_tokens["soft_hover"],
                    text_color=app.palette_tokens["soft_text"],
                    command=command,
                ).grid(row=0, column=col, padx=(0, 6))

    def _add_group(self) -> None:
        name = self.name_var.get()
        if not str(name or "").strip():
            return
        group = self.app.groups.add_group(name, self._colour.get())
        if group:
            self.name_var.set("")
            self.app._toast("success", "groups_created")
            self.refresh()
            self.app._refresh_group_choices()

    def _assign(self) -> None:
        url = str(self.url_var.get() or "").strip()
        group_id = self._lookup.get(self.group_menu.get(), "")
        if not url:
            return
        self.app.groups.assign(url, group_id)
        name = self.app.groups.group_name(group_id) if group_id else self.app.T("groups_unassigned")
        self.app._toast("success", "groups_assigned", name=name)
        self.url_var.set("")

    def _group_action(self, group_id: str, action: str) -> None:
        count = self.app.manager.group_action(group_id, action)
        self.app._toast("info", "groups_summary", done=count, total=count)
        self.refresh()

    def _rename(self, group_id: str, current: str) -> None:
        name = ctk.CTkInputDialog(
            text=self.app.T("groups_name"),
            title=self.app.T("groups_rename"),
        ).get_input()
        if name and self.app.groups.rename_group(group_id, name):
            self.refresh()
            self.app._refresh_group_choices()

    def _remove(self, group_id: str) -> None:
        if not messagebox.askyesno(self.app.T("groups_title"), self.app.T("groups_remove") + "?"):
            return
        self.app.groups.remove_group(group_id)
        self.app._toast("success", "groups_deleted")
        self.refresh()
        self.app._refresh_group_choices()
