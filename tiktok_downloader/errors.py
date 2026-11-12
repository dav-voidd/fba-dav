"""Unexpected-error logging, so a bug never fails silently."""

from __future__ import annotations

import datetime
import traceback

from .config import CONFIG_PATH

LOG_PATH = CONFIG_PATH.parent / "error.log"


def log_exception(exc: BaseException, context: str = "") -> str:
    """Print and append the traceback to error.log; return a one-line summary."""
    details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    print(details)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(LOG_PATH, "a", encoding="utf-8") as log:
            log.write(f"\n[{stamp}] {context}\n{details}")
    except OSError:
        pass
    return f"{type(exc).__name__}: {exc}"


def log_line(context: str, message: str) -> None:
    """Append a one-line note to error.log (for API problems that aren't Python bugs)."""
    print(f"[{context}] {message}")
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(LOG_PATH, "a", encoding="utf-8") as log:
            log.write(f"[{stamp}] {context}: {message}\n")
    except OSError:
        pass
