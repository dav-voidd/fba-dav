from tiktok_downloader.links import extract_links, shorten


def test_extracts_in_order_and_removes_duplicates():
    text = """
    check this https://www.tiktok.com/@a/video/111 and
    https://vt.tiktok.com/ZSabc123/, also https://www.tiktok.com/@a/video/111
    not this https://youtube.com/watch?v=x
    https://vm.tiktok.com/ZMxyz/.
    """
    assert extract_links(text) == [
        "https://www.tiktok.com/@a/video/111",
        "https://vt.tiktok.com/ZSabc123/",
        "https://vm.tiktok.com/ZMxyz/",
    ]


def test_no_links():
    assert extract_links("nothing here") == []


def test_shorten():
    assert shorten("https://www.tiktok.com/@a/video/1") == "tiktok.com/@a/video/1"
    assert shorten("https://x.tiktok.com/" + "a" * 100, 20).endswith("…")


def test_offline_detection():
    from tiktok_downloader.network import looks_offline
    assert looks_offline("<urlopen error [Errno 11001] getaddrinfo failed>")
    assert not looks_offline("Video unavailable")




def test_update_version_compare():
    from tiktok_downloader.updates import parse_version
    assert parse_version("v4.3.0") > parse_version("4.2.0")
    assert parse_version("v4.2.0") == parse_version("4.2.0")
    assert parse_version("v4.10.0") > parse_version("v4.9.9")
