"""Keeps secrets (API key, Page token) out of settings.json in plain text.

Windows: encrypted with DPAPI, tied to the current Windows user account.
Mac: stored in the macOS Keychain; settings.json only holds a reference to it.
Elsewhere: stored as-is in a settings file only this user can read.
"""

from __future__ import annotations

import base64
import sys

PREFIX = "dpapi:"
KEYCHAIN = "keychain:"
SERVICE = "TikTokDownloader"


def protect(secret: str) -> str:
    if not secret:
        return secret
    if sys.platform == "darwin":
        return _keychain_store(secret)
    if sys.platform != "win32":
        return secret
    try:
        return PREFIX + base64.b64encode(_crypt(secret.encode("utf-8"), encrypt=True)).decode()
    except Exception:
        return secret  # never lose the user's key because encryption failed


def unprotect(stored: str) -> str:
    if stored.startswith(KEYCHAIN):
        return _keychain_read(stored[len(KEYCHAIN):])
    if not stored.startswith(PREFIX):
        return stored  # older plain-text value; it is encrypted on the next save
    try:
        return _crypt(base64.b64decode(stored[len(PREFIX):]), encrypt=False).decode("utf-8")
    except Exception:
        return ""  # unreadable (other user / other PC): ask for the key again


def _crypt(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data, len(data))
    blob_in = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = Blob()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    call = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    ok = call(ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out))  # UI_FORBIDDEN
    if not ok:
        raise OSError("DPAPI failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _keychain_store(secret: str) -> str:
    import hashlib
    import subprocess

    account = "secret-" + hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]
    try:
        subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICE, "-a", account, "-w", secret],
                       check=True, capture_output=True, timeout=10)
        return KEYCHAIN + account
    except Exception:
        return secret  # Keychain unavailable: keep it in the owner-only settings file


def _keychain_read(account: str) -> str:
    import subprocess

    try:
        result = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
                                check=True, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except Exception:
        return ""  # removed from Keychain: ask for it again
