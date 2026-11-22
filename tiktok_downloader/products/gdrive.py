"""Download every video from a public Google Drive folder ("Anyone with the link"), numbered in order.

No sign-in: the folder list comes from Drive's public embedded folder view, and each file from
Drive's public download address. Files are saved as 001_name.mp4, 002_name.mp4, ... so the rest
of the app (Sub IDs, Excel, Facebook) keeps the same order.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
MAX_FILE_BYTES = 2 * 1024 ** 3      # 2 GB per video, a safety cap

_FOLDER_ID = re.compile(r"(?:folders/|[?&]id=)([A-Za-z0-9_-]{10,})")
_ENTRY = re.compile(r'<div class="flip-entry" id="entry-([A-Za-z0-9_-]+)".*?(?=<div class="flip-entry" id="entry-|$)', re.S)
_TITLE = re.compile(r'<div class="flip-entry-title">(.*?)</div>', re.S)
_MODIFIED = re.compile(r'<div class="flip-entry-last-modified"><div>(.*?)</div>', re.S)
_FOLDER_TITLE = re.compile(r"<title>(.*?)</title>", re.S)


class DriveError(Exception):
    pass


@dataclass
class DriveFile:
    id: str
    name: str
    modified: str = ""        # as Drive shows it, e.g. "Nov 16" or "9:04 AM"
    is_folder: bool = False

    @property
    def is_video(self) -> bool:
        return not self.is_folder and self.name.lower().endswith(VIDEO_EXTENSIONS)


def folder_id(link: str) -> str:
    match = _FOLDER_ID.search(link or "")
    if not match:
        raise DriveError("That doesn't look like a Google Drive folder link.")
    return match.group(1)


def _get(url: str, timeout: float = 30):
    if not url.startswith("https://") or "google" not in url.split("/")[2]:
        raise DriveError("Refused to contact an unexpected address.")
    return urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout)


def parse_listing(page: str) -> tuple[str, list[DriveFile]]:
    """(folder name, files) from Drive's embedded folder view HTML."""
    title = _FOLDER_TITLE.search(page)
    name = html.unescape(title.group(1)).strip() if title else ""
    name = re.sub(r"\s*[-–]\s*Google Drive\s*$", "", name)
    files = []
    for match in _ENTRY.finditer(page):
        block = match.group(0)
        file_title = _TITLE.search(block)
        modified = _MODIFIED.search(block)
        files.append(DriveFile(
            id=match.group(1),
            name=html.unescape(re.sub(r"<[^>]+>", "", file_title.group(1))).strip() if file_title else match.group(1),
            modified=html.unescape(modified.group(1)).strip() if modified else "",
            is_folder="/drive/folders/" in block,
        ))
    return name, files


def list_folder(link: str) -> tuple[str, list[DriveFile]]:
    fid = folder_id(link)
    try:
        with _get(f"https://drive.google.com/embeddedfolderview?id={fid}#list") as response:
            page = response.read().decode("utf-8", "replace")
    except DriveError:
        raise
    except Exception as exc:
        raise DriveError("Couldn't open the folder. Is it shared as \"Anyone with the link\"?") from exc
    name, files = parse_listing(page)
    if not files and "flip-entry" not in page:
        raise DriveError("Google didn't show the folder. Set its sharing to \"Anyone with the link\" and try again.")
    return name, files


def _natural(text: str):
    """"video 2" before "video 10"."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def sort_files(files: list[DriveFile], order: str) -> list[DriveFile]:
    """order: "name" (A–Z, 2 before 10) or "drive" (the order Drive lists them)."""
    videos = [f for f in files if f.is_video]
    if order == "name":
        return sorted(videos, key=lambda f: _natural(f.name))
    return videos


def safe_name(name: str) -> str:
    stem, dot, ext = name.rpartition(".")
    stem = re.sub(r"[^\w.-]+", "_", stem if dot else name).strip("_")[:80] or "video"
    return f"{stem}.{ext.lower()}" if dot else f"{stem}.mp4"


def start_number(folder: Path, files: list["DriveFile"]) -> int:
    """First number to use: after the highest 001_-style file in ``folder`` that isn't from this list."""
    ours = {safe_name(f.name) for f in files}
    best = 0
    if folder.is_dir():
        for entry in folder.iterdir():
            match = re.match(r"(\d{1,5})_(.+)$", entry.name)
            if match and match.group(2) not in ours and not entry.name.endswith(".part"):
                best = max(best, int(match.group(1)))
    return best + 1


def numbered_name(number: int, name: str) -> str:
    return f"{number:03d}_{safe_name(name)}"


def download(file: DriveFile, destination: Path, report: Callable[[float], None] = lambda _f: None) -> Path:
    """Download one public Drive file (big files too: 'confirm=t' skips the virus-scan page)."""
    url = f"https://drive.usercontent.google.com/download?id={file.id}&export=download&confirm=t"
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    try:
        with _get(url, timeout=60) as response:
            kind = (response.headers.get("Content-Type") or "").lower()
            if "text/html" in kind:
                raise DriveError("Google wouldn't give this file (download limit or not shared). Try later.")
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(partial, "wb") as out:
                while chunk := response.read(256 * 1024):
                    done += len(chunk)
                    if done > MAX_FILE_BYTES:
                        raise DriveError("File is bigger than 2 GB.")
                    out.write(chunk)
                    if total:
                        report(done / total)
        partial.replace(destination)
        report(1.0)
        return destination
    except DriveError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise DriveError(f"Download failed: {exc}") from exc


def default_folder_name(drive_name: str) -> str:
    base = re.sub(r"[^\w -]+", "", drive_name).strip() or "Drive"
    return f"{base} {datetime.now():%Y-%m-%d}"
