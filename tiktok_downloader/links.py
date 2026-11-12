"""Finding TikTok links inside arbitrary pasted text."""

from __future__ import annotations

import re

_TIKTOK_URL = re.compile(r"https?://(?:[\w-]+\.)?tiktok\.com/[^\s\"'<>]+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?)]}"


def extract_links(text: str) -> list[str]:
    """Return every TikTok URL in ``text`` in order of appearance, without duplicates.

    Works with full links (tiktok.com/@user/video/…) and short links (vt./vm.tiktok.com/…).
    """
    seen: set[str] = set()
    links: list[str] = []
    for match in _TIKTOK_URL.findall(text):
        url = match.rstrip(_TRAILING_PUNCTUATION)
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def shorten(url: str, limit: int = 60) -> str:
    """Display-friendly version of a URL: no scheme, truncated with an ellipsis."""
    text = re.sub(r"^https?://(www\.)?", "", url)
    return text if len(text) <= limit else text[: limit - 1] + "…"
