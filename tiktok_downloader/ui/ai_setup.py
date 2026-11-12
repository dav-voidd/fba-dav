"""'Connect Gemini' setup: a 3-step guided window for getting a free Gemini API key.

The key is picked up from the clipboard automatically the moment the user copies it,
then verified with the provider before saving.
"""

from __future__ import annotations

import threading
import webbrowser
from dataclasses import dataclass
from tkinter import TclError
from typing import Callable

import customtkinter as ctk

from ..products import gemini
from . import theme
from .widgets import GhostButton, PrimaryButton, TextButton

_CLIPBOARD_POLL_MS = 700


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    name: str
    pitch: str
    url: str
    url_label: str
    step1_hint: str
    step2_hint: str
    key_prefix: str
    find_key: Callable[[str], str | None]
    check_key: Callable[[str], tuple[bool, str]]


PROVIDERS = {
    "gemini": ProviderSpec(
        key="gemini", name="Gemini",
        pitch="Gemini watches your videos (picture and sound) and names each product,\n"
              "10 videos at a time. You only do this once. It takes about a minute.",
        url=gemini.KEYS_URL, url_label="Open AI Studio  ↗",
        step1_hint="Sign in with your Google account (the same one you use for Gmail).",
        step2_hint="Click the blue  “Create API key”  button.\n"
                   "If it asks for a project, choose any (or “Create new project”).\n"
                   "Then click the copy icon next to your key. It starts with  AIza…",
        key_prefix="AIza…", find_key=gemini.find_key, check_key=gemini.check_key,
    ),
}

Scheduler = Callable[[Callable[[], None]], None]


class AISetup(ctk.CTkToplevel):
    def __init__(self, master, *, provider: str, current_key: str, schedule: Scheduler,
                 on_saved: Callable[[str], None]):
        super().__init__(master)
        self._spec = spec = PROVIDERS[provider]
        self.title(f"Connect {spec.name}")
        self.geometry("560x700")
        self.minsize(520, 640)
        self.configure(fg_color=theme.BACKGROUND)
        self._schedule = schedule
        self._on_saved = on_saved
        self._checking = False
        self._last_clipboard = ""

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=28, pady=24)

        # --- footer
        footer = ctk.CTkFrame(body, fg_color="transparent")
        footer.pack(fill="x", side="bottom", pady=(8, 0))  # packed first: never cut off
        TextButton(footer, "Cancel", self.destroy).pack(side="left")
        self._save = PrimaryButton(footer, "Check & save", self._check_and_save, width=160, height=38)
        self._save.pack(side="right")

        # --- intro
        ctk.CTkLabel(body, text=f"Connect {spec.name}", font=theme.font(20, "bold"),
                     text_color=theme.TEXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(body, text=spec.pitch,
                     font=theme.font(13), text_color=theme.TEXT_MUTED, justify="left",
                     anchor="w").pack(fill="x", pady=(4, 10))

        chips = ctk.CTkFrame(body, fg_color="transparent")
        chips.pack(fill="x", pady=(0, 16))
        for text in ("✓ Free", "✓ No credit card", "✓ Saved on this PC only"):
            ctk.CTkLabel(chips, text=text, font=theme.font(11, "bold"), height=24, corner_radius=12,
                         fg_color=theme.ACCENT_SOFT, text_color=theme.ACCENT_TEXT
                         ).pack(side="left", padx=(0, 6), ipadx=8)

        # --- step 1
        step1 = self._step(body, 1, f"Open the {spec.name} website", spec.step1_hint)
        PrimaryButton(step1, spec.url_label, lambda: webbrowser.open(spec.url),
                      height=36, width=200).pack(anchor="w", pady=(8, 0))

        # --- step 2
        step2 = self._step(body, 2, "Create and copy your key", spec.step2_hint)
        ctk.CTkLabel(step2, text="Tip: this window grabs the key automatically when you copy it.",
                     font=theme.font(11), text_color=theme.ACCENT_TEXT, anchor="w"
                     ).pack(fill="x", pady=(6, 0))

        # --- step 3
        step3 = self._step(body, 3, "Paste it here", None)
        row = ctk.CTkFrame(step3, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        self._entry = ctk.CTkEntry(row, height=38, placeholder_text=spec.key_prefix, show="•",
                                   fg_color=theme.SURFACE, border_color=theme.BORDER_STRONG,
                                   text_color=theme.TEXT, font=theme.mono(12),
                                   corner_radius=theme.RADIUS_CONTROL)
        self._entry.pack(side="left", fill="x", expand=True)
        self._entry.bind("<KeyRelease>", lambda _e: self._set_status("", theme.TEXT_MUTED))
        GhostButton(row, "Paste", self._paste, width=70, height=38).pack(side="left", padx=(8, 0))
        if current_key:
            self._entry.insert(0, current_key)

        self._status = ctk.CTkLabel(step3, text="", font=theme.font(12), anchor="w",
                                    text_color=theme.TEXT_MUTED)
        self._status.pack(fill="x", pady=(8, 0))

        self.after(150, self._focus_on_top)
        self.after(_CLIPBOARD_POLL_MS, self._watch_clipboard)

    # ----------------------------------------------------------------- layout

    def _step(self, master, number: int, title: str, hint: str | None) -> ctk.CTkFrame:
        card = ctk.CTkFrame(master, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                            border_width=1, border_color=theme.BORDER)
        card.pack(fill="x", pady=(0, 10))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)

        head = ctk.CTkFrame(inner, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=str(number), width=24, height=24, corner_radius=12,
                     fg_color=theme.ACCENT, text_color="#FFFFFF", font=theme.font(12, "bold")
                     ).pack(side="left")
        ctk.CTkLabel(head, text=title, font=theme.font(14, "bold"), text_color=theme.TEXT
                     ).pack(side="left", padx=10)
        if hint:
            ctk.CTkLabel(inner, text=hint, font=theme.font(12), text_color=theme.TEXT_MUTED,
                         justify="left", anchor="w").pack(fill="x", pady=(6, 0))
        return inner

    def _focus_on_top(self) -> None:
        self.lift()
        self.focus_force()
        try:
            self.grab_set()  # keep focus here until done
        except TclError:
            pass

    # ---------------------------------------------------------------- actions

    def _watch_clipboard(self) -> None:
        """Auto-fill the moment a key appears on the clipboard."""
        if not self.winfo_exists():
            return
        try:
            clip = self.clipboard_get()
        except TclError:
            clip = ""
        if clip != self._last_clipboard:
            self._last_clipboard = clip
            key = self._spec.find_key(clip)
            if key and key != self._entry.get().strip() and not self._checking:
                self._fill(key)
                self._set_status("Key detected from your clipboard ✓  Checking it…", theme.ACCENT_TEXT)
                self._check_and_save()
        self.after(_CLIPBOARD_POLL_MS, self._watch_clipboard)

    def _paste(self) -> None:
        try:
            clip = self.clipboard_get()
        except TclError:
            clip = ""
        key = self._spec.find_key(clip)
        if key:
            self._fill(key)
            self._set_status("", theme.TEXT_MUTED)
        else:
            self._set_status("Your clipboard doesn't have a key yet. Copy it from the website first.",
                             theme.DANGER)

    def _fill(self, key: str) -> None:
        self._entry.delete(0, "end")
        self._entry.insert(0, key)

    def _check_and_save(self) -> None:
        key = self._spec.find_key(self._entry.get()) or self._entry.get().strip()
        if not key:
            self._set_status("Paste your key first (step 3).", theme.DANGER)
            return
        if self._checking:
            return
        self._checking = True
        self._save.configure(state="disabled", text="Checking…")
        self._set_status(f"Checking your key with {self._spec.name}…", theme.TEXT_MUTED)

        def work() -> None:
            ok, message = self._spec.check_key(key)
            self._schedule(lambda: self._finish_check(ok, message, key))

        threading.Thread(target=work, daemon=True).start()

    def _finish_check(self, ok: bool, message: str, key: str) -> None:
        if not self.winfo_exists():
            return
        self._checking = False
        self._save.configure(state="normal", text="Check & save")
        if ok:
            self._on_saved(key)
            self._set_status(f"✓ {message}", theme.ACCENT_TEXT)
            self.after(900, self.destroy)
        else:
            self._set_status(f"✕ {message}", theme.DANGER)

    def _set_status(self, text: str, color: str) -> None:
        self._status.configure(text=text, text_color=color)
