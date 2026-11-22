from pathlib import Path

import pytest

from tiktok_downloader.products import facebook


def test_caption_and_order(tmp_path):
    for name in ("010_c.mp4", "002_b.mp4", "001_a.mp4", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in facebook.video_files(tmp_path)] == ["001_a.mp4", "002_b.mp4", "010_c.mp4"]
    assert facebook.caption(facebook.DEFAULT_TEMPLATE, "https://s.shopee.ph/6q2", "Clothes Hanger") == \
        "Dito mabibili: https://s.shopee.ph/6q2\nClothes Hanger"


def test_post_reel_flow(tmp_path, monkeypatch):
    video = tmp_path / "001_a.mp4"
    video.write_bytes(b"0" * 1000)
    calls = []

    def fake(self, method, url, params=None, data=None, headers=None, timeout=60):
        short = url.split("v27.0")[-1] if url.startswith(facebook.GRAPH) else url
        calls.append((method, short, dict(params or {}), headers))
        if url.endswith("/video_reels") and params["upload_phase"] == "start":
            return {"video_id": "V1", "upload_url": "https://rupload.facebook.com/video-upload/v27.0/V1"}
        if url.endswith("/V1") and method == "GET":
            return {"post_id": "PAGE_POST1", "status": {"video_status": "ready"}}
        return {"success": True, "id": "C1"}

    monkeypatch.setattr(facebook.FacebookClient, "_call", fake)
    result = facebook.FacebookClient("TOKEN", "PAGE").post_reel(video, "caption", "caption")
    assert (result.video_id, result.post_id, result.commented) == ("V1", "PAGE_POST1", True)
    steps = [(m, u) for m, u, *_ in calls]
    assert steps == [("POST", "/PAGE/video_reels"), ("POST", "https://rupload.facebook.com/video-upload/v27.0/V1"),
                     ("POST", "/PAGE/video_reels"), ("GET", "/V1"), ("GET", "/V1"), ("POST", "/V1/comments")]
    assert calls[1][3]["file_size"] == "1000" and calls[2][2]["description"] == "caption"


def test_refuses_other_hosts():
    with pytest.raises(facebook.FacebookError):
        facebook.FacebookClient("T", "P")._call("POST", "https://evil.example.com/x")


def test_converted_links_and_names():
    from tiktok_downloader.products import excel, subid
    import zipfile
    assert subid.slug_from_subid("NOV11ICspicesstorage1BEFINE") == "spicesstorage"
    assert subid.slug_from_subid("NOV11IChairtieSUNSHINE2PH") == "hairtie"
    assert subid.slug_from_subid("NOV11ICclotheshanger") == "clotheshanger"


def test_comment_failure_still_counts_as_posted(tmp_path, monkeypatch):
    video = tmp_path / "001_a.mp4"
    video.write_bytes(b"0" * 10)
    tried = []

    def fake(self, method, url, params=None, data=None, headers=None, timeout=60):
        if url.endswith("/video_reels") and params["upload_phase"] == "start":
            return {"video_id": "V1", "upload_url": "https://rupload.facebook.com/video-upload/v27.0/V1"}
        if url.endswith("/V1") and method == "GET":
            if params["fields"] == "status":
                return {"status": {"video_status": "ready"}}
            raise facebook.FacebookError("(#100) Tried accessing nonexisting field (post_id)")
        if url.endswith("/comments"):
            tried.append(url.rsplit("/", 2)[-2])
            if "/V1/" not in url:
                raise facebook.FacebookError("(#12) singular statuses API is deprecated for versions v2.4 and higher")
        return {"success": True}

    monkeypatch.setattr(facebook.FacebookClient, "_call", fake)
    monkeypatch.setattr(facebook.time, "sleep", lambda s: None)
    result = facebook.FacebookClient("T", "PAGE").post_reel(video, "c", "c")
    assert result.commented and result.post_id == "" and result.video_id == "V1" and tried == ["V1"]


def test_post_id_helpers():
    assert facebook.split_id("584817111379300_122219645510763039") == ("584817111379300", "122219645510763039")
    assert facebook.split_id(" 122219645510763039 ", "584817111379300") == ("584817111379300", "122219645510763039")
    assert facebook.post_url("584817111379300", "122219645510763039") == \
        "https://www.facebook.com/584817111379300/posts/122219645510763039"


def test_hiccups_are_retried_and_video_id_never_used_as_post_id(tmp_path, monkeypatch):
    video = tmp_path / "001_a.mp4"
    video.write_bytes(b"0" * 10)
    calls = {"status": 0, "post": 0}

    def fake(self, method, url, params=None, data=None, headers=None, timeout=60):
        if url.endswith("/video_reels") and params["upload_phase"] == "start":
            return {"video_id": "2708053046292848", "upload_url": "https://rupload.facebook.com/v/1"}
        if method == "GET" and params["fields"] == "status":
            calls["status"] += 1
            if calls["status"] < 3:
                raise facebook.FacebookError("An error has occurred. No further information is available.")
            return {"status": {"video_status": "ready"}}
        if method == "GET" and params["fields"] == "post_id":
            calls["post"] += 1
            if calls["post"] < 2:
                raise facebook.FacebookError("An unknown error has occurred.")
            return {"post_id": "122219645510763039"}
        return {"success": True}

    monkeypatch.setattr(facebook.FacebookClient, "_call", fake)
    monkeypatch.setattr(facebook.time, "sleep", lambda s: None)
    result = facebook.FacebookClient("T", "PAGE").post_reel(video, "c", "c")
    assert result.post_id == "122219645510763039" and not result.note

    # Facebook never gives it: post ID stays empty (not the video ID)
    def never(self, method, url, params=None, data=None, headers=None, timeout=60):
        if method == "GET":
            raise facebook.FacebookError("An error has occurred. No further information is available.")
        return fake(self, method, url, params, data, headers, timeout)
    monkeypatch.setattr(facebook.FacebookClient, "_call", never)
    result = facebook.FacebookClient("T", "PAGE").post_reel(video, "c", "c")
    assert result.post_id == "" and result.video_id == "2708053046292848" and "pending" not in result.note


def test_posts_on_day_oldest_first(monkeypatch):
    import datetime as dt
    pages = [
        {"data": [{"id": "P_3", "created_time": "2026-11-16T14:30:00+0000", "message": "Dito mabibili: https://s.shopee.ph/c\\nC"},
                  {"id": "P_2", "created_time": "2026-11-16T14:20:00+0000", "message": "Dito mabibili: https://s.shopee.ph/b\\nB"}],
         "paging": {"cursors": {"after": "X"}, "next": "https://graph.facebook.com/next"}},
        {"data": [{"id": "P_1", "created_time": "2026-11-16T14:10:00+0000", "message": "hello"}], "paging": {}},
    ]
    seen = []

    def fake(self, method, url, params=None, data=None, headers=None, timeout=60):
        seen.append(dict(params))
        return pages[len(seen) - 1]

    monkeypatch.setattr(facebook.FacebookClient, "_call", fake)
    posts = facebook.FacebookClient("T", "P").posts_on_day("P", dt.date(2026, 11, 16))
    assert [p["id"] for p in posts] == ["P_1", "P_2", "P_3"] and seen[1]["after"] == "X"
