import hashlib
import io
import sys
from pathlib import Path

import pytest

from tiktok_downloader import tikwm, updates
from tiktok_downloader.errors import redact
from tiktok_downloader.protect import protect, unprotect


def test_keys_are_hidden_in_logs():
    text = "call ...?key=AIzaSyA1b2C3d4E5f6G7h8I9j0K_lMnOpQrStUv&x=1 and gsk_abcdefghijklmnopqrstuvwxyz12"
    cleaned = redact(text)
    assert "AIza" not in cleaned and "gsk_" not in cleaned and "key=[hidden]" in cleaned


def test_only_web_links_are_opened():
    with pytest.raises(tikwm.ApiError):
        tikwm._request("file:///C:/Windows/win.ini")
    assert tikwm._request("https://www.tikwm.com/api/").full_url.startswith("https://")


def test_updates_only_from_github():
    assert updates._trusted("https://github.com/dav-voidd/tiktok-downloader/releases/download/v4.3.0/a.exe")
    assert not updates._trusted("http://github.com/x.exe")
    assert not updates._trusted("https://evil.example.com/a.exe")
    release = updates.Release("v9", "https://github.com/x", "https://github.com/x/a.exe", None)
    assert not updates.can_self_update(release)  # no fingerprint -> manual download only


def test_update_rejected_when_fingerprint_does_not_match(tmp_path, monkeypatch):
    exe = b"MZ" + b"\0" * 2_000_000
    fake_files = {"https://github.com/x/a.exe": exe,
                  "https://github.com/x/a.exe.sha256": (b"0" * 64) + b"  a.exe"}

    class Response(io.BytesIO):
        headers = {"Content-Length": "0"}
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(updates, "_get", lambda url, timeout: Response(fake_files[url]))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "TikTok Downloader.exe"))
    release = updates.Release("v9", "p", "https://github.com/x/a.exe", "https://github.com/x/a.exe.sha256")
    with pytest.raises(RuntimeError, match="safety check"):
        updates.download_update(release, lambda f: None)
    assert not list(tmp_path.glob("*.new.exe"))  # bad download removed

    fake_files["https://github.com/x/a.exe.sha256"] = hashlib.sha256(exe).hexdigest().encode()
    assert updates.download_update(release, lambda f: None).exists()


def test_key_protection_round_trip():
    # On Windows the key is encrypted; elsewhere it's stored as-is. Both read back.
    assert unprotect(protect("AIza-secret")) == "AIza-secret"
    assert unprotect("plain-old-key") == "plain-old-key"
