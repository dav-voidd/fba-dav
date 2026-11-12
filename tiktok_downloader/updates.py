"""Self-update from GitHub Releases.

On start the app asks GitHub for the latest release. If it is newer, the user can
click "Update now": the new .exe is downloaded next to the running one, a tiny helper
script waits for the app to close, swaps the files and starts the new version.
(Running from source? It opens the release page instead.)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from . import __version__

REPO = "dav-voidd/tiktok-downloader"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
FROZEN = getattr(sys, "frozen", False)
_CHUNK = 256 * 1024


@dataclass
class Release:
    version: str            # e.g. "v4.3.0"
    page_url: str
    exe_url: str | None     # the attached .exe, if any


def parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text or "")[:3]) or (0,)


def newer_release(current: str = __version__) -> Release | None:
    """The latest GitHub release if it is newer than ``current``. Never raises."""
    try:
        request = Request(LATEST_API, headers={"User-Agent": "TikTokDownloader",
                                               "Accept": "application/vnd.github+json"})
        with urlopen(request, timeout=8) as response:
            data = json.loads(response.read())
        tag = str(data.get("tag_name", ""))
        if parse_version(tag) <= parse_version(current):
            return None
        exe = next((a.get("browser_download_url") for a in data.get("assets", [])
                    if str(a.get("name", "")).lower().endswith(".exe")), None)
        return Release(tag, data.get("html_url") or RELEASES_PAGE, exe)
    except Exception:
        return None  # offline, rate-limited, no releases yet: no notice


def can_self_update(release: Release) -> bool:
    return FROZEN and sys.platform == "win32" and bool(release.exe_url)


def download_update(release: Release, on_progress: Callable[[float], None]) -> Path:
    """Download the new .exe next to the running one. Returns its path."""
    current = Path(sys.executable)
    target = current.with_name(current.stem + ".new.exe")
    request = Request(release.exe_url, headers={"User-Agent": "TikTokDownloader"})
    with urlopen(request, timeout=60) as response, open(target, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(_CHUNK):
            out.write(chunk)
            done += len(chunk)
            if total:
                on_progress(done / total)
    if target.stat().st_size < 1_000_000:  # sanity check: a real build is many MB
        target.unlink(missing_ok=True)
        raise RuntimeError("The downloaded update looks incomplete. Try again.")
    return target


def install_and_restart(new_exe: Path) -> None:
    """Hand over to a helper script that swaps the .exe once this process exits."""
    current = Path(sys.executable)
    script = Path(tempfile.gettempdir()) / "tiktok_downloader_update.bat"
    script.write_text(
        "@echo off\r\n"
        ":wait\r\n"
        "timeout /t 1 /nobreak >nul\r\n"
        f'tasklist /fi "PID eq {os.getpid()}" | find "{os.getpid()}" >nul && goto wait\r\n'
        f'move /y "{new_exe}" "{current}" >nul\r\n'
        f'start "" "{current}"\r\n'
        'del "%~f0"\r\n',
        encoding="utf-8",
    )
    flags = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags, close_fds=True)
