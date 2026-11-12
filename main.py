"""Entry point. Run with F5 in VS Code, or: python main.py"""

import importlib.util
import subprocess
import sys

REQUIRED = {
    "customtkinter": "customtkinter",
    "PIL": "pillow",
    "yt_dlp": "yt-dlp",
    "curl_cffi": "curl_cffi",  # lets yt-dlp look like a real browser to TikTok
}  # import name -> pip name


def ensure_dependencies() -> None:
    """Install missing packages on first run so the app 'just works'."""
    if getattr(sys, "frozen", False):
        return  # packaged .exe already bundles everything
    missing = [pip for module, pip in REQUIRED.items() if importlib.util.find_spec(module) is None]
    if missing:
        print(f"Installing {', '.join(missing)} (first run only)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", *missing])


if __name__ == "__main__":
    ensure_dependencies()
    from tiktok_downloader.ui.app import run

    run()
