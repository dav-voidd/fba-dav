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
