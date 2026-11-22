#!/bin/bash
# Builds "TikTok Downloader.app" on a Mac (PyInstaller can't build Mac apps on Windows).
# Usage: open Terminal in this folder, then:  bash build_mac.sh
set -e
cd "$(dirname "$0")"
python3 -m pip install --quiet --upgrade pyinstaller customtkinter pillow yt-dlp curl_cffi
rm -rf build dist
python3 -m PyInstaller --noconfirm --windowed --name "TikTok Downloader" \
  --collect-data customtkinter --collect-submodules yt_dlp main.py
codesign --force --deep --sign - "dist/TikTok Downloader.app"   # ad-hoc signature so macOS will run it
cd dist && ditto -c -k --keepParent "TikTok Downloader.app" "TikTok Downloader (Mac).zip"
echo
echo "Done: dist/TikTok Downloader (Mac).zip  (share this file)"
echo "First launch on another Mac: right-click the app > Open > Open (it isn't from the App Store)."
