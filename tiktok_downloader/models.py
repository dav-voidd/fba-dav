"""Plain data types shared by the downloader core and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Quality(Enum):
    BALANCED = "balanced"   # ~4-5 MB, H.264, plays everywhere
    MAX = "max"             # highest bitrate TikTok has


class Status(Enum):
    WAITING = "Waiting"
    DOWNLOADING = "Downloading"
    DONE = "Done"
    FAILED = "Failed"


@dataclass
class Post:
    """What we know about a TikTok post before downloading it."""

    id: str
    author: str
    caption: str = ""
    duration: int = 0                 # seconds
    cover_url: str | None = None      # still thumbnail
    preview_url: str | None = None    # animated thumbnail when available
    video_url: str | None = None      # watermark-free, balanced quality (H.264)
    hd_video_url: str | None = None   # watermark-free, max quality (often HEVC/H.265)
    image_urls: list[str] = field(default_factory=list)  # photo slideshow

    @property
    def is_slideshow(self) -> bool:
        return bool(self.image_urls) and not self.video_url

    @property
    def display_title(self) -> str:
        caption = self.caption.replace("\n", " ").strip()
        return f"@{self.author}" + (f" · {caption}" if caption else "")


@dataclass
class Product:
    """What the scanner recognised in a video."""

    name: str              # e.g. "Silicone Sealant Waterproof Clear"
    short_name: str        # max 2 words, e.g. "silicone sealant"
    confidence: float = 0.0
    sub_id: str = ""       # generated, e.g. "NOV12ICsiliconesealant"
    custom_sub_id: str = ""  # the user's own edit, if any

    @property
    def display_sub_id(self) -> str:
        return self.custom_sub_id or self.sub_id


@dataclass
class QueueItem:
    """One TikTok link in the download queue."""

    index: int
    url: str
    status: Status = Status.WAITING
    progress: float = 0.0
    title: str | None = None
    error: str | None = None
    post: Post | None = None
    saved_path: str | None = None     # file, or folder for slideshows
    product: Product | None = None
    scan_error: str | None = None
    scan_stage: str = ""   # "", "uploading", "uploaded", "analyzing", "done", "failed"

    def reset(self) -> None:
        self.status = Status.WAITING
        self.progress = 0.0
        self.error = None
