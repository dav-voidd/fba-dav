"""☁ GDrive tab: paste a shared Drive folder link, download every video numbered in order."""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from ..products import gdrive
from . import theme
from .preview import open_path
from .widgets import Card, Eyebrow, GhostButton, PrimaryButton, Segmented

ORDERS = {"Name A–Z": "name", "Drive's order": "drive"}


class GDrivePage(ctk.CTkFrame):
    def __init__(self, master, *, output_dir: Callable[[], str], schedule: Callable[[Callable[[], None]], None]):
        super().__init__(master, fg_color="transparent")
        self._output_dir = output_dir
        self._schedule = schedule
        self._drive_name = ""
        self._files: list[gdrive.DriveFile] = []
        self._rows: list[DriveRow] = []
        self._running = False
        self._stop = threading.Event()
        self._order = ctk.StringVar(value="Name A–Z")
        self._save_to = ctk.StringVar(value="")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(head, text="Google Drive folder", font=theme.font(18, "bold"), text_color=theme.TEXT).pack(side="left")
        self._start = PrimaryButton(head, "Download all", self.start, width=150, height=36)
        self._start.pack(side="right")
        self._stop_btn = GhostButton(head, "Stop", self.stop, width=70)
        self._stop_btn.pack(side="right", padx=(0, 8))
        self._open = GhostButton(head, "Open folder", self._open_folder, width=110)
        self._open.pack(side="right", padx=(0, 8))

        # --- inputs
        card = Card(self)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        card.grid_columnconfigure(1, weight=1)
        Eyebrow(card, "Folder link").grid(row=0, column=0, sticky="w", padx=(theme.PAD, 8), pady=(14, 0))
        self._link = ctk.CTkEntry(card, height=32, fg_color=theme.BACKGROUND, border_color=theme.BORDER_STRONG,
                                  text_color=theme.TEXT, font=theme.font(12),
                                  placeholder_text="https://drive.google.com/drive/folders/…  (shared as Anyone with the link)")
        self._link.grid(row=0, column=1, sticky="ew", pady=(14, 0))
        self._link.bind("<Return>", lambda _e: self.load())
        PrimaryButton(card, "Load", self.load, width=90, height=32).grid(row=0, column=2, padx=(8, theme.PAD), pady=(14, 0))
        Eyebrow(card, "Save to").grid(row=1, column=0, sticky="w", padx=(theme.PAD, 8), pady=8)
        ctk.CTkEntry(card, textvariable=self._save_to, height=30, fg_color=theme.BACKGROUND, border_color=theme.BORDER,
                     text_color=theme.TEXT_MUTED, font=theme.font(12)).grid(row=1, column=1, sticky="ew", pady=8)
        GhostButton(card, "Choose", self._pick_folder, width=90, height=30).grid(row=1, column=2, padx=(8, theme.PAD), pady=8)
        order_row = ctk.CTkFrame(card, fg_color="transparent")
        order_row.grid(row=2, column=0, columnspan=3, sticky="ew", padx=theme.PAD, pady=(0, 14))
        Eyebrow(order_row, "Order").pack(side="left", padx=(0, 8))
        Segmented(order_row, list(ORDERS), self._order, lambda _v: self._show()).pack(side="left")
        ctk.CTkLabel(order_row, text="Files are saved as 001_name.mp4, 002_… so the Facebook tab keeps this order.",
                     font=theme.font(11), text_color=theme.TEXT_FAINT).pack(side="left", padx=12)

        # --- list + progress
        self._list = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                                            border_width=1, border_color=theme.BORDER,
                                            scrollbar_button_color=theme.BORDER)
        self._list.grid(row=2, column=0, sticky="nsew")
        self._list.grid_columnconfigure(0, weight=1)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        bar.grid_columnconfigure(1, weight=1)
        self._progress_label = ctk.CTkLabel(bar, text="Nothing loaded", width=200, anchor="w",
                                            font=theme.font(12, "bold"), text_color=theme.TEXT_MUTED)
        self._progress_label.grid(row=0, column=0, sticky="w")
        self._progress = ctk.CTkProgressBar(bar, height=10, corner_radius=5, fg_color=theme.SURFACE_RAISED,
                                            progress_color=theme.ACCENT)
        self._progress.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self._progress.set(0)
        self._status = ctk.CTkLabel(self, text="Paste a shared Drive folder link and press Load.",
                                    font=theme.font(12), text_color=theme.TEXT_MUTED, anchor="w")
        self._status.grid(row=4, column=0, sticky="ew", pady=(6, 12))
        self._buttons()

    # ---------------------------------------------------------------- helpers

    def _say(self, text: str, color: str = theme.TEXT_MUTED) -> None:
        self._status.configure(text=text, text_color=color)

    def _buttons(self) -> None:
        self._start.configure(state="normal" if self._files and not self._running else "disabled",
                              text="Downloading…" if self._running else "Download all")
        self._stop_btn.configure(state="normal" if self._running else "disabled")
        self._open.configure(state="normal" if self._save_to.get() else "disabled")

    def _ordered(self) -> list[gdrive.DriveFile]:
        return gdrive.sort_files(self._files, ORDERS[self._order.get()])

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self, initialdir=self._save_to.get() or self._output_dir())
        if folder:
            self._save_to.set(folder)
            self._buttons()
            if self._files:
                self._show()          # numbers may continue after files already in that folder

    def _open_folder(self) -> None:
        if self._save_to.get():
            Path(self._save_to.get()).mkdir(parents=True, exist_ok=True)
            open_path(self._save_to.get())

    # ---------------------------------------------------------------- actions

    def load(self) -> None:
        link = self._link.get().strip()
        if not link:
            self._say("Paste the Drive folder link first.", theme.DANGER)
            return
        self._say("Reading the folder…")

        def work() -> None:
            try:
                name, files = gdrive.list_folder(link)
                error = ""
            except gdrive.DriveError as exc:
                name, files, error = "", [], str(exc)

            def done() -> None:
                if error:
                    self._say(error, theme.DANGER)
                    return
                self._drive_name, self._files = name, files
                if not self._save_to.get():
                    self._save_to.set(str(Path(self._output_dir()) / gdrive.default_folder_name(name)))
                self._show()
            self._schedule(done)

        threading.Thread(target=work, daemon=True).start()

    def _show(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows = []
        videos = self._ordered()
        self._first = gdrive.start_number(Path(self._save_to.get()), videos) if self._save_to.get() else 1
        for number, file in enumerate(videos, self._first):
            row = DriveRow(self._list, number, file)
            row.grid(row=number, column=0, sticky="ew", padx=6, pady=3)
            self._rows.append(row)
            if (Path(self._save_to.get()) / gdrive.numbered_name(number, file.name)).exists():
                row.show("✓ Already downloaded", theme.SUCCESS)
        others = len(self._files) - len(videos)
        if self._files:
            self._say(f"{len(videos)} videos in “{self._drive_name or 'the folder'}”, in {self._order.get()} order."
                      + (f" {others} other file(s)/folder(s) skipped." if others else ""))
        self._update_progress()
        self._buttons()

    def _update_progress(self, current: float = 0.0) -> None:
        total = len(self._rows)
        done = sum(1 for r in self._rows if r.done)
        self._progress.set(((done + current) / total) if total else 0)
        self._progress_label.configure(
            text=(f"All {total} downloaded ✓" if total and done == total else f"Downloaded {done} / {total}")
            if total else "Nothing loaded",
            text_color=theme.SUCCESS if total and done == total else theme.TEXT)

    def start(self) -> None:
        folder = Path(self._save_to.get() or self._output_dir())
        jobs = [(n, f, row) for n, (f, row) in enumerate(zip(self._ordered(), self._rows), getattr(self, "_first", 1))
                if not row.done]
        if not jobs:
            self._say("Everything is already downloaded ✓", theme.ACCENT_TEXT)
            return
        self._running = True
        self._stop.clear()
        self._buttons()

        def work() -> None:
            failed = 0
            for number, file, row in jobs:
                if self._stop.is_set():
                    break
                self._schedule(lambda r=row: r.show("Downloading…", theme.ACCENT_TEXT))
                try:
                    gdrive.download(file, folder / gdrive.numbered_name(number, file.name),
                                    lambda f, r=row: self._schedule(lambda: (r.show(f"Downloading… {int(f * 100)}%",
                                                                                    theme.ACCENT_TEXT),
                                                                             self._update_progress(f))))
                    self._schedule(lambda r=row: (r.show("✓ Saved", theme.SUCCESS), self._update_progress()))
                except gdrive.DriveError as exc:
                    failed += 1
                    message = str(exc)
                    self._schedule(lambda r=row, m=message: r.show(f"✕ {m}", theme.DANGER))

            def finished() -> None:
                self._running = False
                self._buttons()
                self._update_progress()
                self._say("Done." + (f" {failed} failed: press Download all to retry them." if failed
                                     else " Files are numbered in order in the Save to folder."),
                          theme.DANGER if failed else theme.ACCENT_TEXT)
            self._schedule(finished)

        threading.Thread(target=work, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._say("Stopping after the current video…")


class DriveRow(ctk.CTkFrame):
    def __init__(self, master, number: int, file: gdrive.DriveFile):
        super().__init__(master, fg_color=theme.SURFACE_RAISED, corner_radius=10)
        self.done = False
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=f"{number:03d}", width=36, font=theme.mono(12),
                     text_color=theme.TEXT_FAINT).grid(row=0, column=0, padx=(12, 8), pady=10)
        ctk.CTkLabel(self, text=file.name + (f"   ·  {file.modified}" if file.modified else ""), anchor="w",
                     font=theme.font(12), text_color=theme.TEXT).grid(row=0, column=1, sticky="ew")
        self._state = ctk.CTkLabel(self, text="Waiting", width=230, anchor="e", font=theme.font(11),
                                   text_color=theme.TEXT_FAINT)
        self._state.grid(row=0, column=2, padx=12)

    def show(self, text: str, color: str) -> None:
        self.done = text.startswith("✓")
        self._state.configure(text=text, text_color=color)
