"""Design tokens: the single place to restyle the app.

Palette rule: white base (with soft blush steps for cards and hovers) and one accent,
cherry red, for the primary action, active tab and progress. Green = done, amber = check it,
brick red = errors.
"""

import sys

import customtkinter as ctk

# Base - white
BACKGROUND = "#FBF7F8"      # window, inputs
SURFACE = "#FFFFFF"         # cards
SURFACE_RAISED = "#FFF1F3"  # rows, pills
SURFACE_HOVER = "#FFE3E8"
BORDER = "#F2D9DE"
BORDER_STRONG = "#E6BCC4"

TEXT = "#22161A"
TEXT_MUTED = "#6E5A61"
TEXT_FAINT = "#A48E95"

# The one accent - cherry red
ACCENT = "#C8102E"
ACCENT_HOVER = "#DE2341"
ACCENT_SOFT = "#FFE1E7"
ACCENT_TEXT = "#B00E29"

# Status colors
SUCCESS = "#16803C"         # done / posted
SUCCESS_SOFT = "#DCFCE7"
WARNING = "#B45309"         # done, but check something
INFO = "#FFFFFF"
INFO_SOFT = ACCENT
DANGER = "#B42318"          # errors only
DANGER_SOFT = "#FEE4E2"

# Shape & spacing
RADIUS_CARD = 14
RADIUS_CONTROL = 8
PAD = 18
GAP = 12

if sys.platform == "darwin":
    FONT_FAMILY, MONO_FAMILY = "Helvetica Neue", "Menlo"          # built into every Mac
elif sys.platform == "win32":
    FONT_FAMILY, MONO_FAMILY = "Segoe UI", "Cascadia Mono"
else:
    FONT_FAMILY, MONO_FAMILY = "DejaVu Sans", "DejaVu Sans Mono"


def asset(name: str) -> str:
    """Path to a bundled file in tiktok_downloader/assets (works in the .exe too)."""
    from pathlib import Path
    base = Path(getattr(sys, "_MEIPASS", "")) / "tiktok_downloader" if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent.parent
    return str(base / "assets" / name)


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(FONT_FAMILY, size, weight)


def mono(size: int = 12) -> ctk.CTkFont:
    return ctk.CTkFont(MONO_FAMILY, size)
