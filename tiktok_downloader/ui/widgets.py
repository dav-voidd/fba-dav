"""Small reusable widgets styled with the design tokens."""

from __future__ import annotations

from tkinter import TclError
from typing import Callable

import customtkinter as ctk

from ..links import shorten
from ..models import QueueItem, Status
from . import theme


class Card(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", theme.SURFACE)
        super().__init__(master, corner_radius=theme.RADIUS_CARD, border_width=1,
                         border_color=theme.BORDER, **kwargs)


class PrimaryButton(ctk.CTkButton):
    def __init__(self, master, text, command, **kwargs):
        kwargs.setdefault("height", 40)
        super().__init__(master, text=text, command=command, corner_radius=theme.RADIUS_CONTROL,
                         fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                         text_color="#FFFFFF", text_color_disabled="#FFD9E1",
                         font=theme.font(14, "bold"), **kwargs)


class GhostButton(ctk.CTkButton):
    """Quiet, bordered button for secondary actions."""

    def __init__(self, master, text, command, **kwargs):
        kwargs.setdefault("height", 32)
        super().__init__(master, text=text, command=command, corner_radius=theme.RADIUS_CONTROL,
                         fg_color=theme.SURFACE_RAISED, hover_color=theme.SURFACE_HOVER,
                         border_width=1, border_color=theme.BORDER, text_color=theme.TEXT,
                         font=theme.font(12, "bold"), **kwargs)


class TextButton(ctk.CTkButton):
    def __init__(self, master, text, command, **kwargs):
        super().__init__(master, text=text, command=command, width=10, height=26,
                         corner_radius=6, fg_color="transparent", hover_color=theme.SURFACE_HOVER,
                         text_color=theme.TEXT_MUTED, font=theme.font(12), **kwargs)


class Eyebrow(ctk.CTkLabel):
    """Small uppercase label above a section."""

    def __init__(self, master, text, color=theme.TEXT_FAINT, **kwargs):
        super().__init__(master, text=text.upper(), font=theme.font(11, "bold"),
                         text_color=color, anchor="w", **kwargs)


class Divider(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, height=1, fg_color=theme.BORDER, **kwargs)


class Segmented(ctk.CTkSegmentedButton):
    def __init__(self, master, values, variable, command=None):
        super().__init__(
            master, values=values, variable=variable, command=command, height=32,
            corner_radius=theme.RADIUS_CONTROL, border_width=2,
            fg_color=theme.SURFACE_RAISED, unselected_color=theme.SURFACE_RAISED,
            unselected_hover_color=theme.SURFACE_HOVER,
            selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HOVER,
            text_color=theme.TEXT, font=theme.font(12, "bold"),
        )


class TabStrip(ctk.CTkFrame):
    """Browser-style tabs: the open tab is a raised card with an accent bar under it."""

    def __init__(self, master, names: list[str], on_change):
        super().__init__(master, fg_color="transparent")
        self._on_change = on_change
        self._tabs: dict[str, tuple[ctk.CTkButton, ctk.CTkFrame]] = {}
        for name in names:
            holder = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)   # size = the button
            holder.pack(side="left", padx=(0, 4))
            button = ctk.CTkButton(holder, text=name, width=120, height=36, corner_radius=12, anchor="w",
                                   border_width=1, font=theme.font(13, "bold"),
                                   command=lambda n=name: self._click(n))
            button.pack()
            bar = ctk.CTkFrame(holder, width=1, height=3, corner_radius=2, fg_color="transparent")
            bar.pack(fill="x", padx=16, pady=(4, 0))
            self._tabs[name] = (button, bar)
        self.select(names[0])

    def _click(self, name: str) -> None:
        self.select(name)
        self._on_change(name)

    def select(self, name: str) -> None:
        for tab, (button, bar) in self._tabs.items():
            active = tab == name
            button.configure(
                fg_color=theme.SURFACE if active else theme.BACKGROUND,
                hover_color=theme.SURFACE if active else theme.SURFACE_HOVER,
                border_color=theme.BORDER_STRONG if active else theme.BACKGROUND,
                text_color=theme.TEXT if active else theme.TEXT_MUTED)
            bar.configure(fg_color=theme.ACCENT if active else "transparent")


class Switch(ctk.CTkSwitch):
    def __init__(self, master, text, variable):
        super().__init__(master, text=text, variable=variable, onvalue=True, offvalue=False,
                         switch_width=34, switch_height=18, progress_color=theme.ACCENT,
                         button_color="#FFFFFF", button_hover_color="#FFFFFF",
                         fg_color=theme.BORDER_STRONG, text_color=theme.TEXT_MUTED,
                         font=theme.font(12))


# ------------------------------------------------------------------ queue row

# status -> (label color, pill background, progress color)
_STATUS_STYLE = {
    Status.WAITING: (theme.TEXT_FAINT, theme.SURFACE_RAISED, theme.BORDER_STRONG),
    Status.DOWNLOADING: (theme.INFO, theme.INFO_SOFT, theme.ACCENT),
    Status.DONE: (theme.SUCCESS, theme.SUCCESS_SOFT, theme.SUCCESS),
    Status.FAILED: (theme.DANGER, theme.DANGER_SOFT, theme.DANGER),
}


class QueueRow(ctk.CTkFrame):
    """Compact row: index, title + subtitle, status pill, hairline progress."""

    def __init__(self, master, item: QueueItem, on_select: Callable[[QueueItem], None] | None = None):
        super().__init__(master, fg_color="transparent", corner_radius=10)
        self.grid_columnconfigure(1, weight=1)
        self._selected = False

        self._index = ctk.CTkLabel(self, text=f"{item.index:02d}", width=28, anchor="w",
                                   font=theme.mono(12), text_color=theme.TEXT_FAINT)
        self._index.grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=(8, 2))

        self._title = ctk.CTkLabel(self, anchor="w", font=theme.font(13), text_color=theme.TEXT)
        self._title.grid(row=0, column=1, sticky="ew", pady=(7, 0))
        self._subtitle = ctk.CTkLabel(self, anchor="w", font=theme.font(11), text_color=theme.TEXT_FAINT)
        self._subtitle.grid(row=1, column=1, sticky="ew")

        self._pill = ctk.CTkLabel(self, width=84, height=24, corner_radius=12, font=theme.font(11, "bold"))
        self._pill.grid(row=0, column=2, rowspan=2, padx=12)

        self._bar = ctk.CTkProgressBar(self, height=2, corner_radius=1, fg_color=theme.BORDER)
        self._bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(5, 0))

        self.render(item)
        if on_select:
            for widget in (self, *self.winfo_children()):
                widget.bind("<Button-1>", lambda _e: on_select(item))
                widget.bind("<Enter>", lambda _e: self._hover(True))
                widget.bind("<Leave>", lambda _e: self._hover(False))
                try:
                    widget.configure(cursor="hand2")
                except (ValueError, TclError):
                    pass  # not every CTk widget accepts a cursor

    def render(self, item: QueueItem) -> None:
        label_color, pill_bg, bar_color = _STATUS_STYLE[item.status]
        self._pill.configure(text=_status_text(item), text_color=label_color, fg_color=pill_bg)
        self._bar.configure(progress_color=bar_color)
        self._bar.set(item.progress if item.status is not Status.WAITING else 0)

        post = item.post
        self._title.configure(text=shorten(post.caption or f"@{post.author}", 70) if post
                              else shorten(item.url, 70))
        if item.status is Status.FAILED and item.error:
            subtitle = item.error
        elif item.product:
            subtitle = f"🛍 {item.product.display_sub_id or item.product.name}"
        elif post:
            subtitle = f"@{post.author}" + (f"  ·  {post.duration // 60}:{post.duration % 60:02d}"
                                            if post.duration else "")
        else:
            subtitle = "tiktok.com"
        self._subtitle.configure(text=shorten(subtitle, 90),
                                 text_color=theme.DANGER if item.status is Status.FAILED else theme.TEXT_FAINT)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.configure(fg_color=theme.SURFACE_RAISED if selected else "transparent")

    def _hover(self, inside: bool) -> None:
        if not self._selected:
            self.configure(fg_color=theme.SURFACE_HOVER if inside else "transparent")


def _status_text(item: QueueItem) -> str:
    if item.status is Status.DOWNLOADING:
        return f"{int(item.progress * 100)}%"
    if item.status is Status.DONE:
        return "✓ Saved"
    if item.status is Status.FAILED:
        return "Failed"
    return "Queued"
