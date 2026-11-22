"""Post Reels to your own Facebook Page with the official Graph API.

Per video: start upload -> send the file -> publish with the caption -> wait until
Facebook gives the post ID -> comment the caption (with the Shopee link) on it.
Only these Meta hosts are ever contacted: graph.facebook.com and rupload.facebook.com.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from ..errors import log_line

GRAPH = "https://graph.facebook.com/v27.0"
ALLOWED_HOSTS = {"graph.facebook.com", "rupload.facebook.com"}
PUBLISH_WAIT = 10 * 60   # seconds to wait for Facebook to finish processing a Reel
DEFAULT_TEMPLATE = "Dito mabibili: {link}\n{product}"


class FacebookError(Exception):
    def __init__(self, message: str = "", status: int = 0):
        super().__init__(message)
        self.status = status        # HTTP status (429 = Facebook says "slow down")


def _transient(error: Exception) -> bool:
    """Facebook's temporary "try again" errors (codes 1, 2, unknown error)."""
    text = str(error).lower()
    return any(k in text for k in ("an error has occurred", "unknown error", "temporarily", "try again",
                                   "unexpected error", "service unavailable", "couldn't reach"))


@dataclass
class Page:
    id: str
    name: str


@dataclass
class Posted:
    video_id: str
    post_id: str           # "" when Facebook didn't give it yet (use Fix post IDs later)
    commented: bool
    note: str = ""   # what went wrong after publishing (the Reel is live anyway)


def caption(template: str, link: str, product: str) -> str:
    text = (template or DEFAULT_TEMPLATE).replace("{link}", link or "").replace("{product}", product or "")
    return "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()


# ---------------------------------------------------------------- posting log

def _log_path() -> Path:
    from ..config import CONFIG_PATH
    return CONFIG_PATH.parent / "facebook_posts.json"


def load_log() -> dict[str, dict]:
    """{video file path (lowercase): {"video_id", "post_id", "page_id", "posted_at"}} for everything posted."""
    try:
        return json.loads(_log_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_to_log(video: Path, video_id: str, post_id: str, page_id: str) -> None:
    log = load_log()
    log[str(video.resolve()).lower()] = {"video_id": video_id, "post_id": post_id, "page_id": page_id,
                                         "posted_at": time.strftime("%Y-%m-%d %H:%M")}
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(log, indent=1), encoding="utf-8")
    temp.replace(path)


def split_id(full: str, page_id: str = "") -> tuple[str, str]:
    """"584817111379300_122219645510763039" -> (page, post). A bare post ID keeps ``page_id``."""
    full = re.sub(r"[^0-9_]", "", full or "")
    if "_" in full:
        page, _, post = full.partition("_")
        return page, post
    return page_id, full


def post_url(page_id: str, post_id: str) -> str:
    return f"https://www.facebook.com/{page_id}/posts/{post_id}"


def facebook_link(full_id: str) -> str:
    page, post = split_id(full_id)
    return post_url(page, post)


def video_files(folder: Path) -> list[Path]:
    """Videos in the folder, in number order (001_..., 002_... or 1.mp4, 2.mp4)."""
    def order(path: Path):
        match = re.match(r"\d+", path.name)
        return (0, int(match.group()), path.name.lower()) if match else (1, 0, path.name.lower())
    return sorted((p for p in folder.glob("*.mp4") if p.is_file()), key=order)


class FacebookClient:
    def __init__(self, token: str, page_id: str = ""):
        if not token.strip():
            raise FacebookError("Paste your Page access token first.")
        self._token = token.strip()
        self.page_id = page_id

    # ----------------------------------------------------------------- http

    def _call(self, method: str, url: str, params: dict | None = None,
              data: bytes | None = None, headers: dict | None = None, timeout: float = 60) -> dict:
        if (urlsplit(url).hostname or "") not in ALLOWED_HOSTS or not url.startswith("https://"):
            raise FacebookError("Refused to contact an unexpected address.")
        params = dict(params or {})
        if data is None:
            params["access_token"] = self._token
        if method == "GET":
            url, body = f"{url}?{urlencode(params)}", None
        else:
            body = data if data is not None else urlencode(params).encode()
        request = Request(url, data=body, method=method, headers=headers or {})
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read() or b"{}")
        except HTTPError as error:
            try:
                info = json.loads(error.read() or b"{}").get("error", {})
            except ValueError:
                info = {}
            message = info.get("error_user_msg") or info.get("message") or f"HTTP {error.code}"
            log_line(f"facebook HTTP {error.code}", message[:500])
            if info.get("code") == 190:
                raise FacebookError("Your Page token expired or is wrong. Paste a new one.") from error
            if info.get("code") in (10, 200) or "permission" in message.lower():
                raise FacebookError(f"Missing permission: {message}") from error
            raise FacebookError(message, error.code) from error
        except (URLError, TimeoutError) as error:
            raise FacebookError("Couldn't reach Facebook. Check your internet.") from error

    # ------------------------------------------------------------------ api

    def connect(self) -> Page:
        """Check the token and find which Page it belongs to."""
        me = self._call("GET", f"{GRAPH}/me", {"fields": "id,name"})
        if not me.get("id"):
            raise FacebookError("That token didn't return a Page.")
        self.page_id = me["id"]
        return Page(me["id"], me.get("name", "your Page"))

    def post_reel(self, video: Path, text: str, comment: str,
                  on_stage: Callable[[str], None] = lambda _s: None) -> Posted:
        if not self.page_id:
            self.connect()
        reels = f"{GRAPH}/{self.page_id}/video_reels"

        on_stage("Starting upload…")
        start = self._call("POST", reels, {"upload_phase": "start"})
        video_id, upload_url = start.get("video_id"), start.get("upload_url")
        if not video_id or not upload_url:
            raise FacebookError("Facebook didn't accept the upload.")

        on_stage(f"Uploading {video.stat().st_size / 1_048_576:.1f} MB…")
        data = video.read_bytes()
        self._call("POST", upload_url, data=data, timeout=600, headers={
            "Authorization": f"OAuth {self._token}", "offset": "0", "file_size": str(len(data))})

        on_stage("Publishing…")
        self._call("POST", reels, {"upload_phase": "finish", "video_id": video_id,
                                   "video_state": "PUBLISHED", "description": text})

        # From here on the Reel is published: problems below must NOT mark it failed,
        # or pressing Start again would post it twice.
        note = ""
        on_stage("Facebook is processing the video…")
        try:
            post_id = self._wait_for_post(video_id)
        except FacebookError as exc:
            post_id, note = "", f"post ID not ready yet ({exc})"

        if not post_id and not note:
            note = "post ID not ready yet"

        commented, last = False, ""
        if comment.strip():
            on_stage("Commenting the link…")
            full_post = post_id if "_" in post_id else (f"{self.page_id}_{post_id}" if post_id else "")
            targets = [t for t in dict.fromkeys([video_id, full_post]) if t]
            for target in targets:
                try:
                    self._call("POST", f"{GRAPH}/{target}/comments", {"message": comment})
                    commented = True
                    break
                except FacebookError as exc:
                    last = str(exc)
                    log_line("facebook comment target failed", f"{target}: {last[:200]}")
            if not commented:
                note = (note + "; " if note else "") + f"the comment failed ({last})"
        return Posted(video_id, post_id, commented, note)

    def posts_on_day(self, page_id: str, day: "date") -> list[dict]:
        """Every post on the Page published on ``day`` (this PC's time zone), oldest first.

        Each item: {"id": "pageid_postid", "time": "21:04", "message": "..."}."""
        import datetime as dt
        start = dt.datetime.combine(day, dt.time.min)
        since, until = int(start.timestamp()), int((start + dt.timedelta(days=1)).timestamp())
        params = {"fields": "id,created_time,message,permalink_url", "since": since, "until": until, "limit": 100}
        posts, seen = [], set()
        for _ in range(20):                                   # up to 2,000 posts in a day
            data = self._call("GET", f"{GRAPH}/{page_id}/posts", params)
            for post in data.get("data", []):
                if post.get("id") in seen:
                    continue
                seen.add(post["id"])
                created = dt.datetime.strptime(post["created_time"], "%Y-%m-%dT%H:%M:%S%z").astimezone()
                link = post.get("permalink_url") or ""
                if link.startswith("/"):
                    link = "https://www.facebook.com" + link
                posts.append({"id": post["id"], "created": created, "time": created.strftime("%I:%M %p"),
                              "link": link or facebook_link(post["id"]),
                              "message": (post.get("message") or "").strip()})
            after = ((data.get("paging") or {}).get("cursors") or {}).get("after")
            if not after or not (data.get("paging") or {}).get("next"):
                break
            params = {**params, "after": after}
        posts.sort(key=lambda p: p["created"])
        return posts

    def check_post(self, page_id: str, post_id: str) -> str:
        """Returns the post's link if it exists on Facebook; raises FacebookError if not."""
        info = self._call("GET", f"{GRAPH}/{page_id}_{post_id}", {"fields": "id,permalink_url"})
        return info.get("permalink_url") or post_url(page_id, post_id)

    def _wait_for_post(self, video_id: str) -> str:
        """Wait until Facebook finishes the Reel, then read its post ID. Short Facebook hiccups are retried."""
        deadline = time.time() + PUBLISH_WAIT
        hiccups = 0
        while time.time() < deadline:
            try:
                info = self._call("GET", f"{GRAPH}/{video_id}", {"fields": "status"})
            except FacebookError as exc:
                if not _transient(exc) or hiccups >= 12:
                    break                       # give up on the status, still try the post ID below
                hiccups += 1
                time.sleep(30 if exc.status == 429 else 10)
                continue
            status = info.get("status") or {}
            if status.get("video_status") == "error":
                detail = (status.get("processing_phase") or {}).get("error", {}).get("message", "")
                raise FacebookError(f"Facebook couldn't process this video. {detail}".strip())
            publishing = (status.get("publishing_phase") or {}).get("status")
            if status.get("video_status") == "ready" or publishing == "complete":
                break
            time.sleep(10)          # checking more often only earns "429 too many calls"
        return self.find_post_id(video_id)

    def find_post_id(self, video_id: str, attempts: int = 6) -> str:
        """The Page post ID for a Reel (what Business Suite shows). "" if Facebook won't say yet."""
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                value = self._call("GET", f"{GRAPH}/{video_id}", {"fields": "post_id"}).get("post_id")
                if value:
                    return str(value)
            except FacebookError as exc:
                last = exc
                if not _transient(exc):
                    break
            time.sleep(30 if getattr(last, "status", 0) == 429 else min(5 * (attempt + 1), 20))
        if last:
            raise last
        return ""
