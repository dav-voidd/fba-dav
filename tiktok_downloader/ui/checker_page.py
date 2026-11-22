"""✅ Checker tab: post IDs -> full IDs (pageid_postid) + clickable links, and check they exist."""

from __future__ import annotations

import threading
import webbrowser
from typing import Callable

import customtkinter as ctk

from ..products import facebook
from . import theme
from .widgets import Card, Eyebrow, GhostButton, PrimaryButton, TextButton


class CheckerPage(ctk.CTkFrame):
    def __init__(self, master, *, settings, get_posted: Callable[[], list[str]],
                 schedule: Callable[[Callable[[], None]], None]):
        super().__init__(master, fg_color="transparent")
        self._settings = settings
        self._get_posted = get_posted
        self._schedule = schedule
        self._rows: list[CheckRow] = []
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(head, text="Post ID checker", font=theme.font(18, "bold"), text_color=theme.TEXT).pack(side="left")
        self._check = PrimaryButton(head, "Check on Facebook", self.check_all, width=180, height=36)
        self._check.pack(side="right")
        GhostButton(head, "Copy full IDs", self._copy_full, width=120).pack(side="right", padx=(0, 8))
        self._page = ctk.CTkEntry(head, width=170, height=32, fg_color=theme.SURFACE, border_color=theme.BORDER_STRONG,
                                  text_color=theme.TEXT, font=theme.mono(12), placeholder_text="584817111379300")
        self._page.pack(side="right", padx=(0, 12))
        if settings.fb_page_id:
            self._page.insert(0, settings.fb_page_id)
        Eyebrow(head, "Page ID").pack(side="right", padx=(0, 8))

        # --- input
        card = Card(self)
        card.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        card.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=theme.PAD, pady=(14, 6))
        ctk.CTkLabel(top, text="Post IDs", font=theme.font(14, "bold"), text_color=theme.TEXT).pack(side="left")
        TextButton(top, "Use posted", self._use_posted).pack(side="right")
        TextButton(top, "Paste", self._paste).pack(side="right")
        self._box = ctk.CTkTextbox(card, width=260, fg_color=theme.BACKGROUND, border_color=theme.BORDER,
                                   border_width=1, corner_radius=10, font=theme.mono(12), text_color=theme.TEXT)
        self._box.grid(row=1, column=0, sticky="nsew", padx=theme.PAD)
        PrimaryButton(card, "Make links  →", self.build, height=32).grid(
            row=2, column=0, sticky="ew", padx=theme.PAD, pady=12)

        # --- results
        self._list = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                                            border_width=1, border_color=theme.BORDER,
                                            scrollbar_button_color=theme.BORDER)
        self._list.grid(row=1, column=1, sticky="nsew")
        self._list.grid_columnconfigure(0, weight=1)
        self._status = ctk.CTkLabel(self, text="One post ID per line (122219645510763039), or full IDs (pageid_postid).",
                                    font=theme.font(12), text_color=theme.TEXT_MUTED, anchor="w")
        self._status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 12))

    # ---------------------------------------------------------------- actions

    def _say(self, text: str, color: str = theme.TEXT_MUTED) -> None:
        self._status.configure(text=text, text_color=color)

    def _paste(self) -> None:
        try:
            text = self.clipboard_get()
        except Exception:
            return
        self._box.delete("1.0", "end")
        self._box.insert("1.0", text.strip() + "\n")
        self.build()

    def _use_posted(self) -> None:
        ids = self._get_posted()
        if not ids:
            self._say("Nothing posted yet in the Facebook tab.", theme.DANGER)
            return
        self._box.delete("1.0", "end")
        self._box.insert("1.0", "\n".join(ids) + "\n")
        self.build()

    def build(self) -> None:
        if self._settings.fb_page_id and not self._page.get().strip():
            self._page.insert(0, self._settings.fb_page_id)   # same Page as the Facebook tab
        page = "".join(ch for ch in self._page.get() if ch.isdigit())
        lines = [line.strip() for line in self._box.get("1.0", "end").splitlines() if line.strip()]
        for row in self._rows:
            row.destroy()
        self._rows = []
        bad = 0
        for i, line in enumerate(lines, 1):
            page_id, post_id = facebook.split_id(line, page)
            if not page_id or not post_id:
                bad += 1
                continue
            row = CheckRow(self._list, i, page_id, post_id, self)
            row.grid(row=i, column=0, sticky="ew", padx=6, pady=3)
            self._rows.append(row)
        if page and page != self._settings.fb_page_id:
            self._settings.fb_page_id = page
            self._settings.save()
        if bad and not page:
            self._say("Type your Page ID first (the number before the _).", theme.DANGER)
        else:
            self._say(f"{len(self._rows)} links ready. Click a link to open it, or Check on Facebook."
                      + (f" {bad} line(s) skipped." if bad else ""))

    def check_all(self) -> None:
        if not self._rows:
            self.build()
        token = self._settings.fb_token
        if not token:
            self._say("Connect your Page in the Facebook tab first (the check uses your token).", theme.DANGER)
            return
        self._check.configure(state="disabled", text="Checking…")
        rows = list(self._rows)

        def work() -> None:
            client, ok = facebook.FacebookClient(token), 0
            for row in rows:
                try:
                    link = client.check_post(row.page_id, row.post_id)
                    ok += 1
                    self._schedule(lambda r=row, l=link: r.mark(True, "✓ Found", l))
                    continue
                except facebook.FacebookError as exc:
                    message = str(exc)
                # Maybe it's a Reel's video ID (what older versions showed): look up its real post ID.
                try:
                    real = facebook.split_id(client.find_post_id(row.post_id, attempts=3))[1]
                except facebook.FacebookError:
                    real = ""
                if real:
                    ok += 1
                    self._schedule(lambda r=row, p=real: r.replace_post(p))
                else:
                    self._schedule(lambda r=row, m=message: r.mark(False, f"✕ {m}"))

            def done(ok=ok) -> None:
                self._check.configure(state="normal", text="Check on Facebook")
                missing = len(rows) - ok
                self._say(f"{ok} of {len(rows)} posts found on Facebook."
                          + (f" {missing} not found: check those IDs." if missing else " All good ✓"),
                          theme.DANGER if missing else theme.ACCENT_TEXT)
            self._schedule(done)

        threading.Thread(target=work, daemon=True).start()

    def _copy_full(self) -> None:
        if not self._rows:
            self.build()
        full = [row.full_id for row in self._rows]
        self.copy("\n".join(full), f"Copied {len(full)} full IDs (pageid_postid), one per line.")

    def copy(self, text: str, note: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self._say(note, theme.ACCENT_TEXT)


class CheckRow(ctk.CTkFrame):
    def __init__(self, master, number: int, page_id: str, post_id: str, page: CheckerPage):
        super().__init__(master, fg_color=theme.SURFACE_RAISED, corner_radius=10)
        self.page_id, self.post_id = page_id, post_id
        self.full_id = f"{page_id}_{post_id}"
        self._url = facebook.post_url(page_id, post_id)
        self._page = page
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=f"{number:02d}", width=28, font=theme.mono(12),
                     text_color=theme.TEXT_FAINT).grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=8)
        self._id_label = ctk.CTkLabel(self, text=self.full_id, anchor="w", font=theme.mono(13),
                                      text_color=theme.ACCENT_TEXT)
        self._id_label.grid(row=0, column=1, sticky="ew", pady=(8, 0))
        self._link = ctk.CTkLabel(self, text=self._url, anchor="w", font=theme.font(11, "normal"),
                                  text_color="#6EA8FE", cursor="hand2")
        self._link.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        self._link.bind("<Button-1>", lambda _e: webbrowser.open(self._url))
        self._state = ctk.CTkLabel(self, text="", width=170, anchor="e", font=theme.font(11),
                                   text_color=theme.TEXT_FAINT, wraplength=170)
        self._state.grid(row=0, column=2, rowspan=2, padx=8)
        GhostButton(self, "Copy", lambda: page.copy(self.full_id, f"Copied {self.full_id}"),
                    width=64, height=28).grid(row=0, column=3, rowspan=2, padx=(0, 12))

    def replace_post(self, post_id: str) -> None:
        """It was a video ID: show the real post ID instead."""
        self.post_id = post_id
        self.full_id = f"{self.page_id}_{post_id}"
        self._url = facebook.post_url(self.page_id, post_id)
        self._id_label.configure(text=self.full_id)
        self._link.configure(text=self._url)
        self.mark(True, "✓ Fixed (was a video ID)")

    def mark(self, ok: bool, text: str, link: str = "") -> None:
        if link:
            self._url = link
            self._link.configure(text=link)
        self._state.configure(text=text, text_color=theme.ACCENT_TEXT if ok else theme.DANGER)
