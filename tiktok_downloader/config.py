"""User settings, persisted as JSON in the user's app-data folder."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .protect import protect, unprotect


def _config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TikTokDownloader"
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / "TikTokDownloader"


CONFIG_PATH = _config_dir() / "settings.json"
DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "TikTok"


@dataclass
class Settings:
    output_dir: str = field(default_factory=lambda: str(DEFAULT_OUTPUT_DIR))
    numbered_filenames: bool = True
    quality: str = "balanced"  # "balanced" or "max" (see models.Quality)
    auto_scan: bool = True     # scan products after each batch
    gemini_api_key: str = ""   # free key from https://aistudio.google.com/apikey
    gemini_model: str = ""
    subid_code: str = "IC"     # goes after the date: NOV11 + IC + product
    fb_token: str = ""         # Facebook Page access token (encrypted on disk)
    fb_page_id: str = ""
    fb_page_name: str = ""
    fb_template: str = ""      # Reel caption, e.g. "Dito mabibili: {link}\n{product}"
    fb_delay: int = 30         # seconds between posts

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            settings = cls(**known)
            settings.gemini_api_key = unprotect(str(settings.gemini_api_key or ""))
            settings.fb_token = unprotect(str(settings.fb_token or ""))
            settings.gemini_model = ""  # always start on the newest Flash; old fallbacks were slow
            return settings
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = asdict(self)
            data["gemini_api_key"] = protect(self.gemini_api_key)  # never stored in plain text
            data["fb_token"] = protect(self.fb_token)
            temp = CONFIG_PATH.with_suffix(".tmp")
            temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            if sys.platform != "win32":
                os.chmod(temp, 0o600)  # only this user can read it
            temp.replace(CONFIG_PATH)  # atomic: a crash mid-save can't corrupt settings
        except OSError:
            pass  # settings are a convenience; never crash over them
