from tiktok_downloader.downloader import _has_video, _safe
from tiktok_downloader.tikwm import parse_post


def test_parse_video_post():
    post = parse_post({
        "id": "77", "title": "hello", "duration": 22,
        "author": {"unique_id": "suishoupp"},
        "cover": "https://x/c.jpg", "ai_dynamic_cover": "https://x/a.webp",
        "play": "https://x/sd.mp4", "hdplay": "https://x/hd.mp4",
    })
    assert post.video_url == "https://x/sd.mp4"  # H.264, plays everywhere
    assert post.preview_url == "https://x/a.webp"
    assert post.display_title == "@suishoupp · hello"
    assert not post.is_slideshow


def test_parse_slideshow_and_relative_urls():
    post = parse_post({"id": "1", "author": {"unique_id": "a"},
                       "play": "", "images": ["https://x/1.jpg", "https://x/2.jpg"],
                       "cover": "/video/cover/1.jpeg"})
    assert post.is_slideshow and len(post.image_urls) == 2
    assert post.cover_url == "https://www.tikwm.com/video/cover/1.jpeg"


def test_ytdlp_video_detection():
    assert not _has_video({"formats": [{"vcodec": "none", "ext": "mp3"}]})
    assert _has_video({"formats": [{"vcodec": "none"}, {"vcodec": "h264"}]})
    assert _has_video({"formats": [{"ext": "mp4", "width": 576}]})


def test_safe_filename():
    assert _safe("we!rd name/ok") == "we_rd_name_ok"


def test_get_post_retries_a_stall(monkeypatch):
    from tiktok_downloader import tikwm
    calls = []

    def flaky(url, timeout=12):
        calls.append(url)
        if len(calls) < 3:
            raise TimeoutError("Operation timed out after 20005 milliseconds with 0 bytes received")
        return {"code": 0, "data": {"id": "1", "author": {"unique_id": "a"}, "play": "https://x/v.mp4"}}

    monkeypatch.setattr(tikwm, "get_json", flaky)
    monkeypatch.setattr(tikwm.time, "sleep", lambda s: None)
    client = tikwm.TikwmClient()
    monkeypatch.setattr(client, "_throttle", lambda: None)
    post = client.get_post("https://www.tiktok.com/@a/video/1")
    assert post.id == "1" and len(calls) == 3


def test_numbering_continues_in_the_same_folder(tmp_path):
    from tiktok_downloader.downloader import assign_numbers
    from tiktok_downloader.models import QueueItem
    for name in ("001_a_1.mp4", "002_b_2.mp4", "030_c_3.mp4", "031_x.mp4.part", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    batch = [QueueItem(1, "u1"), QueueItem(2, "u2")]
    assign_numbers(batch, tmp_path)
    assert [i.file_number for i in batch] == [31, 32]          # continues after 030
    retry = QueueItem(3, "u3", file_number=5)
    new = QueueItem(4, "u4")
    assign_numbers([retry, new], tmp_path)
    assert retry.file_number == 5 and new.file_number == 31    # retry keeps its own number
    fresh = [QueueItem(1, "u")]
    assign_numbers(fresh, tmp_path / "empty")
    assert fresh[0].file_number == 1                           # a new folder starts at 001
