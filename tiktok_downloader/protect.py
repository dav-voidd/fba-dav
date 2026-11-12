"""Encrypts secrets (the API key) with Windows DPAPI before they touch the disk.

DPAPI ties the encryption to the current Windows user account: the same user on the
same PC can read it back, but a copied settings.json is useless to anyone else.
On other systems the value is stored as-is (there is no built-in equivalent).
"""

from __future__ import annotations

import base64
import sys

PREFIX = "dpapi:"


def protect(secret: str) -> str:
    if not secret or sys.platform != "win32":
        return secret
    try:
        return PREFIX + base64.b64encode(_crypt(secret.encode("utf-8"), encrypt=True)).decode()
    except Exception:
        return secret  # never lose the user's key because encryption failed


def unprotect(stored: str) -> str:
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
