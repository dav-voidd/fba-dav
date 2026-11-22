"""Connectivity checks and turning network failures into plain-language messages."""

from __future__ import annotations

import socket

NO_INTERNET = "No internet connection. Connect to Wi-Fi and try again."

_OFFLINE_HINTS = (
    "getaddrinfo failed",
    "failed to resolve",
    "name or service not known",
    "temporary failure in name resolution",
    "network is unreachable",
    "no route to host",
    "connection refused",
    "unable to connect",
    "connection aborted",
    "connection reset",
)


def has_internet(host: str = "www.tiktok.com", port: int = 443, timeout: float = 3.0) -> bool:
    """True if we can open a TCP connection to TikTok."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# Note: "timed out" is deliberately NOT here. A slow server is not a missing connection.


def looks_offline(message: str) -> bool:
    text = message.lower()
    return any(hint in text for hint in _OFFLINE_HINTS)
