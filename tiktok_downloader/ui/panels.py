"""Regions of the main window: top bar, composer, queue and status bar."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import customtkinter as ctk

from .. import __app_name__, __version__
from ..models import QueueItem
from . import theme
from .widgets import (Card, Divider, Eyebrow, GhostButton, PrimaryButton, QueueRow,
                      Segmented, Switch, TextButton)

Action = Callable[[], None]

QUALITY_LABELS = {"balanced": "Balanced", "max": "Max quality"}
QUALITY_HINTS = {
    "balanced": "~4–5 MB per video · H.264 · plays on every device",
    "max": "Largest file TikTok has · may need the HEVC codec on Windows",
}


class TopBar(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        logo = ctk.CTkFrame(self, width=34, height=34, corner_radius=9, fg_color=theme.ACCENT)
        logo.pack(side="left")
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="♪", font=theme.font(18, "bold"), text_color="#FFFFFF").pack(expand=True)

        ctk.CTkLabel(self, text=__app_name__, font=theme.font(17, "bold"),
                     text_color=theme.TEXT).pack(side="left", padx=(12, 8))
        ctk.CTkLabel(self, text=f"v{__version__}", font=theme.font(11, "bold"), height=22,
                     corner_radius=11, fg_color=theme.SURFACE_RAISED,
                     text_color=theme.TEXT_MUTED).pack(side="left", ipadx=8)

        self._stats = ctk.CTkLabel(self, font=theme.font(12), text_color=theme.TEXT_MUTED)
        self._stats.pack(side="right")
        self._update: ctk.CTkButton | None = None
        self.set_stats(0, 0, 0)

    def show_update(self, text: str, on_click: Action | None = None) -> None:
        """An accent pill next to the title, e.g. '⬆ v4.3.0 available, Update now'."""
        if self._update is None:
            self._update = ctk.CTkButton(
                self, text=text, command=on_click, height=28, corner_radius=14,
                fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, text_color="#FFFFFF",
                text_color_disabled="#FFFFFF", font=theme.font(12, "bold"))
            self._update.pack(side="left", padx=(12, 0))
        self._update.configure(text=text, state="normal" if on_click else "disabled")
        if on_click:
            self._update.configure(command=on_click)

    def set_stats(self, total: int, done: int, failed: int) -> None:
        parts = [f"{total} queued", f"{done} saved"] + ([f"{failed} failed"] if failed else [])
        self._stats.configure(text="   ·   ".join(parts))


class Composer(Card):
    """The hero: paste box, one primary action, and the three settings that matter."""

    def __init__(self, master, *, output_dir: ctk.StringVar, numbered: ctk.BooleanVar,
                 quality: ctk.StringVar, auto_scan: ctk.BooleanVar, on_text_changed: Action, on_paste: Action, on_clear: Action,
                 on_download: Action, on_change_folder: Action, on_open_folder: Action):
        super().__init__(master)
        self.grid_columnconfigure(0, weight=1)
        pad = theme.PAD
        self._output_dir = output_dir

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=pad, pady=(pad - 6, 6))
        ctk.CTkLabel(head, text="Paste TikTok links", font=theme.font(15, "bold"),
                     text_color=theme.TEXT).pack(side="left")
        self._count = ctk.CTkLabel(head, font=theme.font(12), text_color=theme.TEXT_FAINT)
        self._count.pack(side="right")

        self.textbox = ctk.CTkTextbox(
            self, height=78, fg_color=theme.BACKGROUND, border_color=theme.BORDER, border_width=1,
            corner_radius=10, font=theme.mono(12), text_color=theme.TEXT, wrap="none",
        )
        self.textbox.grid(row=1, column=0, sticky="ew", padx=pad)
        self.textbox.bind("<KeyRelease>", lambda _e: on_text_changed())

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=pad, pady=10)
        GhostButton(actions, "Paste", on_paste, width=72).pack(side="left")
        TextButton(actions, "Clear", on_clear).pack(side="left", padx=6)
        self._download = PrimaryButton(actions, "Download", on_download, width=220)
        self._download.pack(side="right")

        Divider(self).grid(row=3, column=0, sticky="ew", padx=pad)

        settings = ctk.CTkFrame(self, fg_color="transparent")
        settings.grid(row=4, column=0, sticky="ew", padx=pad, pady=(10, pad - 6))
        settings.grid_columnconfigure(1, weight=1)

        quality_box = ctk.CTkFrame(settings, fg_color="transparent")
        quality_box.grid(row=0, column=0, sticky="w")
        Eyebrow(quality_box, "Quality").pack(anchor="w")
        self._quality_label = ctk.StringVar(value=QUALITY_LABELS.get(quality.get(), "Balanced"))

        def choose(label: str) -> None:
            key = next(k for k, v in QUALITY_LABELS.items() if v == label)
            quality.set(key)
            self._quality_hint.configure(text=QUALITY_HINTS[key])

        quality_row = ctk.CTkFrame(quality_box, fg_color="transparent")
        quality_row.pack(anchor="w", pady=(4, 0))
        Segmented(quality_row, list(QUALITY_LABELS.values()), self._quality_label, choose).pack(side="left")
        self._quality_hint = ctk.CTkLabel(quality_row, text=QUALITY_HINTS.get(quality.get(), ""),
                                          font=theme.font(11), text_color=theme.TEXT_FAINT, anchor="w")
        self._quality_hint.pack(side="left", padx=(10, 0))

        folder_box = ctk.CTkFrame(settings, fg_color="transparent")
        folder_box.grid(row=0, column=1, sticky="w", padx=(32, 0))
        Eyebrow(folder_box, "Save to").pack(anchor="w")
        folder_row = ctk.CTkFrame(folder_box, fg_color="transparent")
        folder_row.pack(anchor="w", pady=(4, 0))
        self._folder = ctk.CTkLabel(folder_row, font=theme.font(12), text_color=theme.TEXT, anchor="w")
        self._folder.pack(side="left")
        TextButton(folder_row, "Change", on_change_folder).pack(side="left", padx=(8, 0))
        TextButton(folder_row, "Open", on_open_folder).pack(side="left")
        output_dir.trace_add("write", lambda *_: self._render_folder())
        self._render_folder()

        toggles = ctk.CTkFrame(settings, fg_color="transparent")
        toggles.grid(row=0, column=2, sticky="e")
        Switch(toggles, "Number files in order", numbered).pack(anchor="w", pady=(0, 6))
        Switch(toggles, "Scan products after download", auto_scan).pack(anchor="w")

        self.set_link_count(0)

    # ------------------------------------------------------------------ API

    def text(self) -> str:
        return self.textbox.get("1.0", "end")

    def append(self, text: str) -> None:
        self.textbox.insert("end", text)

    def clear(self) -> None:
        self.textbox.delete("1.0", "end")

    def set_link_count(self, count: int) -> None:
        self._count.configure(text=f"{count} link{'s' * (count != 1)} detected" if count
                              else "Links are detected automatically")
        if self._download.cget("state") != "disabled":
            self._download.configure(text=f"Download {count} video{'s' * (count != 1)}  →" if count
                                     else "Download  →")

    def set_running(self, running: bool, done: int = 0, total: int = 0) -> None:
        if running:
            self._download.configure(state="disabled", text=f"Downloading  {done} / {total}")
        else:
            self._download.configure(state="normal")
            self.set_link_count(0)

    def _render_folder(self) -> None:
        path = Path(self._output_dir.get() or ".")
        home = Path.home()
        try:
            shown = "~\\" + str(path.relative_to(home))
        except ValueError:
            shown = str(path)
        self._folder.configure(text=shown if len(shown) < 42 else "…" + shown[-40:])


class QueuePanel(Card):
    """Scrollable queue; rows are built a few per tick so big pastes never freeze the window."""

    BATCH = 4

    def __init__(self, master, *, on_select: Callable[[QueueItem], None],
                 on_clear_finished: Action, on_clear_all: Action):
        super().__init__(master)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._on_select = on_select
        self._rows: dict[int, QueueRow] = {}
        self._pending: list[QueueItem] = []
        self._selected: int | None = None

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=theme.PAD, pady=(theme.PAD - 4, 8))
        Eyebrow(head, "Queue").pack(side="left")
        TextButton(head, "Clear all", on_clear_all).pack(side="right")
        TextButton(head, "Clear finished", on_clear_finished).pack(side="right", padx=4)

        self._list = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                            scrollbar_button_color=theme.BORDER,
                                            scrollbar_button_hover_color=theme.BORDER_STRONG)
        self._list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._list.grid_columnconfigure(0, weight=1)

        self._empty = ctk.CTkFrame(self._list, fg_color="transparent")
        self._empty.grid(row=0, column=0, pady=70)
        ctk.CTkLabel(self._empty, text="↓", font=theme.font(30, "bold"),
                     text_color=theme.BORDER_STRONG).pack()
        ctk.CTkLabel(self._empty, text="Your queue is empty", font=theme.font(14, "bold"),
                     text_color=theme.TEXT_MUTED).pack(pady=(6, 2))
        ctk.CTkLabel(self._empty, text="Paste links above. They download one by one, in order.",
                     font=theme.font(12), text_color=theme.TEXT_FAINT).pack()

    def add_many(self, items: list[QueueItem]) -> None:
        start = not self._pending
        self._pending.extend(items)
        if start and self._pending:
            self._empty.grid_remove()
            self._build_pending()

    def _build_pending(self) -> None:
        for _ in range(self.BATCH):
            if not self._pending:
                return
            item = self._pending.pop(0)
            row = QueueRow(self._list, item, self._on_select)
            row.grid(row=item.index, column=0, sticky="ew", pady=1)
            self._rows[item.index] = row
        if self._pending:
            self.after(1, self._build_pending)

    def refresh(self, item: QueueItem) -> None:
        row = self._rows.get(item.index)
        if row is not None:
            row.render(item)

    def select(self, item: QueueItem) -> None:
        if self._selected in self._rows:
            self._rows[self._selected].set_selected(False)
        self._selected = item.index
        if item.index in self._rows:
            self._rows[item.index].set_selected(True)

    def scroll_to(self, item: QueueItem) -> None:
        """Scroll so ``item`` sits in the upper third of the list (after layout settles)."""
        self.after_idle(lambda: self._scroll_to(item))

    def _scroll_to(self, item: QueueItem) -> None:
        row = self._rows.get(item.index)
        if row is None:
            return
        canvas = self._list._parent_canvas  # CTkScrollableFrame's scrolling canvas
        content_height = self._list.winfo_height()
        if content_height <= 1:
            return
        target = row.winfo_y() - canvas.winfo_height() / 3
        canvas.yview_moveto(max(0.0, target / content_height))

    def remove(self, item: QueueItem) -> None:
        if item in self._pending:
            self._pending.remove(item)
        row = self._rows.pop(item.index, None)
        if row is not None:
            row.destroy()
        if not self._rows and not self._pending:
            self._empty.grid()


class StatusBar(Card):
    def __init__(self, master, *, on_stop: Action, on_retry: Action, on_products: Action):
        super().__init__(master, fg_color=theme.SURFACE)
        self.grid_columnconfigure(0, weight=1)

        self._status = ctk.CTkLabel(self, text="Ready.", anchor="w", font=theme.font(12),
                                    text_color=theme.TEXT_MUTED)
        self._status.grid(row=0, column=0, sticky="ew", padx=(theme.PAD, 12), pady=(12, 4))
        self._progress = ctk.CTkProgressBar(self, height=4, corner_radius=2,
                                            progress_color=theme.ACCENT, fg_color=theme.BORDER)
        self._progress.set(0)
        self._progress.grid(row=1, column=0, sticky="ew", padx=(theme.PAD, 12), pady=(0, 14))

        self._counter = ctk.CTkLabel(self, text="", font=theme.mono(12), text_color=theme.TEXT_MUTED)
        self._counter.grid(row=0, column=1, rowspan=2, padx=8)
        GhostButton(self, "🛍  Sub IDs", on_products, width=110).grid(row=0, column=2, rowspan=2, padx=(0, 8))
        GhostButton(self, "Retry failed", on_retry, width=104).grid(row=0, column=3, rowspan=2, padx=(0, 8))
        GhostButton(self, "Stop", on_stop, width=64).grid(row=0, column=4, rowspan=2, padx=(0, theme.PAD))

    def set_status(self, text: str, error: bool = False) -> None:
        self._status.configure(text=text, text_color=theme.DANGER if error else theme.TEXT_MUTED)

    def set_progress(self, fraction: float, done: int | None = None, total: int | None = None) -> None:
        self._progress.set(max(0.0, min(1.0, fraction)))
        if done is not None and total:
            self._counter.configure(text=f"{done} / {total}")
