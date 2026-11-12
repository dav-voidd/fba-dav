"""Main window: owns the queue and wires the UI regions to the download engine."""

from __future__ import annotations

import os
import queue
import threading
from tkinter import TclError, filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from .. import __app_name__
from ..config import DEFAULT_OUTPUT_DIR, Settings
from ..downloader import Downloader
from ..errors import LOG_PATH, log_exception
from ..links import extract_links
from ..models import Quality, QueueItem, Status
from ..network import NO_INTERNET, has_internet
from ..products.scanner import Scanner
from . import theme
from .panels import Composer, QueuePanel, StatusBar, TopBar
from .preview import PreviewCard, open_path
from ..products.subid import assign_subids
from .ai_setup import AISetup
from .products_window import ProductsWindow

_POLL_MS = 50


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(__app_name__)
        self.geometry("1180x880")
        self.minsize(1000, 780)
        self.configure(fg_color=theme.BACKGROUND)

        self.settings = Settings.load()
        self.output_dir = ctk.StringVar(value=self.settings.output_dir)
        self.numbered = ctk.BooleanVar(value=self.settings.numbered_filenames)
        self.quality = ctk.StringVar(value=self.settings.quality)
        self.auto_scan = ctk.BooleanVar(value=self.settings.auto_scan)

        self.items: list[QueueItem] = []
        self._next_index = 1
        self._batch: list[QueueItem] = []
        self._ui_tasks: queue.Queue[Callable[[], None]] = queue.Queue()
        self.downloader = Downloader(_ThreadSafeListener(self))
        self.scanner = Scanner(_ThreadSafeScanListener(self))
        self.products_window: ProductsWindow | None = None
        self._ai_setup: AISetup | None = None
        self._offered_setup = False
        self.subid_code = ctk.StringVar(value=self.settings.subid_code)

        self._build_layout()
        self.after(_POLL_MS, self._drain_ui_tasks)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- layout

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, minsize=290)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        margin, gap = 24, theme.GAP

        self.topbar = TopBar(self)
        self.topbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=margin, pady=(18, 14))

        self.composer = Composer(
            self, output_dir=self.output_dir, numbered=self.numbered, quality=self.quality,
            auto_scan=self.auto_scan,
            on_text_changed=self._update_link_count, on_paste=self.paste_clipboard,
            on_clear=self.clear_input, on_download=self.download,
            on_change_folder=self.choose_folder, on_open_folder=self.open_folder,
        )
        self.composer.grid(row=1, column=0, columnspan=2, sticky="ew", padx=margin, pady=(0, gap))

        self.preview = PreviewCard(self, self.call_soon)
        self.preview.grid(row=2, column=0, sticky="nsew", padx=(margin, gap // 2), pady=(0, gap))

        self.queue = QueuePanel(self, on_select=self.select_item,
                                on_clear_finished=self.clear_finished, on_clear_all=self.clear_all)
        self.queue.grid(row=2, column=1, sticky="nsew", padx=(gap // 2, margin), pady=(0, gap))

        self.statusbar = StatusBar(self, on_stop=self.stop, on_retry=self.retry_failed,
                                   on_products=self.open_products)
        self.statusbar.grid(row=3, column=0, columnspan=2, sticky="ew", padx=margin, pady=(0, 20))

    # --------------------------------------------------------------- actions

    def download(self) -> None:
        """The one primary action: queue whatever is in the box, then start."""
        if self.composer.text().strip():
            self.add_links()
        self.start()

    def add_links(self) -> int:
        links = extract_links(self.composer.text())
        known = {item.url for item in self.items}
        new_items = []
        for url in links:
            if url not in known:
                new_items.append(QueueItem(index=self._next_index, url=url))
                self._next_index += 1
        self.items.extend(new_items)
        self.queue.add_many(new_items)
        self.composer.clear()
        self._update_link_count()

        skipped = len(links) - len(new_items)
        if not links:
            self.statusbar.set_status("No TikTok links found in the box.", error=True)
        else:
            self.statusbar.set_status(f"Added {len(new_items)} video(s)."
                                      + (f"  Skipped {skipped} duplicate(s)." if skipped else ""))
        self._update_stats()
        return len(new_items)

    def start(self) -> None:
        if self.downloader.is_running:
            return
        pending = [item for item in self.items if item.status is Status.WAITING]
        if not pending:
            self.statusbar.set_status("Nothing to download. Paste some TikTok links first.")
            return

        self._save_settings()
        self._batch = pending
        self.composer.set_running(True, 0, len(pending))
        self.statusbar.set_status("Checking internet connection…")

        def check() -> None:
            online = has_internet()
            self.call_soon(lambda: self._begin(pending) if online else self._offline())

        threading.Thread(target=check, daemon=True).start()

    def _begin(self, pending: list[QueueItem]) -> None:
        self.statusbar.set_progress(0, 0, len(pending))
        self.downloader.start(pending, self.settings.output_dir, self.settings.numbered_filenames,
                              Quality(self.settings.quality))

    def _offline(self) -> None:
        self.composer.set_running(False)
        self.statusbar.set_status(NO_INTERNET, error=True)
        messagebox.showwarning("No internet", "This app needs Wi-Fi or an internet connection.\n\n"
                               "Connect, then press Download again.")

    def stop(self) -> None:
        if self.downloader.is_running:
            self.downloader.stop()
            self.statusbar.set_status("Stopping after the current video…")
        if self.scanner.is_running:
            self.scanner.stop()
            self.statusbar.set_status("Stopping the product scan…")

    # ------------------------------------------------------------ products

    def scan_products(self, automatic: bool = False, items: list[QueueItem] | None = None,
                      flush: bool = True) -> None:
        """Queue downloaded, unscanned videos for Gemini.

        ``flush=False`` (used while a download is running) only starts the upload; the
        recognition request waits until the batch is full or the download is finished.
        """
        targets = [i for i in (items if items is not None else self.items)
                   if i.status is Status.DONE and not i.product]
        if not targets:
            if flush and self.scanner.is_running:
                self.scanner.flush()
            elif not automatic:
                self.statusbar.set_status("Every downloaded video is already scanned.")
            return
        if not self.settings.gemini_api_key:
            if automatic and self._offered_setup:
                return
            self._offered_setup = True  # show the guide once per session automatically
            self.set_api_key(then=lambda: self.scan_products(automatic=automatic))
            return
        for item in targets:
            item.scan_error = None
        self.scanner.enqueue(targets, self.settings.gemini_api_key, self.settings.gemini_model, flush=flush)
        self._products_refresh()

    def _products_refresh(self, item: QueueItem | None = None) -> None:
        if self.products_window is not None and self.products_window.winfo_exists():
            if item is None:
                self.products_window.refresh()
            else:
                self.products_window.refresh_item(item)

    def set_api_key(self, then: Callable[[], None] | None = None) -> None:
        """Open the guided 'Connect Gemini' window; run ``then`` once a key is saved."""
        if self._ai_setup is not None and self._ai_setup.winfo_exists():
            self._ai_setup.destroy()

        def saved(key: str) -> None:
            self.settings.gemini_api_key = key
            self.settings.save()
            self.statusbar.set_status("Gemini connected ✓")
            if self.products_window is not None and self.products_window.winfo_exists():
                self.products_window.refresh_header()
            if then:
                self.after(1000, then)

        self._ai_setup = AISetup(self, provider="gemini", current_key=self.settings.gemini_api_key,
                                 schedule=self.call_soon, on_saved=saved)

    def open_products(self) -> None:
        if self.products_window is not None and self.products_window.winfo_exists():
            self.products_window.refresh()
            self.products_window.focus()
            return
        self.products_window = ProductsWindow(
            self, get_items=lambda: self.items, on_scan=self.scan_products,
            on_connect=lambda: self.set_api_key(), is_connected=lambda: bool(self.settings.gemini_api_key),
            is_scanning=lambda: self.scanner.is_running,
            code=self.subid_code, on_code_changed=self._code_changed,
        )

    def _code_changed(self) -> None:
        self.settings.subid_code = "".join(ch for ch in self.subid_code.get() if ch.isalnum())
        self.settings.save()
        self._refresh_subids()

    def _refresh_subids(self) -> None:
        """Generate every sub ID at once, after all names are in, so 1, 2 numbering is final."""
        if not self.scanner.is_running:
            assign_subids(self.items, self.settings.subid_code)
        for item in self.items:
            if item.product:
                self.queue.refresh(item)
        self._products_refresh()

    def handle_scan_item(self, item: QueueItem) -> None:
        self.queue.refresh(item)
        self._products_refresh(item)
        if item.scan_error and ("API key" in item.scan_error or item.scan_error == NO_INTERNET):
            self.statusbar.set_status(item.scan_error, error=True)

    def handle_scan_progress(self, done: int, total: int) -> None:
        if not self.downloader.is_running:  # the download owns the status bar while it runs
            self.statusbar.set_progress(done / total if total else 1, done, total)
        self._products_refresh()

    def handle_scan_status(self, message: str) -> None:
        if self.scanner.is_running:
            if not self.downloader.is_running:
                self.statusbar.set_status(f"Sub IDs  ·  {message}")
            if self.products_window is not None and self.products_window.winfo_exists():
                self.products_window.set_status(message)

    def handle_scan_finished(self, found: int, failed: int) -> None:
        self._refresh_subids()
        if not self.downloader.is_running:
            done = [i for i in self.items if i.status is Status.DONE]
            scanned = sum(1 for i in done if i.product)
            failed = sum(1 for i in done if i.scan_error)
            message = f"Sub IDs ready: {scanned} of {len(done)}" + (f", {failed} failed" if failed else "")
            self.statusbar.set_status(message + "  ·  open 🛍 Sub IDs to copy them", error=bool(failed and not scanned))
        if self.products_window is not None and self.products_window.winfo_exists():
            self.products_window.set_status("")
            self.products_window.refresh()

    def retry_failed(self) -> None:
        for item in self.items:
            if item.status is Status.FAILED:
                item.reset()
                self.queue.refresh(item)
        self.start()

    def select_item(self, item: QueueItem) -> None:
        self.queue.select(item)
        self.preview.show(item)

    def clear_finished(self) -> None:
        self._remove(lambda item: item.status is Status.DONE)

    def clear_all(self) -> None:
        if self.downloader.is_running:
            self.statusbar.set_status("Stop the download before clearing the queue.")
            return
        self._remove(lambda item: True)
        self._next_index = 1
        self.statusbar.set_progress(0)

    def paste_clipboard(self) -> None:
        try:
            self.composer.append(self.clipboard_get().strip() + "\n")
        except TclError:
            pass  # clipboard empty or not text
        self._update_link_count()

    def clear_input(self) -> None:
        self.composer.clear()
        self._update_link_count()

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.output_dir.get() or str(DEFAULT_OUTPUT_DIR))
        if folder:
            self.output_dir.set(folder)
            self._save_settings()

    def open_folder(self) -> None:
        folder = self.output_dir.get() or str(DEFAULT_OUTPUT_DIR)
        os.makedirs(folder, exist_ok=True)
        open_path(folder)

    # ---------------------------------------------------- downloader events

    def handle_item_changed(self, item: QueueItem) -> None:
        self.queue.refresh(item)
        if item.status is Status.DOWNLOADING:
            self.queue.select(item)
            self.queue.scroll_to(item)  # keep the active row in view
            self.preview.show(item)     # follow the current download
            self.statusbar.set_status(f"Downloading #{item.index:02d}"
                                      + (f"  ·  @{item.post.author}" if item.post else "…"))
        else:
            self.preview.refresh(item)
            if item.status is Status.DONE and self.auto_scan.get() and self.settings.gemini_api_key:
                self.scan_products(automatic=True, items=[item], flush=False)  # upload while the rest downloads
            if item.status is Status.FAILED:
                self.statusbar.set_status(f"#{item.index:02d} failed: {(item.error or 'unknown error')[:100]}",
                                          error=True)
        done = sum(i.status in (Status.DONE, Status.FAILED) for i in self._batch)
        self.composer.set_running(self.downloader.is_running, done, len(self._batch))
        self._update_stats()

    def handle_progress(self, item: QueueItem) -> None:
        self.queue.refresh(item)
        self.preview.refresh(item)

    def handle_queue_progress(self, fraction: float) -> None:
        done = sum(i.status in (Status.DONE, Status.FAILED) for i in self._batch)
        self.statusbar.set_progress(fraction, done, len(self._batch))

    def handle_all_finished(self, succeeded: int, failed: int) -> None:
        self.composer.set_running(False)
        message = f"Done. {succeeded} saved" + (f", {failed} failed. Press Retry failed." if failed else ".")
        self.statusbar.set_status(message, error=bool(failed))
        self._update_stats()
        self.bell()
        if self.auto_scan.get() and succeeded:
            self.scan_products(automatic=True)  # anything not yet queued while downloading

    # -------------------------------------------------------------- helpers

    def call_soon(self, task: Callable[[], None]) -> None:
        """Schedule ``task`` on the UI thread. Safe to call from any thread."""
        self._ui_tasks.put(task)

    def _drain_ui_tasks(self) -> None:
        # One failing task must never stop the pump, or the whole UI freezes.
        try:
            while True:
                try:
                    task = self._ui_tasks.get_nowait()
                except queue.Empty:
                    break
                try:
                    task()
                except Exception as exc:
                    self._show_internal_error(exc)
        finally:
            self.after(_POLL_MS, self._drain_ui_tasks)

    def report_callback_exception(self, exc_type, exc, tb) -> None:  # Tk hook for widget callbacks
        self._show_internal_error(exc)

    def _show_internal_error(self, exc: BaseException) -> None:
        summary = log_exception(exc, "UI")
        try:
            self.statusbar.set_status(f"Error: {summary[:90]}  (see {LOG_PATH.name})", error=True)
        except Exception:
            pass

    def _update_link_count(self) -> None:
        self.composer.set_link_count(len(extract_links(self.composer.text())))

    def _remove(self, should_remove: Callable[[QueueItem], bool]) -> None:
        for item in [i for i in self.items if should_remove(i)]:
            self.queue.remove(item)
            self.items.remove(item)
        self._update_stats()

    def _update_stats(self) -> None:
        done = sum(item.status is Status.DONE for item in self.items)
        failed = sum(item.status is Status.FAILED for item in self.items)
        self.topbar.set_stats(len(self.items), done, failed)

    def _save_settings(self) -> None:
        self.settings.output_dir = self.output_dir.get().strip() or str(DEFAULT_OUTPUT_DIR)
        self.settings.numbered_filenames = bool(self.numbered.get())
        self.settings.auto_scan = bool(self.auto_scan.get())
        self.settings.quality = self.quality.get() if self.quality.get() in ("balanced", "max") else "balanced"
        self.settings.save()

    def _on_close(self) -> None:
        self._save_settings()
        self.destroy()


class _ThreadSafeListener:
    """Forwards downloader callbacks (worker thread) to the UI thread."""

    def __init__(self, app: App) -> None:
        self._app = app

    def on_item_started(self, item: QueueItem) -> None:
        self._app.call_soon(lambda: self._app.handle_item_changed(item))

    def on_item_info(self, item: QueueItem) -> None:
        self._app.call_soon(lambda: self._app.handle_item_changed(item))

    def on_item_progress(self, item: QueueItem) -> None:
        self._app.call_soon(lambda: self._app.handle_progress(item))

    def on_item_finished(self, item: QueueItem) -> None:
        self._app.call_soon(lambda: self._app.handle_item_changed(item))

    def on_queue_progress(self, fraction: float) -> None:
        self._app.call_soon(lambda: self._app.handle_queue_progress(fraction))

    def on_all_finished(self, succeeded: int, failed: int) -> None:
        self._app.call_soon(lambda: self._app.handle_all_finished(succeeded, failed))


class _ThreadSafeScanListener:
    """Forwards scanner callbacks (worker thread) to the UI thread."""

    def __init__(self, app: App) -> None:
        self._app = app

    def on_scan_item(self, item: QueueItem) -> None:
        self._app.call_soon(lambda: self._app.handle_scan_item(item))

    def on_scan_progress(self, done: int, total: int) -> None:
        self._app.call_soon(lambda: self._app.handle_scan_progress(done, total))

    def on_scan_finished(self, found: int, failed: int) -> None:
        self._app.call_soon(lambda: self._app.handle_scan_finished(found, failed))

    def on_scan_status(self, message: str) -> None:
        self._app.call_soon(lambda: self._app.handle_scan_status(message))

    def on_scan_model(self, model: str) -> None:
        def remember() -> None:
            self._app.settings.gemini_model = model
            self._app.settings.save()
        self._app.call_soon(remember)


def run() -> None:
    App().mainloop()
