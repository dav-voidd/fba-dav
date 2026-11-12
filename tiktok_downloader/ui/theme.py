"""Design tokens: the single place to restyle the app.

Palette rule: two base colors (deep navy + slate navy) and one accent (violet).
Base shades are only lighter/darker steps of the same navy; the accent is reserved
for the primary action, active state and progress. Red appears only for errors.
"""

import customtkinter as ctk

# Base 1 - deep navy (window background, inputs)
BACKGROUND = "#0B0E1A"

# Base 2 - slate navy (cards) and its lighter steps
SURFACE = "#131829"
SURFACE_RAISED = "#1A2036"
SURFACE_HOVER = "#212842"
BORDER = "#222A44"
BORDER_STRONG = "#2E3757"

TEXT = "#E9ECF7"
TEXT_MUTED = "#8C95B4"
TEXT_FAINT = "#566081"

# The one accent - violet
ACCENT = "#7C6CFF"
ACCENT_HOVER = "#8F81FF"
ACCENT_SOFT = "#221E4D"
ACCENT_TEXT = "#B4ABFF"

# Status colors are derived from the palette, not new hues
SUCCESS = ACCENT_TEXT
SUCCESS_SOFT = ACCENT_SOFT
INFO = "#FFFFFF"
INFO_SOFT = ACCENT
DANGER = "#FF6B81"     # errors only
DANGER_SOFT = "#2C1424"

# Shape & spacing
RADIUS_CARD = 14
RADIUS_CONTROL = 8
PAD = 18
GAP = 12

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Cascadia Mono"


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(FONT_FAMILY, size, weight)


def mono(size: int = 12) -> ctk.CTkFont:
    return ctk.CTkFont(MONO_FAMILY, size)
