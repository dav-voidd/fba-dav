# 📝 Changelog

## v4.3.0 · Security

- 🔐 Gemini key is **encrypted** with Windows DPAPI (only your Windows account can read it)
- ✅ Updates are **verified** before installing: GitHub-only, SHA-256 fingerprint, real Windows app
- 🌐 Only web links are ever opened; downloads are size-capped
- 📝 Error log hides API keys and stays under 1 MB
- 💥 Crashes are caught and logged, with a friendly message instead of the app vanishing

## v4.2.0

- 📅 **Sub ID date is editable:** type any date (`NOV13`, `DEC25`) or use **Today** / **Tomorrow**
- ⬆️ **One-click updates:** when a new version is released, click **Update now** and the app updates and restarts itself

## v4.1.0 · First public release 🎉

**⬇️ [Download fba-dav.exe](https://github.com/dav-voidd/tiktok-downloader/releases/latest)**

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
