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


def main() -> None:
    ensure_dependencies()
    from tiktok_downloader.errors import LOG_PATH, install_crash_handlers, log_exception

    install_crash_handlers()
    try:
        from tiktok_downloader.ui.app import run
        run()
    except Exception as exc:  # last line of defence: explain instead of vanishing
        log_exception(exc, "fatal")
        try:
            from tkinter import Tk, messagebox
            root = Tk()
            root.withdraw()
            messagebox.showerror("TikTok Downloader",
                                 f"Something went wrong and the app has to close.\n\n"
                                 f"Details were saved to:\n{LOG_PATH}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
