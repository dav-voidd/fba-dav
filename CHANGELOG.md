# 📝 Changelog

## v4.1.0 · First public release 🎉

**⬇️ [Download TikTok Downloader.exe](https://github.com/dav-voidd/tiktok-downloader/releases/latest)**

### ✨ Features
- 📥 Bulk download: paste any amount of TikTok links, saved in order (`001_`, `002_`…)
- 🚫 No watermark: *Balanced* (H.264) or *Max quality*
- 👀 Live preview with animated thumbnails
- 🤖 Gemini product scanner: watches each video (picture + sound), 5 at a time
- 🏷️ Sub ID generator: `NOV12ICspicesstorage1`, with one-click **Copy all**
- 🛒 Shopee search links sorted by best sellers
- 🔑 Guided **Connect Gemini** setup (key detected automatically when copied)
- 📶 Clear "No internet" warning, auto-retry, and error log

### 🛠️ Under the hood
- tikwm first, yt-dlp fallback
- Uploads to Gemini while downloading; batches of 5, two at a time
- Switches to a less busy Gemini model automatically when Google is overloaded
