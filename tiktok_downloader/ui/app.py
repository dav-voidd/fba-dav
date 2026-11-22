"""Main window: owns the queue and wires the UI regions to the download engine."""

from __future__ import annotations

import os
import queue
from pathlib import Path
import threading
import webbrowser
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
from .. import updates
from ..products.scanner import Scanner
from . import theme
from .panels import Composer, QueuePanel, StatusBar, TopBar
from .preview import PreviewCard, open_path
from ..products.subid import assign_subids, date_prefix
from .ai_setup import AISetup
from .products_window import ProductsWindow
from .excel_page import ExcelPage
from .facebook_page import FacebookPage
from .checker_page import CheckerPage
from .postids_page import PostIdsPage
from .gdrive_page import GDrivePage

_POLL_MS = 50


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("light")
        self.title(__app_name__)
        self._set_icon()
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
        self._ai_setup: AISetup | None = None
        self._offered_setup = False
        self.subid_code = ctk.StringVar(value=self.settings.subid_code)
        self.subid_date = ctk.StringVar(value=date_prefix())  # starts as today every launch

        self._build_layout()
        self.after(_POLL_MS, self._drain_ui_tasks)
        threading.Thread(target=self._check_for_update, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- layout

    PAGE_DOWNLOADER, PAGE_GDRIVE, PAGE_SUBIDS, PAGE_EXCEL, PAGE_FACEBOOK, PAGE_POSTIDS, PAGE_REELS, PAGE_CHECK = (
        "⬇  Downloader", "☁  GDrive", "🛍  Sub IDs", "📊  Excel", "📘  Facebook", "📋  Post IDs", "🔗  Reel Links",
        "✅  Checker")

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        margin, gap = 24, theme.GAP

        self.topbar = TopBar(self)
        self.topbar.grid(row=0, column=0, sticky="ew", padx=margin, pady=(16, 12))
        self.topbar.add_tabs([self.PAGE_DOWNLOADER, self.PAGE_GDRIVE, self.PAGE_SUBIDS, self.PAGE_EXCEL, self.PAGE_FACEBOOK,
                                self.PAGE_POSTIDS, self.PAGE_REELS, self.PAGE_CHECK], self.show_page)

        # Page 1: downloader (composer on top, preview + queue below)
        self.download_page = page = ctk.CTkFrame(self, fg_color="transparent")
        page.grid(row=1, column=0, sticky="nsew", padx=margin)
        page.grid_columnconfigure(0, minsize=290)
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(1, weight=1)

        self.composer = Composer(
            page, output_dir=self.output_dir, numbered=self.numbered, quality=self.quality,
            auto_scan=self.auto_scan,
            on_text_changed=self._update_link_count, on_paste=self.paste_clipboard,
            on_clear=self.clear_input, on_download=self.download,
            on_change_folder=self.choose_folder, on_open_folder=self.open_folder,
        )
        self.composer.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, gap))

        self.preview = PreviewCard(page, self.call_soon)
        self.preview.grid(row=1, column=0, sticky="nsew", padx=(0, gap // 2), pady=(0, gap))

        self.queue = QueuePanel(page, on_select=self.select_item,
                                on_clear_finished=self.clear_finished, on_clear_all=self.clear_all)
        self.queue.grid(row=1, column=1, sticky="nsew", padx=(gap // 2, 0), pady=(0, gap))

        # Page 2: sub IDs (same window, shown instead of page 1)
        self.products_window = ProductsWindow(
            self, get_items=lambda: self.items, on_scan=self.scan_products, on_scan_folder=self.scan_folder,
            on_connect=lambda: self.set_api_key(), is_connected=lambda: bool(self.settings.gemini_api_key),
            is_scanning=lambda: self.scanner.is_running,
            code=self.subid_code, on_code_changed=self._code_changed,
            date=self.subid_date, on_date_changed=self._refresh_subids,
        )
        self.products_window.grid(row=1, column=0, sticky="nsew", padx=margin)
        self.products_window.grid_remove()

        # Page 3: Excel sheet
        self.excel_page = ExcelPage(
            self, get_sub_ids=lambda: [i.product.display_sub_id for i in self.items
                                       if i.product and i.product.display_sub_id],
            default_name=self._excel_name, output_dir=lambda: self.output_dir.get(),
        )
        self.excel_page.grid(row=1, column=0, sticky="nsew", padx=margin)
        self.excel_page.grid_remove()

        # Page 4: post Reels to Facebook
        self.facebook_page = FacebookPage(
            self, settings=self.settings, get_products=self._products_by_file,
            get_scan_names=self._products_by_slug,
            output_dir=lambda: self.output_dir.get(), schedule=self.call_soon,
        )
        self.facebook_page.grid(row=1, column=0, sticky="nsew", padx=margin)
        self.facebook_page.grid_remove()

        # Page 5: post ID checker
        self.checker_page = CheckerPage(self, settings=self.settings, get_posted=self.facebook_page.posted_ids,
                                        schedule=self.call_soon)
        self.checker_page.grid(row=1, column=0, sticky="nsew", padx=margin)
        self.checker_page.grid_remove()

        # Page 8: reel links by date (with shop / search filters)
        self.reels_page = PostIdsPage(self, settings=self.settings, schedule=self.call_soon, reels=True)
        self.reels_page.grid(row=1, column=0, sticky="nsew", padx=margin)
        self.reels_page.grid_remove()

        # Page 7: Google Drive folder downloader
        self.gdrive_page = GDrivePage(self, output_dir=lambda: self.output_dir.get(), schedule=self.call_soon)
        self.gdrive_page.grid(row=1, column=0, sticky="nsew", padx=margin)
        self.gdrive_page.grid_remove()

        # Page 6: post IDs by date
        self.postids_page = PostIdsPage(self, settings=self.settings, schedule=self.call_soon)
        self.postids_page.grid(row=1, column=0, sticky="nsew", padx=margin)
        self.postids_page.grid_remove()


        self.statusbar = StatusBar(self, on_stop=self.stop, on_retry=self.retry_failed,
                                   on_products=self.open_products)
        self.statusbar.grid(row=2, column=0, sticky="ew", padx=margin, pady=(0, 20))

    def _set_icon(self) -> None:
        """Window/taskbar icon = the fba-dav logo (CustomTkinter sets its own icon first, so apply after)."""
        import sys
        ico = theme.asset("logo.ico")

        def apply() -> None:
            try:
                if sys.platform == "win32":
                    self.iconbitmap(ico)
                else:
                    from PIL import Image, ImageTk
                    self._icon_photo = ImageTk.PhotoImage(Image.open(theme.asset("logo.png")).resize((64, 64)))
                    self.iconphoto(True, self._icon_photo)
            except Exception:
                pass
        self.after(250, apply)

    def show_page(self, name: str) -> None:
        """Switch between the Downloader, Sub IDs and Excel tabs."""
        self.topbar.set_tab(name)
        pages = {self.PAGE_DOWNLOADER: self.download_page, self.PAGE_SUBIDS: self.products_window,
                 self.PAGE_EXCEL: self.excel_page, self.PAGE_FACEBOOK: self.facebook_page,
                 self.PAGE_CHECK: self.checker_page, self.PAGE_POSTIDS: self.postids_page,
                 self.PAGE_GDRIVE: self.gdrive_page, self.PAGE_REELS: self.reels_page}
        for page_name, page in pages.items():
            if page_name == name:
                page.grid()
            else:
                page.grid_remove()
        if name == self.PAGE_SUBIDS:
            self.products_window.refresh()

    def _products_by_file(self) -> dict[str, str]:
        """Video file name -> product name ("Clothes Hanger") from the scan."""
        names = {}
        for item in self.items:
            if item.saved_path and item.product:
                names[Path(item.saved_path).name.lower()] = item.product.short_name.title()
        return names

    def _products_by_slug(self) -> dict[str, str]:
        """Sub ID product part -> product name ("spicesstorage" -> "Spices Storage") from the scan."""
        from ..products.subid import slug_from_subid
        names = {}
        for item in self.items:
            if item.product and item.product.sub_id:
                names[slug_from_subid(item.product.sub_id)] = item.product.short_name.title()
        return names

    def _excel_name(self) -> str:
        """NOV13 + IC -> NOV13IC (the same name as the sample sheet)."""
        day = "".join(ch for ch in self.subid_date.get() if ch.isalnum()).upper()
        code = "".join(ch for ch in self.subid_code.get() if ch.isalnum())
        return f"{day}{code}"

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
                   if i.status is Status.DONE and not i.product
                   and i.saved_path and Path(i.saved_path).exists()]   # only videos that are really on disk
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
        """The status bar button toggles between the two tabs."""
        on_subids = self.products_window.winfo_ismapped()
        self.show_page(self.PAGE_DOWNLOADER if on_subids else self.PAGE_SUBIDS)

    def _code_changed(self) -> None:
        self.settings.subid_code = "".join(ch for ch in self.subid_code.get() if ch.isalnum())
        self.settings.save()
        self._refresh_subids()

    def _refresh_subids(self) -> None:
        """Generate every sub ID at once, after all names are in, so 1, 2 numbering is final."""
        if not self.scanner.is_running:
            assign_subids(self.items, self.settings.subid_code, prefix=self.subid_date.get())
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

    def scan_folder(self) -> None:
        """Scan videos that are already on the PC (e.g. from the GDrive tab), in 001_ number order."""
        from ..products.facebook import video_files
        if self.downloader.is_running or self.scanner.is_running:
            self.statusbar.set_status("Wait for the current download/scan to finish first.", error=True)
            return
        folder = filedialog.askdirectory(parent=self, title="Folder with your numbered videos",
                                         initialdir=self.output_dir.get() or None)
        if not folder:
            return
        videos = video_files(Path(folder))
        if not videos:
            self.statusbar.set_status("No .mp4 videos in that folder.", error=True)
            return
        if self.items and not messagebox.askyesno(
                "Scan a folder", f"Replace the current list with the {len(videos)} videos in this folder?\n\n"
                                 "(Videos and files on your PC are not deleted.)", parent=self):
            return
        self._remove(lambda item: True)
        new_items = []
        for number, path in enumerate(videos, 1):
            item = QueueItem(index=number, url=path.as_uri(), status=Status.DONE, progress=1.0,
                             title=path.stem, saved_path=str(path))
            new_items.append(item)
        self._next_index = len(new_items) + 1
        self.items.extend(new_items)
        self.queue.add_many(new_items)
        self._update_stats()
        self.show_page(self.PAGE_SUBIDS)
        self.statusbar.set_status(f"Loaded {len(new_items)} videos from {Path(folder).name}. Scanning…")
        self.scan_products()

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

    def _check_for_update(self) -> None:
        release = updates.newer_release()
        if release:
            label = "Update now" if updates.can_self_update(release) else "Download"
            self.call_soon(lambda: self.topbar.show_update(
                f"⬆  {release.version} available · {label}", lambda: self._update_app(release)))

    def _update_app(self, release: "updates.Release") -> None:
        if not updates.can_self_update(release):
            webbrowser.open(release.page_url)  # running from source: get it from GitHub
            return
        if self.downloader.is_running or self.scanner.is_running:
            self.statusbar.set_status("Finish or stop the current download/scan before updating.")
            return

        def progress(fraction: float) -> None:
            self.call_soon(lambda: self.topbar.show_update(f"Downloading update  {int(fraction * 100)}%"))

        def work() -> None:
            try:
                new_exe = updates.download_update(release, progress)
            except Exception as exc:
                log_exception(exc, "self-update")
                self.call_soon(lambda: (
                    self.topbar.show_update(f"⬆  {release.version} · Retry update", lambda: self._update_app(release)),
                    self.statusbar.set_status("Update failed. Check your internet and try again.", error=True)))
                return
            self.call_soon(lambda: self._restart_into(new_exe))

        self.topbar.show_update("Downloading update…")
        threading.Thread(target=work, daemon=True).start()

    def _restart_into(self, new_exe) -> None:
        self.topbar.show_update("Restarting…")
        self._save_settings()
        updates.install_and_restart(new_exe)
        self.after(300, lambda: os._exit(0))

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
        # A fallback model is only for this session; next launch starts on the newest model again.
        pass


def run() -> None:
    App().mainloop()
