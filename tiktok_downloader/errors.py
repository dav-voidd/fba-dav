"""Unexpected-error logging, so a bug never fails silently."""

from __future__ import annotations

import datetime
import re
import sys
import threading
import traceback

from .config import CONFIG_PATH

LOG_PATH = CONFIG_PATH.parent / "error.log"
MAX_LOG_BYTES = 1_000_000
_SECRETS = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|gsk_[0-9A-Za-z]{20,}|([?&]key=)[^&\s]+)")


def redact(text: str) -> str:
    """Hide API keys so they never end up in a log someone might share."""
    return _SECRETS.sub(lambda m: (m.group(2) or "") + "[hidden]", text)


def _write(entry: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_LOG_BYTES:
            LOG_PATH.replace(LOG_PATH.with_suffix(".old.log"))  # keep one previous log
        with open(LOG_PATH, "a", encoding="utf-8") as log:
            log.write(redact(entry))
    except OSError:
        pass


def install_crash_handlers() -> None:
    """Log any uncaught error (main thread or background) instead of dying silently."""
    def on_error(exc_type, exc, tb):
        log_exception(exc.with_traceback(tb) if exc else exc_type(), "uncaught")

    sys.excepthook = on_error
    threading.excepthook = lambda args: on_error(args.exc_type, args.exc_value, args.exc_traceback)


def log_exception(exc: BaseException, context: str = "") -> str:
    """Print and append the traceback to error.log; return a one-line summary."""
    details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    print(redact(details))
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    _write(f"\n[{stamp}] {context}\n{details}")
    return redact(f"{type(exc).__name__}: {exc}")


def log_line(context: str, message: str) -> None:
    """Append a one-line note to error.log (for API problems that aren't Python bugs)."""
    print(redact(f"[{context}] {message}"))
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    _write(f"[{stamp}] {context}: {message}\n")
