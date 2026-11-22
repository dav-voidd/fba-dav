"""Self-update from GitHub Releases.

On start the app asks GitHub for the latest release. If it is newer, the user can
click "Update now": the new .exe is downloaded next to the running one, a tiny helper
script waits for the app to close, swaps the files and starts the new version.
(Running from source? It opens the release page instead.)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from . import __version__

REPO = "dav-voidd/tiktok-downloader"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
FROZEN = getattr(sys, "frozen", False)
_CHUNK = 256 * 1024
MAX_UPDATE_BYTES = 300 * 1024 * 1024
# Release files are only ever served from GitHub. Anything else is refused.
TRUSTED_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")


@dataclass
class Release:
    version: str            # e.g. "v4.3.0"
    page_url: str
    exe_url: str | None     # the attached .exe, if any
    sha256_url: str | None  # its published SHA-256 fingerprint (.sha256 file)


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
        assets = {str(a.get("name", "")).lower(): a.get("browser_download_url") for a in data.get("assets", [])}
        exe = next((url for name, url in assets.items() if name.endswith(".exe")), None)
        checksum = next((url for name, url in assets.items() if name.endswith(".sha256")), None)
        return Release(tag, data.get("html_url") or RELEASES_PAGE, exe, checksum)
    except Exception:
        return None  # offline, rate-limited, no releases yet: no notice


def can_self_update(release: Release) -> bool:
    """Only when the release has both the .exe and its fingerprint, served by GitHub.
    Otherwise the user is sent to the release page to download it themselves."""
    return (FROZEN and sys.platform == "win32"
            and _trusted(release.exe_url) and _trusted(release.sha256_url))


def _trusted(url: str | None) -> bool:
    if not url:
        return False
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname in TRUSTED_HOSTS


def _get(url: str, timeout: float):
    if not _trusted(url):
        raise RuntimeError("Refused an update from outside GitHub.")
    return urlopen(Request(url, headers={"User-Agent": "TikTokDownloader"}), timeout=timeout)


def download_update(release: Release, on_progress: Callable[[float], None]) -> Path:
    """Download the new .exe next to the running one and verify it before use."""
    with _get(release.sha256_url, 20) as response:
        expected = (re.findall(r"\b[0-9a-fA-F]{64}\b", response.read().decode("utf-8", "ignore")) or [""])[0].lower()
    if not expected:
        raise RuntimeError("The update has no valid fingerprint.")

    current = Path(sys.executable)
    target = current.with_name(current.stem + ".new.exe")
    digest = hashlib.sha256()
    try:
        with _get(release.exe_url, 60) as response, open(target, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            if total > MAX_UPDATE_BYTES:
                raise RuntimeError("The update file is unexpectedly large.")
            done = 0
            while chunk := response.read(_CHUNK):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if done > MAX_UPDATE_BYTES:
                    raise RuntimeError("The update file is unexpectedly large.")
                if total:
                    on_progress(done / total)
        with open(target, "rb") as check:
            is_program = check.read(2) == b"MZ"  # every Windows .exe starts with "MZ"
        if not is_program or digest.hexdigest() != expected:
            raise RuntimeError("The update failed its safety check and was not installed.")
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise


def install_and_restart(new_exe: Path) -> None:
    """Hand over to a helper script that swaps the .exe once this process exits."""
    current = Path(sys.executable)
    handle, name = tempfile.mkstemp(prefix="tiktok_update_", suffix=".bat")  # unique, private
    os.close(handle)
    script = Path(name)
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
