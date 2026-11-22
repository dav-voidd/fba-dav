"""Preview card: animated thumbnail, caption, author, progress and a Play button."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageOps, ImageSequence

from .. import tikwm
from ..errors import log_exception
from ..models import QueueItem, Status
from . import theme
from .widgets import Card, Eyebrow, GhostButton

THUMB_SIZE = (150, 200)  # 3:4, like a TikTok cover
_MAX_FRAMES = 48
_DEFAULT_FRAME_MS = 80

Scheduler = Callable[[Callable[[], None]], None]

_HEADLINE = {
    Status.WAITING: ("Up next", theme.TEXT_FAINT),
    Status.DOWNLOADING: ("● Downloading", theme.ACCENT),
    Status.DONE: ("✓ Saved", theme.SUCCESS),
    Status.FAILED: ("✕ Failed", theme.DANGER),
}


def load_frames(data: bytes) -> list[tuple[Image.Image, int]]:
    """Decode a (possibly animated) image into fitted frames with their durations."""
    image = Image.open(io.BytesIO(data))
    frames = []
    for frame in ImageSequence.Iterator(image):
        rgb = frame.convert("RGB")
        rgb.thumbnail((THUMB_SIZE[0] * 2, THUMB_SIZE[1] * 2))  # cheap pre-shrink of big frames
        fitted = ImageOps.fit(rgb, THUMB_SIZE, Image.BILINEAR)
        frames.append((fitted, int(frame.info.get("duration") or _DEFAULT_FRAME_MS)))
        if len(frames) >= _MAX_FRAMES:
            break
    return frames


class PreviewCard(Card):
    def __init__(self, master, schedule: Scheduler):
        super().__init__(master)
        self._schedule = schedule          # runs a callable on the UI thread
        self._item: QueueItem | None = None
        self._frames: list[tuple[ctk.CTkImage, int]] = []
        self._cache: dict[int, list[tuple[Image.Image, int]]] = {}  # item index -> decoded frames
        self._generation = 0               # invalidates stale loads/animations
        self.grid_columnconfigure(0, weight=1)

        self._eyebrow = Eyebrow(self, "Preview")
        self._eyebrow.grid(row=0, column=0, sticky="ew", padx=theme.PAD, pady=(theme.PAD - 4, 8))

        self._blank = ctk.CTkImage(Image.new("RGBA", THUMB_SIZE, (0, 0, 0, 0)), size=THUMB_SIZE)
        self._thumb = ctk.CTkLabel(self, text="♪", image=self._blank, compound="center",
                                   width=THUMB_SIZE[0], height=THUMB_SIZE[1], corner_radius=12,
                                   fg_color=theme.BACKGROUND, font=theme.font(32, "bold"),
                                   text_color=theme.BORDER_STRONG)
        self._thumb.grid(row=1, column=0, padx=theme.PAD)

        self._title = ctk.CTkLabel(self, text="Nothing playing", anchor="w", justify="left",
                                   wraplength=230, font=theme.font(14, "bold"),
                                   text_color=theme.TEXT)
        self._title.grid(row=2, column=0, sticky="ew", padx=theme.PAD, pady=(12, 2))
        self._meta = ctk.CTkLabel(self, text="Paste links and hit Download.", anchor="w",
                                  font=theme.font(12), text_color=theme.TEXT_MUTED)
        self._meta.grid(row=3, column=0, sticky="ew", padx=theme.PAD)

        self._bar = ctk.CTkProgressBar(self, height=4, corner_radius=2, fg_color=theme.BORDER,
                                       progress_color=theme.ACCENT)
        self._bar.set(0)
        self._bar.grid(row=4, column=0, sticky="ew", padx=theme.PAD, pady=(12, 0))

        self._play = GhostButton(self, "▶  Play", self._open_saved)
        self._play.grid(row=5, column=0, sticky="ew", padx=theme.PAD, pady=(12, theme.PAD - 4))
        self._play.configure(state="disabled")

    # ------------------------------------------------------------------ API

    @property
    def item(self) -> QueueItem | None:
        return self._item

    def show(self, item: QueueItem) -> None:
        """Display ``item``; reloads the thumbnail only when its media changes."""
        reload = self._item is not item or not self._frames
        self._item = item
        self._render()
        if reload:
            self._load_thumbnail()

    def refresh(self, item: QueueItem) -> None:
        if item is self._item:
            self._render()

    # -------------------------------------------------------------- internals

    def _render(self) -> None:
        item, post = self._item, self._item.post
        headline, color = _HEADLINE[item.status]
        self._eyebrow.configure(text=headline.upper(), text_color=color)

        caption = (post.caption if post and post.caption else item.title or item.url).replace("\n", " ")
        self._title.configure(text=caption[:110] + ("…" if len(caption) > 110 else ""))

        meta = [f"@{post.author}" if post else f"#{item.index:02d}"]
        if post and post.duration:
            meta.append(f"{post.duration // 60}:{post.duration % 60:02d}")
        if post and post.is_slideshow:
            meta.append(f"{len(post.image_urls)} photos")
        if item.status is Status.FAILED and item.error:
            meta = [item.error[:60]]
        self._meta.configure(text="  ·  ".join(meta),
                             text_color=theme.DANGER if item.status is Status.FAILED else theme.TEXT_MUTED)

        self._bar.configure(progress_color=theme.SUCCESS if item.status is Status.DONE else theme.ACCENT)
        self._bar.set(1 if item.status is Status.DONE else item.progress)

        is_folder = bool(post and post.is_slideshow)
        self._play.configure(state="normal" if item.saved_path else "disabled",
                             text="📁  Open photos" if is_folder else "▶  Play")

    def _load_thumbnail(self) -> None:
        """Show the still cover as soon as possible, then upgrade to the animated preview."""
        self._generation += 1
        generation = self._generation
        self._frames = []
        item = self._item
        cached = self._cache.get(item.index)
        if cached:
            self._start_animation(cached, generation, item.index)
            return
        self._thumb.configure(image=self._blank, text="♪")
        post = item.post
        if post is None:
            return

        def work() -> None:
            for url in (post.cover_url, post.preview_url):  # still first: it's small and fast
                if not url:
                    continue
                try:
                    frames = load_frames(tikwm.get_bytes(url))
                except Exception as exc:
                    log_exception(exc, f"thumbnail {url[:80]}")
                    continue
                self._schedule(lambda f=frames: self._start_animation(f, generation, item.index))

        threading.Thread(target=work, daemon=True).start()

    def _start_animation(self, frames: list[tuple[Image.Image, int]], generation: int, index: int) -> None:
        if not frames:
            return
        if len(frames) >= len(self._cache.get(index, [])):
            self._cache[index] = frames  # keep the richest version for instant re-display
        if generation != self._generation:
            return  # the user moved on to another video
        if self._frames and len(frames) < len(self._frames):
            return  # already showing a richer (animated) version
        self._frames = [(ctk.CTkImage(img, img, size=THUMB_SIZE), ms) for img, ms in frames]
        self._thumb.configure(text="")
        self._animate(0, generation)

    def _animate(self, index: int, generation: int) -> None:
        if generation != self._generation or not self._frames:
            return
        image, delay = self._frames[index % len(self._frames)]
        self._thumb.configure(image=image)
        if len(self._frames) > 1:
            self.after(max(delay, 30), self._animate, index + 1, generation)

    def _open_saved(self) -> None:
        path = self._item.saved_path if self._item else None
        if path and os.path.exists(path):
            open_path(path)


def open_path(path: str) -> None:
    """Open a file or folder with the system's default app."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - opening a local file
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])
