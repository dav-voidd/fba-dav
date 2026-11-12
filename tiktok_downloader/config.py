"""User settings, persisted as JSON in the user's app-data folder."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _config_dir() -> Path:
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

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            pass  # settings are a convenience; never crash over them
