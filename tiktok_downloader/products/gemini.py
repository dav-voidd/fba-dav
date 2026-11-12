"""Gemini client for batch product recognition, the way the Gemini app does it.

Videos are uploaded once with the Files API (in parallel, as soon as each one finishes
downloading), then ONE request asks Gemini about every video in the batch together.
Free tier friendly: a batch of 10 is a single request.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..errors import log_line
from .common import ScanError, normalise_result

API_ROOT = "https://generativelanguage.googleapis.com"
KEYS_URL = "https://aistudio.google.com/apikey"
DEFAULT_MODEL = "gemini-flash-latest"
KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{30,}")

PROMPT = """You are helping a Shopee affiliate in the Philippines.
Above are {count} TikTok videos, each introduced by its number and caption. For EACH video,
name the product that video is SELLING.

Use the visuals AND the audio together:
- The visuals show WHAT the product is: the item being shown, held, opened, used or
  demonstrated, usually in the centre of the frame.
- The speech, on-screen text, caption and hashtags CONFIRM or NAME it ("tissue box po ito",
  #tissueholder). Use that name when it fits what is shown. Hashtags joined together are
  words: #spicesrack = spices rack.
- If the audio is only music, lyrics or talk that never names the product, go by the visuals.
- Ignore everything else in the scene: furniture, the room, other objects nearby, the
  person's clothes or phone. Never pick a background object because it is bigger or clearer.
- Judge each video on its own. Do not mix up products between videos.

For each video return:
- video: its number
- product_name: what a buyer would type in the Shopee PH search bar to find this exact item.
  Specific, 3-8 words, plain English; include product type and key feature/size. No hashtags,
  emojis, prices or seller talk. Brand only if clearly visible.
- short_name: the core product in at most 2 words, lowercase, the way a seller would tag it
  (e.g. "tissue holder", "roach killer", "spices storage", "led flashlight").
- confidence: 0 to 1. Higher when the visuals and the audio/caption agree."""

SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "video": {"type": "INTEGER"},
            "product_name": {"type": "STRING"},
            "short_name": {"type": "STRING"},
            "confidence": {"type": "NUMBER"},
        },
        "required": ["video", "product_name", "short_name", "confidence"],
    },
}


@dataclass
class UploadedVideo:
    name: str   # "files/abc123"
    uri: str
    mime_type: str


def find_key(text: str) -> str | None:
    match = KEY_PATTERN.search(text or "")
    return match.group(0) if match else None


def check_key(api_key: str) -> tuple[bool, str]:
    try:
        with urlopen(f"{API_ROOT}/v1beta/models?key={api_key.strip()}&pageSize=1", timeout=15):
            return True, "Key works. You're all set!"
    except HTTPError as error:
        if error.code in (400, 401, 403):
            return False, "Google rejected this key. Copy it again from AI Studio."
        return False, f"Google returned an error (HTTP {error.code}). Try again in a moment."
    except OSError:
        return False, "No internet connection. Connect to Wi-Fi and try again."


class GeminiClient:
    MAX_ATTEMPTS = 6

    def __init__(self, api_key: str, model: str = "",
                 on_status: Callable[[str], None] | None = None) -> None:
        if not api_key.strip():
            raise ScanError("No Gemini API key set.")
        self._key = api_key.strip()
        self._model = model or DEFAULT_MODEL
        self._fallbacks: list[str] | None = None
        self._status = on_status or (lambda _msg: None)

    @property
    def model(self) -> str:
        return self._model

    # ------------------------------------------------------------- uploads

    def upload(self, path: Path, mime_type: str = "video/mp4") -> UploadedVideo:
        """Upload one file with the resumable Files API and wait until Gemini can use it."""
        data = path.read_bytes()
        start = Request(
            f"{API_ROOT}/upload/v1beta/files?key={self._key}",
            data=json.dumps({"file": {"display_name": path.name[:100]}}).encode(),
            headers={
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(len(data)),
                "X-Goog-Upload-Header-Content-Type": mime_type,
                "Content-Type": "application/json",
            },
        )
        with _open(start, 60) as response:
            upload_url = response.headers.get("X-Goog-Upload-URL")
        if not upload_url:
            raise ScanError("Gemini did not accept the upload.")
        send = Request(upload_url, data=data, headers={
            "Content-Length": str(len(data)),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        })
        with _open(send, 300) as response:
            info = json.loads(response.read()).get("file", {})
        video = UploadedVideo(info["name"], info["uri"], info.get("mimeType", mime_type))
        self._wait_active(video, info.get("state"))
        return video

    def _wait_active(self, video: UploadedVideo, state: str | None, limit: float = 180) -> None:
        deadline = time.monotonic() + limit
        while state != "ACTIVE":
            if state == "FAILED":
                raise ScanError("Gemini could not process this video.")
            if time.monotonic() > deadline:
                raise ScanError("Gemini took too long to process the upload.")
            time.sleep(2)
            with _open(Request(f"{API_ROOT}/v1beta/{video.name}?key={self._key}"), 30) as response:
                state = json.loads(response.read()).get("state")

    def delete(self, video: UploadedVideo) -> None:
        try:
            _open(Request(f"{API_ROOT}/v1beta/{video.name}?key={self._key}", method="DELETE"), 20).close()
        except Exception:
            pass  # files expire on their own after 48 hours

    # ------------------------------------------------------------- analysis

    def identify_batch(self, videos: list[tuple[int, str, UploadedVideo]],
                       timeout: float = 90) -> dict[int, dict]:
        """``videos`` = [(number, caption, upload)]. Returns {number: result}."""
        parts: list[dict] = []
        for number, caption, video in videos:
            parts.append({"text": f"Video {number}. Caption: {_quote(caption)}"})
            parts.append({"file_data": {"mime_type": video.mime_type, "file_uri": video.uri}})
        parts.append({"text": PROMPT.format(count=len(videos))})
        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
                "temperature": 0.2,
                "mediaResolution": "MEDIA_RESOLUTION_LOW",  # plenty to recognise a product
                "thinkingConfig": {"thinkingBudget": 0},     # answer straight away
            },
        }
        config = body["generationConfig"]
        last_error = "Gemini did not answer."
        for _ in range(self.MAX_ATTEMPTS):
            self._status(f"Gemini is watching {len(videos)} video(s) ({self._model})…")
            status, data = _post_json(
                f"{API_ROOT}/v1beta/models/{self._model}:generateContent?key={self._key}", body, timeout)
            if status == 200:
                return parse_batch(data)

            last_error = (data.get("error") or {}).get("message", f"HTTP {status}")
            log_line(f"gemini {self._model} HTTP {status}", last_error[:300])
            if status in (400, 401, 403) and "key" in last_error.lower():
                raise ScanError("Gemini API key is invalid. Connect Gemini again.")
            if status == 400:
                rejected = [opt for opt in ("thinkingConfig", "mediaResolution")
                            if opt in config and opt.lower() in last_error.lower().replace("_", "")]
                if rejected or "thinking" in last_error.lower():
                    for opt in rejected or ["thinkingConfig"]:
                        config.pop(opt, None)
                    continue
            if status == 404 or (status == 429 and "limit: 0" in last_error.lower()):
                self._switch_model(f"{self._model} isn't available on your free plan")
                continue
            if status in (500, 503, 504):
                reason = ("is too slow right now" if status == 504 else "is busy on Google's side")
                try:
                    self._switch_model(f"{self._model} {reason}")
                except ScanError:
                    self._status("Google's Gemini servers are busy. Retrying in 15s…")
                    time.sleep(15)
                continue
            if status == 429:
                wait = min(_retry_delay(last_error), 65)
                self._status(f"Gemini free limit hit. Waiting {int(wait)}s…")
                time.sleep(wait)
                continue
            raise ScanError(last_error)
        raise ScanError(last_error)

    def _switch_model(self, reason: str) -> None:
        if self._fallbacks is None:
            self._fallbacks = self._flash_models()
        remaining = [m for m in self._fallbacks if m != self._model]
        if not remaining:
            raise ScanError(f"{reason}, and no other Gemini model was found.")
        self._fallbacks = remaining
        self._model = remaining[0]
        self._status(f"{reason}. Switching to {self._model}…")

    def _flash_models(self) -> list[str]:
        with _open(Request(f"{API_ROOT}/v1beta/models?key={self._key}&pageSize=200"), 20) as response:
            models = json.loads(response.read()).get("models", [])
        names = [
            m["name"].split("/", 1)[1] for m in models
            if "generateContent" in m.get("supportedGenerationMethods", [])
            and "flash" in m["name"]
            and not any(bad in m["name"] for bad in ("tts", "image", "live", "audio", "embedding"))
        ]
        return rank_models(names)


def rank_models(names: list[str]) -> list[str]:
    """Stable before preview, newest first; each Flash followed by its Flash-Lite,
    which is usually far less busy when Google is overloaded."""
    def key(name: str):
        return ("preview" in name or "exp" in name, -_version(name), "lite" in name, name)
    return sorted(set(names), key=key)


def parse_batch(data: dict) -> dict[int, dict]:
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "empty response")
        raise ScanError(f"Gemini returned no answer ({reason}).") from exc
    results: dict[int, dict] = {}
    for entry in json.loads(text):
        try:
            results[int(entry["video"])] = normalise_result(entry)
        except (KeyError, TypeError, ValueError, ScanError):
            continue
    return results


def _version(name: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", name)
    return float(match.group(1)) if match else 0.0


def _quote(text: str) -> str:
    return '"' + " ".join((text or "").replace('"', "'").split())[:300] + '"'


def _open(request: Request, timeout: float):
    try:
        return urlopen(request, timeout=timeout)
    except HTTPError as error:
        try:
            message = json.loads(error.read() or b"{}").get("error", {}).get("message", "")
        except ValueError:
            message = ""
        log_line(f"gemini files HTTP {error.code}", message[:300])
        if error.code in (400, 401, 403) and "key" in message.lower():
            raise ScanError("Gemini API key is invalid. Connect Gemini again.") from error
        raise ScanError(message or f"Gemini upload failed (HTTP {error.code}).") from error


def _post_json(url: str, body: dict, timeout: float) -> tuple[int, dict]:
    request = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        try:
            return error.code, json.loads(error.read() or b"{}")
        except ValueError:
            return error.code, {}
    except TimeoutError:
        return 504, {"error": {"message": "Gemini took too long to answer."}}
    except URLError as error:
        if isinstance(error.reason, TimeoutError):
            return 504, {"error": {"message": "Gemini took too long to answer."}}
        raise


def _retry_delay(message: str) -> float:
    match = re.search(r"retry in ([\d.]+)s", message, re.IGNORECASE)
    return float(match.group(1)) + 1 if match else 30
