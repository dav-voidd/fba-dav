<div align="center">

# 🎵 TikTok Downloader

**Paste 30 links → get 30 clean videos + ready-to-copy affiliate sub IDs.**
Bulk, in order, no watermark, no ads.

[![Release](https://img.shields.io/github/v/release/dav-voidd/tiktok-downloader?color=7C6CFF&label=release&style=for-the-badge)](https://github.com/dav-voidd/tiktok-downloader/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/dav-voidd/tiktok-downloader/total?color=25F4EE&style=for-the-badge)](https://github.com/dav-voidd/tiktok-downloader/releases)
[![Tests](https://img.shields.io/github/actions/workflow/status/dav-voidd/tiktok-downloader/tests.yml?label=tests&style=for-the-badge)](https://github.com/dav-voidd/tiktok-downloader/actions/workflows/tests.yml)

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows&logoColor=white)
![Gemini](https://img.shields.io/badge/AI-Gemini-8E75B2?logo=googlegemini&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-FE2C55)

### [⬇️ Download the app](https://github.com/dav-voidd/tiktok-downloader/releases/latest)

</div>

---

## ✨ Features

| | |
|---|---|
| 📥 **Bulk & ordered** | Paste any amount of links. Downloads one by one, numbered `001_`, `002_`… |
| 🚫 **No watermark** | *Balanced* (H.264, plays everywhere) or *Max quality* |
| 👀 **Live preview** | Animated thumbnail, caption and progress of each video |
| 🤖 **AI product scan** | Gemini watches each video (picture + sound) and names the product |
| 🏷️ **Sub ID generator** | `NOV12ICspicesstorage1`: one click copies them all |
| 🛒 **Shopee links** | Opens a Shopee search for each product, best sellers first |
| 🖼️ **Slideshows** | Photo posts are saved as a folder of images |
| ⬆️ **Auto-update** | One click installs the newest release, verified by SHA-256 |
| 🔐 **Private** | Your Gemini key is encrypted on your PC and never leaves it except to Google |

## 🚀 Quick start

**Just use it:** download the `.exe` from [Releases](https://github.com/dav-voidd/tiktok-downloader/releases/latest) and open it.
> Windows may say *"protected your PC"*: click **More info → Run anyway**.

**Run from code:**
```bash
git clone https://github.com/dav-voidd/tiktok-downloader.git
cd tiktok-downloader
python main.py        # installs what it needs on first run
```

## 🏷️ Sub IDs in 3 steps

1. 🔑 First scan opens **Connect Gemini**: get a free key at [AI Studio](https://aistudio.google.com/apikey) (no card).
2. 📥 Download your videos. They're scanned automatically, 5 at a time.
3. 📋 Open **🛍 Sub IDs** → **Copy all**.

```
NOV12  +  IC  +  spicesstorage  +  1
date      code   product (2 words)  repeat #
```

## ❓ FAQ

<details>
<summary>Is it free?</summary>

Yes. The app is free and has no ads. The Gemini key is free too (no credit card).
</details>

<details>
<summary>A video failed to download?</summary>

Press **Retry failed**. Private or deleted videos can't be downloaded.
</details>

<details>
<summary>The scan is slow or says "busy"?</summary>

Google's free Gemini servers get busy sometimes. The app switches models and retries on its own, so just wait.
</details>

<details>
<summary>Can I change the sub ID?</summary>

Yes. Click any sub ID in the **🛍 Sub IDs** window to edit it, or change the `IC` code at the top.
</details>

## 🧱 Built with

[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) · [tikwm](https://www.tikwm.com) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Gemini API](https://ai.google.dev)

<details>
<summary>📁 Project structure</summary>

```
main.py                    entry point
tiktok_downloader/
├── downloader.py          download engine (tikwm → yt-dlp fallback)
├── tikwm.py · links.py · config.py · models.py · network.py · errors.py
├── products/              gemini.py · scanner.py · subid.py · shopee.py
└── ui/                    app.py · panels.py · preview.py · products_window.py · …
tests/                     pytest
```
</details>

<details>
<summary>🛠️ Build the .exe yourself</summary>

Double-click `build.bat` → `dist/TikTok Downloader.exe`
</details>

---

<div align="center">

⚠️ For personal use. Respect creators and TikTok's Terms of Service.

Made with 💜 by [dabid](https://github.com/dav-voidd) · [MIT License](LICENSE)

</div>
