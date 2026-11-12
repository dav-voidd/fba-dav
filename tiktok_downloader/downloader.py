"""Download engine: works through a queue of TikTok links one at a time, in order.

Strategy per link:
  1. Ask tikwm.com for clean media URLs (fast, watermark-free, handles slideshows).
  2. If that fails, fall back to yt-dlp, refusing audio-only results.

The engine knows nothing about the UI. It reports through a ``DownloadListener``
whose callbacks run on the worker thread, so a GUI must hand them over to its own
thread (see ``ui/app.py``).
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Callable, Protocol

from . import tikwm
from .errors import log_exception
from .models import Post, Quality, QueueItem, Status
from .network import NO_INTERNET, looks_offline

Progress = Callable[[float], None]

# yt-dlp fallback: skip TikTok's watermarked "download" copy and never accept audio-only.
YTDLP_FORMATS = {
    Quality.BALANCED: "best[format_id!*=download][vcodec^=h264]/best[format_id!*=download][vcodec!=none]/best[vcodec!=none]",
    Quality.MAX: "best[format_id!*=download][vcodec!=none]/best[vcodec!=none]",
}


class DownloadListener(Protocol):
    def on_item_started(self, item: QueueItem) -> None: ...
    def on_item_info(self, item: QueueItem) -> None: ...
    def on_item_progress(self, item: QueueItem) -> None: ...
    def on_item_finished(self, item: QueueItem) -> None: ...
    def on_queue_progress(self, fraction: float) -> None: ...
    def on_all_finished(self, succeeded: int, failed: int) -> None: ...


class NoVideoError(Exception):
    """The post has audio but no video or images."""


class Downloader:
    def __init__(self, listener: DownloadListener) -> None:
        self._listener = listener
        self._api = tikwm.TikwmClient()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._quality = Quality.BALANCED

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, items: list[QueueItem], output_dir: str, numbered: bool,
              quality: Quality = Quality.BALANCED) -> None:
        if self.is_running or not items:
            return
        self._quality = quality
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._guarded_run, args=(items, Path(output_dir), numbered), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Finish the current video, then stop."""
        self._stop.set()

    # ---------------------------------------------------------------- worker

    def _run(self, items: list[QueueItem], output_dir: Path, numbered: bool) -> None:
        total = len(items)
        succeeded = failed = 0

        for position, item in enumerate(items):
            if self._stop.is_set():
                break

            item.status, item.progress = Status.DOWNLOADING, 0.0
            self._listener.on_item_started(item)

            def report(fraction: float, item: QueueItem = item, position: int = position) -> None:
                item.progress = fraction
                self._listener.on_item_progress(item)
                self._listener.on_queue_progress((position + fraction) / total)

            prefix = f"{item.index:03d}_" if numbered else ""
            try:
                item.saved_path = str(self._download(item, output_dir, prefix, report))
                item.status, item.progress = Status.DONE, 1.0
                succeeded += 1
            except Exception as exc:  # any failure only affects this one link
                item.status = Status.FAILED
                item.error = _friendly_error(exc)
                failed += 1

            self._listener.on_item_finished(item)
            self._listener.on_queue_progress((position + 1) / total)

        self._listener.on_all_finished(succeeded, failed)

    def _guarded_run(self, items: list[QueueItem], output_dir: Path, numbered: bool) -> None:
        try:
            self._run(items, output_dir, numbered)
        except Exception as exc:  # a bug in the engine must still release the UI
            log_exception(exc, "download worker crashed")
            self._listener.on_all_finished(0, len(items))

    def _download(self, item: QueueItem, output_dir: Path, prefix: str, report: Progress) -> Path:
        try:
            post = self._api.get_post(item.url)
        except Exception as exc:
            if looks_offline(str(exc)):
                raise
            if not isinstance(exc, tikwm.ApiError):  # expected API refusals aren't bugs
                log_exception(exc, f"tikwm failed for {item.url}; using yt-dlp")
            return _download_with_ytdlp(item, output_dir, prefix, report, self._quality)

        item.post = post
        item.title = post.display_title
        self._listener.on_item_info(item)

        stem = f"{prefix}{_safe(post.author)}_{post.id}"
        video_url = post.hd_video_url if self._quality is Quality.MAX else post.video_url
        if video_url:
            return tikwm.download_file(video_url, output_dir / f"{stem}.mp4", report, expect="video")
        if post.image_urls:
            return _download_slideshow(post, output_dir / f"{stem}_photos", report)
        raise NoVideoError()


def _download_slideshow(post: Post, folder: Path, report: Progress) -> Path:
    count = len(post.image_urls)
    for number, url in enumerate(post.image_urls, 1):
        tikwm.download_file(url, folder / f"{number:02d}.jpg",
                            lambda f, n=number: report((n - 1 + f) / count))
        report(number / count)
    return folder


def _download_with_ytdlp(item: QueueItem, output_dir: Path, prefix: str, report: Progress,
                         quality: Quality = Quality.BALANCED) -> Path:
    import yt_dlp  # imported lazily: only needed as a fallback

    def hook(status: dict) -> None:
        if status.get("status") == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            if total:
                report(status.get("downloaded_bytes", 0) / total)

    options = {
        "outtmpl": str(output_dir / f"{prefix}%(uploader)s_%(id)s.%(ext)s"),
        "format": YTDLP_FORMATS[quality],
        "noplaylist": True, "restrictfilenames": True,
        "retries": 5, "fragment_retries": 5,
        "quiet": True, "no_warnings": True, "noprogress": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        # process=False: inspect formats before yt-dlp tries to pick one.
        info = ydl.extract_info(item.url, download=False, process=False) or {}
        if not _has_video(info):
            raise NoVideoError()
        result = ydl.process_ie_result(info, download=True) or info
        item.title = item.title or f"@{result.get('uploader', '')}"
        downloads = result.get("requested_downloads") or [{}]
        return Path(downloads[0].get("filepath") or ydl.prepare_filename(result))


def _has_video(info: dict) -> bool:
    return any(_is_video_format(f) for f in (info.get("formats") or [info]))


def _is_video_format(fmt: dict) -> bool:
    codec = fmt.get("vcodec")
    if codec:
        return codec != "none"
    return bool(fmt.get("width") or fmt.get("height")) or fmt.get("ext") in ("mp4", "webm", "mov")


def _safe(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name).strip("_") or "tiktok"


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, NoVideoError):
        return "This post has no downloadable video."
    message = str(exc).replace("ERROR: ", "").strip()
    if looks_offline(message):
        return NO_INTERNET
    return message or exc.__class__.__name__
