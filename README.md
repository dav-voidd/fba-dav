# 🎵 TikTok Downloader

A clean, ad-free desktop app for downloading TikTok videos **in bulk**, **in order**, and **without the watermark**.

Paste 1 link or 100. The app queues them and downloads them one by one, in the order you pasted them.

## Features

- **Bulk paste:** drop in any amount of text and every TikTok link is detected automatically, including short `vt.` / `vm.` links.
- **Ordered queue:** files are numbered `001_`, `002_`, … to match your paste order (this can be turned off).
- **No watermark, two qualities:** *Balanced* (~4–5 MB H.264, plays everywhere) or *Max quality* (largest file TikTok has).
- **Live preview:** animated thumbnail, caption and progress of the current video; click any row to preview it.
- **Photo slideshows** are saved as a folder of images.
- **Sub ID scanner (free, Gemini):** each video is uploaded to Gemini as soon as it downloads, then Gemini watches up to 10 videos per request (picture and sound), names each product and builds an affiliate sub ID like `NOV11ICspicesstorage1` (repeats are numbered). Copy one or all from the **🛍 Sub IDs** window, edit any of them by hand, or click **Shopee ↗** to open a Shopee search sorted by best sellers. Needs a free key from [Google AI Studio](https://aistudio.google.com/apikey).
- **Live progress:** each video has its own progress bar and status, plus an overall progress bar.
- **Duplicates skipped:** the same link pasted twice is only queued once.
- **Stop / Retry failed:** stop after the current video, and retry only the links that failed.
- **No ads, no tracking, no accounts.**

## Quick start

Requires **Python 3.10+**.

```bash
git clone https://github.com/<dav-voidd>/tiktok-downloader.git
cd tiktok-downloader
pip install -r requirements.txt
python main.py
```

**VS Code:** open the folder and press **F5**. The dependencies install automatically on the first run.

## Build a standalone .exe (Windows)

```bash
build.bat
```

The app is created at `dist/TikTok Downloader.exe`.

## Project structure

```
tiktok-downloader/
├── main.py                     # entry point (+ first-run dependency install)
├── tiktok_downloader/
│   ├── __init__.py             # app name & version
│   ├── models.py               # QueueItem, Status
│   ├── links.py                # link detection from pasted text
│   ├── config.py               # persisted user settings
│   ├── tikwm.py                # tikwm.com API client (clean media URLs)
│   ├── downloader.py           # download engine: tikwm first, yt-dlp fallback
│   ├── network.py              # connectivity check, offline detection
│   ├── errors.py               # error logging
│   ├── products/               # sub ID scanner
│   │   ├── gemini.py           # Gemini Files API upload + batch recognition
│   │   ├── scanner.py          # uploads while downloading, 10 videos per request
│   │   ├── subid.py            # sub ID generator (NOV11 + IC + product + #)
│   │   ├── shopee.py           # Shopee search links (best sellers first)
│   │   └── common.py           # shared result cleanup
│   └── ui/
│       ├── theme.py            # colors & fonts
│       ├── widgets.py          # reusable styled widgets, QueueRow
│       ├── panels.py           # TopBar, Composer, QueuePanel, StatusBar
│       ├── preview.py          # animated preview card
│       ├── products_window.py  # Sub IDs window: edit + copy
│       ├── ai_setup.py         # guided "Connect Gemini" window
│       └── app.py              # main window, wires UI <-> engine
├── tests/                      # pytest unit tests
├── build.bat                   # PyInstaller build script
└── requirements.txt
```

The download engine has no dependency on the UI. It reports progress through a small `DownloadListener` interface, and the UI marshals those callbacks onto the Tk thread.

## Troubleshooting

If downloads start failing, TikTok has probably changed something. Press **⟳ Update download engine** in the app, or run `pip install -U yt-dlp`, then restart.

## Disclaimer

This app is for personal use. Only download content you have the right to download, and respect creators and TikTok's Terms of Service.

## Credits

Built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) and [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## License

[MIT](LICENSE)
