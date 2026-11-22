from tiktok_downloader.products import gdrive

PAGE = """<html><head><title>Nov 18 videos - Google Drive</title></head><body>
<div class="flip-entry" id="entry-AAA111bbb222"><a href="https://drive.google.com/file/d/AAA111bbb222/view?usp=drive_web">
<div class="flip-entry-title">video 10.mp4</div></a><div class="flip-entry-last-modified"><div>Nov 18</div></div></div>
<div class="flip-entry" id="entry-CCC333ddd444"><a href="https://drive.google.com/file/d/CCC333ddd444/view?usp=drive_web">
<div class="flip-entry-title">video 2.MP4</div></a><div class="flip-entry-last-modified"><div>Nov 17</div></div></div>
<div class="flip-entry" id="entry-EEE555fff666"><a href="https://drive.google.com/drive/folders/EEE555fff666">
<div class="flip-entry-title">old stuff</div></a></div>
<div class="flip-entry" id="entry-GGG777hhh888"><a href="https://drive.google.com/file/d/GGG777hhh888/view">
<div class="flip-entry-title">notes &amp; links.docx</div></a></div>
</body></html>"""


def test_folder_link_and_listing():
    assert gdrive.folder_id("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMn?usp=sharing") == "1AbCdEfGhIjKlMn"
    name, files = gdrive.parse_listing(PAGE)
    assert name == "Nov 18 videos" and len(files) == 4
    assert files[2].is_folder and not files[3].is_video and files[3].name == "notes & links.docx"
    ordered = gdrive.sort_files(files, "name")
    assert [f.name for f in ordered] == ["video 2.MP4", "video 10.mp4"]       # 2 before 10
    assert [f.name for f in gdrive.sort_files(files, "drive")] == ["video 10.mp4", "video 2.MP4"]
    assert gdrive.numbered_name(1, "video 2.MP4") == "001_video_2.mp4"


def test_drive_numbering_continues_after_other_files(tmp_path):
    files = [gdrive.DriveFile("A" * 12, "clip.mp4"), gdrive.DriveFile("B" * 12, "next.mp4")]
    assert gdrive.start_number(tmp_path, files) == 1                    # empty folder
    (tmp_path / "030_shop_123.mp4").write_bytes(b"x")                   # a TikTok download
    assert gdrive.start_number(tmp_path, files) == 31
    (tmp_path / "031_clip.mp4").write_bytes(b"x")                       # one of ours, already saved
    assert gdrive.start_number(tmp_path, files) == 31                   # doesn't push the start
