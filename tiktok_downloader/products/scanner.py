"""Gemini batch scanner.

Each video is uploaded to Gemini the moment it finishes downloading (several at once).
Recognition then happens in batches: one Gemini request covers up to BATCH_SIZE videos,
like dropping 10 videos into the Gemini app. A batch runs when it is full, or when the
download finishes (``flush``).
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Protocol

from ..errors import log_exception, log_line
from ..models import Product, QueueItem
from ..network import NO_INTERNET, looks_offline
from .common import ScanError
from .gemini import GeminiClient, UploadedVideo

BATCH_SIZE = 10         # videos per Gemini request (the Gemini limit is 10): half the requests, so the free limit lasts twice as long
PARALLEL_BATCHES = 2    # requests in flight at once
PARALLEL_UPLOADS = 3


class ScanListener(Protocol):
    def on_scan_item(self, item: QueueItem) -> None: ...
    def on_scan_progress(self, done: int, total: int) -> None: ...
    def on_scan_finished(self, found: int, failed: int) -> None: ...
    def on_scan_status(self, message: str) -> None: ...
    def on_scan_model(self, model: str) -> None: ...


class Scanner:
    def __init__(self, listener: ScanListener) -> None:
        self._listener = listener
        self._cond = threading.Condition()
        self._pending: list[QueueItem] = []
        self._uploads: dict[int, Future] = {}
        self._flush = False
        self._stop = False
        self._active = False
        self._pool: ThreadPoolExecutor | None = None
        self._client: GeminiClient | None = None
        self._done = self._total = 0

    @property
    def is_running(self) -> bool:
        with self._cond:
            return self._active

    def enqueue(self, items: list[QueueItem], api_key: str, model: str, flush: bool = False) -> None:
        """Queue videos: their upload starts now; recognition waits for a full batch or a flush."""
        with self._cond:
            if not self._active:
                self._start(api_key, model)
            for item in items:
                if id(item) in self._uploads:
                    continue
                self._pending.append(item)
                self._total += 1
                item.scan_stage, item.scan_error = "uploading", None
                self._uploads[id(item)] = self._pool.submit(self._upload, item)
            self._flush = self._flush or flush
            self._cond.notify_all()

    def flush(self) -> None:
        """Recognise whatever is queued now, even if the batch is not full."""
        with self._cond:
            self._flush = True
            self._cond.notify_all()

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()

    # ---------------------------------------------------------------- worker

    def _start(self, api_key: str, model: str) -> None:
        self._active, self._stop, self._flush = True, False, False
        self._done = self._total = 0
        self._client = GeminiClient(api_key, model, on_status=self._listener.on_scan_status)
        self._pool = ThreadPoolExecutor(max_workers=PARALLEL_UPLOADS)
        threading.Thread(target=self._run, args=(model,), daemon=True).start()

    def _upload(self, item: QueueItem) -> UploadedVideo:
        self._listener.on_scan_item(item)
        video = self._upload_file(item)
        item.scan_stage = "uploaded"
        self._listener.on_scan_item(item)
        return video

    def _upload_file(self, item: QueueItem) -> UploadedVideo:
        path = Path(item.saved_path or "")
        if path.is_dir():  # photo slideshow: the first photo shows the product
            photos = sorted(path.glob("*.jpg"))
            if not photos:
                raise ScanError("No photos to scan.")
            return self._client.upload(photos[0], "image/jpeg")
        if not path.is_file():
            # moved/renamed since download? find it by its number prefix (e.g. "003_")
            prefix = path.name.split("_", 1)[0] + "_" if "_" in path.name else ""
            matches = sorted(path.parent.glob(f"{prefix}*.mp4")) if prefix and path.parent.is_dir() else []
            if not matches:
                raise ScanError("The video file isn't in the folder anymore. Download it again.")
            path = matches[0]
            item.saved_path = str(path)
        return self._client.upload(path)

    def _next_batch(self) -> list[QueueItem] | None:
        with self._cond:
            while True:
                if self._stop:
                    return None
                if len(self._pending) >= BATCH_SIZE or (self._flush and self._pending):
                    batch, self._pending = self._pending[:BATCH_SIZE], self._pending[BATCH_SIZE:]
                    return batch  # once flushed, stay flushed until the queue is empty
                if self._flush and not self._pending:
                    return None
                self._cond.wait(timeout=1)

    def _run(self, model: str) -> None:
        counts = {"found": 0, "failed": 0}
        lock = threading.Lock()
        try:
            with ThreadPoolExecutor(max_workers=PARALLEL_BATCHES) as batches:
                running: set[Future] = set()
                while (batch := self._next_batch()) is not None:
                    running.add(batches.submit(self._process, batch, counts, lock))
                    if len(running) >= PARALLEL_BATCHES:  # wait for a slot
                        done, running = wait(running, return_when="FIRST_COMPLETED")
                wait(running)
            if self._client.model != model:
                self._listener.on_scan_model(self._client.model)
        except Exception as exc:
            log_exception(exc, "scanner crashed")
        finally:
            with self._cond:
                leftover, self._pending = self._pending, []
                self._uploads.clear()
                self._active = False
            for item in leftover:
                item.scan_stage, item.scan_error = "failed", item.scan_error or "Scan stopped."
                self._listener.on_scan_item(item)
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._listener.on_scan_finished(counts["found"], counts["failed"])

    def _process(self, batch: list[QueueItem], counts: dict, lock: threading.Lock) -> None:
        """Upload-wait, then one Gemini request for the whole batch."""
        ready: list[tuple[QueueItem, UploadedVideo]] = []
        for item in batch:
            try:
                ready.append((item, self._uploads[id(item)].result()))
            except Exception as exc:
                self._fail(item, exc, counts, lock)
        if not ready:
            return
        for item, _ in ready:
            item.scan_stage = "analyzing"
            self._listener.on_scan_item(item)
        try:
            results = self._client.identify_batch(
                [(item.index, item.post.caption if item.post else "", video) for item, video in ready])
        except Exception as exc:
            for item, _ in ready:
                self._fail(item, exc, counts, lock)
            if "API key" in str(exc) or looks_offline(str(exc)):
                self.stop()
            return
        finally:
            for _, video in ready:
                self._pool.submit(self._client.delete, video)
        for item, _ in ready:
            result = results.get(item.index)
            if not result:
                self._fail(item, ScanError("Gemini skipped this video. Press Scan again."), counts, lock)
                continue
            short = result["short_name"] or " ".join(result["product_name"].split()[:2])
            item.product = Product(result["product_name"], short, result["confidence"])
            item.scan_stage, item.scan_error = "done", None
            with lock:
                counts["found"] += 1
            self._finish(item)

    def _fail(self, item: QueueItem, exc: Exception, counts: dict, lock: threading.Lock) -> None:
        message = str(exc)
        item.scan_stage = "failed"
        item.scan_error = NO_INTERNET if looks_offline(message) else message[:160]
        with lock:
            counts["failed"] += 1
        if isinstance(exc, ScanError):
            log_line("scan failed", f"#{item.index}: {exc}")
        else:
            log_exception(exc, f"scan {item.url}")
        self._finish(item)

    def _finish(self, item: QueueItem) -> None:
        with self._cond:
            self._done += 1
            done, total = self._done, self._total
        self._listener.on_scan_item(item)
        self._listener.on_scan_progress(done, total)
