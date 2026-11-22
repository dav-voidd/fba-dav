"""📊 Excel tab: paste links + sub IDs, get the ready-made affiliate sheet."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from ..products import excel
from . import theme
from .preview import open_path
from .widgets import Card, Eyebrow, GhostButton, PrimaryButton, TextButton


class ExcelPage(ctk.CTkFrame):
    def __init__(self, master, *, get_sub_ids: Callable[[], list[str]],
                 default_name: Callable[[], str], output_dir: Callable[[], str]):
        super().__init__(master, fg_color="transparent")
        self._get_sub_ids = get_sub_ids
        self._default_name = default_name
        self._output_dir = output_dir
        self._saved: Path | None = None
        self.grid_columnconfigure((0, 1), weight=1, uniform="col")
        self.grid_rowconfigure(1, weight=1)

        # --- header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(head, text="Excel sheet", font=theme.font(18, "bold"), text_color=theme.TEXT).pack(side="left")
        self._save = PrimaryButton(head, "Create Excel file", self.create, width=180, height=36)
        self._save.pack(side="right")
        self._open = GhostButton(head, "Open file", self._open_file, width=100)
        self._open.pack(side="right", padx=(0, 8))
        self._open.configure(state="disabled")
        self._name = ctk.CTkEntry(head, width=170, height=32, fg_color=theme.SURFACE,
                                  border_color=theme.BORDER_STRONG, text_color=theme.TEXT, font=theme.mono(12))
        self._name.pack(side="right", padx=(0, 8))
        Eyebrow(head, "File name").pack(side="right", padx=(0, 8))

        # --- two boxes
        self._links = self._box(0, "Links", "One link per line (s.shopee.ph/...)", self._paste_links)
        self._subs = self._box(1, "Sub IDs", "One sub ID per line, same order as the links", self._paste_subs,
                               extra=("Use my sub IDs", self._fill_sub_ids))

        # --- status
        self._status = ctk.CTkLabel(self, text="", font=theme.font(12), text_color=theme.TEXT_MUTED, anchor="w")
        self._status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 12))
        self.refresh()

    def _box(self, column: int, title: str, hint: str, on_paste, extra=None):
        card = Card(self)
        card.grid(row=1, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (8, 0))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=theme.PAD, pady=(14, 6))
        ctk.CTkLabel(top, text=title, font=theme.font(14, "bold"), text_color=theme.TEXT).pack(side="left")
        count = ctk.CTkLabel(top, text="0", font=theme.mono(12), text_color=theme.TEXT_FAINT)
        count.pack(side="left", padx=8)
        TextButton(top, "Clear", lambda: (box.delete("1.0", "end"), self.refresh())).pack(side="right")
        TextButton(top, "Paste", on_paste).pack(side="right")
        if extra:
            TextButton(top, extra[0], extra[1]).pack(side="right")
        box = ctk.CTkTextbox(card, fg_color=theme.BACKGROUND, border_color=theme.BORDER, border_width=1,
                             corner_radius=10, font=theme.mono(12), text_color=theme.TEXT, wrap="none")
        box.grid(row=1, column=0, sticky="nsew", padx=theme.PAD)
        box.bind("<KeyRelease>", lambda _e: self.refresh())
        ctk.CTkLabel(card, text=hint, font=theme.font(11), text_color=theme.TEXT_FAINT,
                     anchor="w").grid(row=2, column=0, sticky="ew", padx=theme.PAD, pady=(6, 12))
        box.count_label = count
        return box

    # ---------------------------------------------------------------- actions

    def refresh(self) -> None:
        if not self._name.get().strip():
            self._name.insert(0, self._default_name())
        links, subs = excel.lines(self._links.get("1.0", "end")), excel.lines(self._subs.get("1.0", "end"))
        self._links.count_label.configure(text=str(len(links)))
        self._subs.count_label.configure(text=str(len(subs)))
        if links and subs and len(links) != len(subs):
            self._say(f"⚠ {len(links)} links but {len(subs)} sub IDs. Row 1 pairs with row 1, and so on.", theme.DANGER)
        elif links or subs:
            self._say(f"{max(len(links), len(subs))} rows ready.", theme.TEXT_MUTED)
        else:
            self._say("Paste your links on the left and sub IDs on the right.", theme.TEXT_MUTED)

    def _say(self, text: str, color: str) -> None:
        self._status.configure(text=text, text_color=color)

    def _paste_into(self, box) -> None:
        try:
            text = self.clipboard_get()
        except Exception:
            return
        box.delete("1.0", "end")
        box.insert("1.0", text.strip() + "\n")
        self.refresh()

    def _paste_links(self) -> None:
        self._paste_into(self._links)

    def _paste_subs(self) -> None:
        self._paste_into(self._subs)

    def _fill_sub_ids(self) -> None:
        ids = self._get_sub_ids()
        if not ids:
            self._say("No sub IDs yet. Scan on the Sub IDs tab first.", theme.DANGER)
            return
        self._subs.delete("1.0", "end")
        self._subs.insert("1.0", "\n".join(ids) + "\n")
        self.refresh()

    def create(self) -> None:
        links, subs = excel.lines(self._links.get("1.0", "end")), excel.lines(self._subs.get("1.0", "end"))
        if not links and not subs:
            self._say("Nothing to save yet: paste links and sub IDs first.", theme.DANGER)
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Save Excel file", defaultextension=".xlsx",
            initialdir=self._output_dir(), initialfile=excel.safe_filename(self._name.get()),
            filetypes=[("Excel file", "*.xlsx")])
        if not path:
            return
        try:
            rows = excel.build(links, subs, Path(path))
        except PermissionError:
            self._say("Can't save: that file is open in Excel. Close it and try again.", theme.DANGER)
            return
        except Exception as exc:
            self._say(f"Couldn't save: {exc}", theme.DANGER)
            return
        self._saved = Path(path)
        self._open.configure(state="normal")
        self._say(f"Saved {rows} rows to {self._saved.name} ✓", theme.ACCENT_TEXT)

    def _open_file(self) -> None:
        if self._saved and self._saved.exists():
            open_path(str(self._saved))
