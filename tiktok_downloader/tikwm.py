"""Client for the tikwm.com API: resolves a TikTok link to direct, watermark-free media URLs.

This is the same approach "ssstik"-style websites use: a server that talks to TikTok
for us and hands back clean video/image links. Only the standard library is used.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Post

API_URL = "https://www.tikwm.com/api/"
SITE = "https://www.tikwm.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
_CHUNK = 256 * 1024


class ApiError(Exception):
    """tikwm could not resolve the link (private, deleted, region-locked, rate-limited…)."""


class TikwmClient:
    # The free API allows about one request per second.
    MIN_INTERVAL = 1.1
    MAX_ATTEMPTS = 4

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_call = 0.0

    def get_post(self, url: str) -> Post:
        for _ in range(self.MAX_ATTEMPTS):
            self._throttle()
            payload = get_json(f"{API_URL}?{urlencode({'url': url, 'hd': 1})}")
            if payload.get("code") == 0 and payload.get("data"):
                return parse_post(payload["data"])
            message = str(payload.get("msg") or "Unknown API error")
            if "limit" not in message.lower():
                raise ApiError(message)
            time.sleep(1.5)  # rate-limited: back off and retry
        raise ApiError("Download service is busy. Try again in a moment.")

    def _throttle(self) -> None:
        with self._lock:
            wait = self.MIN_INTERVAL - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()


def parse_post(data: dict) -> Post:
    author = data.get("author") or {}
    return Post(
        id=str(data.get("id", "")),
        author=author.get("unique_id") or author.get("nickname") or "unknown",
        caption=(data.get("title") or "").strip(),
        duration=int(data.get("duration") or 0),
        cover_url=_absolute(data.get("cover") or data.get("origin_cover")),
        preview_url=_absolute(data.get("ai_dynamic_cover") or data.get("cover")),
        # "play" is the standard-quality H.264 copy (plays everywhere, ~4-5 MB).
        # "hdplay" is often HEVC/H.265, which Windows can't play without a paid codec.
        video_url=_absolute(data.get("play") or data.get("hdplay")),
        hd_video_url=_absolute(data.get("hdplay") or data.get("play")),
        image_urls=[_absolute(u) for u in (data.get("images") or [])],
    )


def _absolute(url: str | None) -> str | None:
    if not url:
        return None
    return SITE + url if url.startswith("/") else url


# ------------------------------------------------------------------ HTTP helpers

def _request(url: str) -> Request:
    return Request(url, headers={"User-Agent": USER_AGENT})


def get_bytes(url: str, timeout: float = 20) -> bytes:
    """GET ``url``. Uses curl_cffi (looks like real Chrome) when installed, else urllib."""
    try:
        from curl_cffi import requests as browser
    except ImportError:
        browser = None
    if browser is not None:
        response = browser.get(url, impersonate="chrome", timeout=timeout)
        response.raise_for_status()
        return response.content
    with urlopen(_request(url), timeout=timeout) as response:
        return response.read()


def get_json(url: str, timeout: float = 20) -> dict:
    return json.loads(get_bytes(url, timeout).decode("utf-8"))


def download_file(url: str, destination: Path,
                  on_progress: Callable[[float], None] | None = None,
                  expect: str | None = None) -> Path:
    """Stream ``url`` to ``destination`` (via a .part file, so failures leave no junk)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    try:
        with urlopen(_request(url), timeout=30) as response, open(partial, "wb") as out:
            content_type = response.headers.get("Content-Type", "")
            if expect and expect not in content_type and "octet-stream" not in content_type:
                raise ApiError(f"Expected {expect}, got '{content_type or 'unknown'}'")
            total = int(response.headers.get("Content-Length") or 0)
            received = 0
            while chunk := response.read(_CHUNK):
                out.write(chunk)
                received += len(chunk)
                if total and on_progress:
                    on_progress(received / total)
        partial.replace(destination)
        return destination
    finally:
        partial.unlink(missing_ok=True)
