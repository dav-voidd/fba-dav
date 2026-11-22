"""📋 Post IDs tab: every post on your Page from one day, in posting order, ready to copy."""

from __future__ import annotations

import datetime as dt
import re
import threading
import webbrowser
from typing import Callable

import customtkinter as ctk

from pathlib import Path
from tkinter import filedialog

from ..products import excel, facebook
from ..products.subid import shop_from_subid
from . import theme
from .widgets import Eyebrow, GhostButton, PrimaryButton, Switch, TextButton


class PostIdsPage(ctk.CTkFrame):
    def __init__(self, master, *, settings, schedule: Callable[[Callable[[], None]], None], reels: bool = False):
        super().__init__(master, fg_color="transparent")
        self._reels = reels                     # True: the Reel Links tab (copies reel links, has filters)
        self._settings = settings
        self._schedule = schedule
        self._posts: list[dict] = []
        self._rows: list[ctk.CTkFrame] = []
        self._only_links = ctk.BooleanVar(value=True)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(head, text="Reel links by date" if reels else "Post IDs by date", font=theme.font(18, "bold"),
                     text_color=theme.TEXT).pack(side="left")
        self._copy = PrimaryButton(head, "Copy all reel links" if reels else "Copy all post IDs", self._copy_all,
                                   width=180, height=36)
        self._copy.pack(side="right")
        self._copy.configure(state="disabled")

        # --- controls
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        Eyebrow(bar, "Date").pack(side="left", padx=(0, 8))
        self._date = ctk.CTkEntry(bar, width=120, height=32, fg_color=theme.SURFACE, border_color=theme.BORDER_STRONG,
                                  text_color=theme.TEXT, font=theme.mono(12), placeholder_text="2026-11-16")
        self._date.pack(side="left")
        self._date.insert(0, dt.date.today().isoformat())
        TextButton(bar, "Today", lambda: self._set_day(0)).pack(side="left", padx=(8, 0))
        TextButton(bar, "Yesterday", lambda: self._set_day(-1)).pack(side="left")
        Eyebrow(bar, "Page ID").pack(side="left", padx=(16, 8))
        self._page = ctk.CTkEntry(bar, width=170, height=32, fg_color=theme.SURFACE, border_color=theme.BORDER_STRONG,
                                  text_color=theme.TEXT, font=theme.mono(12), placeholder_text="584817111379300")
        self._page.pack(side="left")
        Switch(bar, "Only posts with a link", self._only_links).pack(side="left", padx=16)
        self._only_links.trace_add("write", lambda *_: self._show() if self._posts else None)
        self._get = PrimaryButton(bar, "Get post IDs", self.fetch, width=140, height=32)
        self._get.pack(side="right")

        # --- optional: match with the links Excel (post order = Excel row order)
        match = ctk.CTkFrame(self, fg_color="transparent")
        match.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        Eyebrow(match, "Match with Excel").pack(side="left", padx=(0, 8))
        self._excel = ctk.StringVar(value="")
        ctk.CTkEntry(match, textvariable=self._excel, height=30, width=420, fg_color=theme.SURFACE,
                     border_color=theme.BORDER, text_color=theme.TEXT_MUTED, font=theme.font(12),
                     placeholder_text="optional: your boss's converted links file").pack(side="left")
        GhostButton(match, "Choose", self._pick_excel, width=80, height=30).pack(side="left", padx=8)
        TextButton(match, "Clear", lambda: (self._excel.set(""), self._show() if self._posts else None)).pack(side="left")
        self._rows_excel: list[tuple[str, str]] = []

        # --- Reel Links filters
        self._search = ctk.StringVar(value="")
        self._shops_only = ctk.BooleanVar(value=False)
        if reels:
            filters = ctk.CTkFrame(self, fg_color="transparent")
            filters.grid(row=5, column=0, sticky="ew", pady=(10, 0))
            Eyebrow(filters, "Search").pack(side="left", padx=(0, 8))
            ctk.CTkEntry(filters, textvariable=self._search, width=220, height=30, fg_color=theme.SURFACE,
                         border_color=theme.BORDER_STRONG, text_color=theme.TEXT, font=theme.font(12),
                         placeholder_text="product, shop or sub ID").pack(side="left")
            Switch(filters, "Only sub IDs with a shop name (needs the Excel)", self._shops_only).pack(side="left", padx=16)
            for var in (self._search, self._shops_only):
                var.trace_add("write", lambda *_: self._show() if self._posts else None)

        # --- list
        self._list = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                                            border_width=1, border_color=theme.BORDER,
                                            scrollbar_button_color=theme.BORDER)
        self._list.grid(row=2, column=0, sticky="nsew")
        self._list.grid_columnconfigure(1, weight=1)
        self._status = ctk.CTkLabel(self, text="Pick a date and press Get post IDs. They come oldest first, "
                                    "the same order you posted them.", font=theme.font(12),
                                    text_color=theme.TEXT_MUTED, anchor="w")
        self._status.grid(row=6, column=0, sticky="ew", pady=(8, 12))

    # ---------------------------------------------------------------- actions

    def _say(self, text: str, color: str = theme.TEXT_MUTED) -> None:
        self._status.configure(text=text, text_color=color)

    def _pick_excel(self) -> None:
        path = filedialog.askopenfilename(parent=self, filetypes=[("Excel file", "*.xlsx")])
        if path:
            self._excel.set(path)
            if self._posts:
                self._show()

    @staticmethod
    def _link_key(url: str) -> str:
        return url.strip().rstrip("/").split("?")[0].lower().replace("http://", "https://")

    def _set_day(self, offset: int) -> None:
        self._date.delete(0, "end")
        self._date.insert(0, (dt.date.today() + dt.timedelta(days=offset)).isoformat())

    def fetch(self) -> None:
        try:
            day = dt.date.fromisoformat(self._date.get().strip())
        except ValueError:
            self._say("Type the date like 2026-11-16.", theme.DANGER)
            return
        if not self._page.get().strip() and self._settings.fb_page_id:
            self._page.insert(0, self._settings.fb_page_id)
        page = "".join(ch for ch in self._page.get() if ch.isdigit())
        token = self._settings.fb_token
        if not token or not page:
            self._say("Connect your Page in the Facebook tab first.", theme.DANGER)
            return
        self._get.configure(state="disabled", text="Getting…")
        self._say(f"Asking Facebook for every post on {day:%b %d, %Y}…")

        def work() -> None:
            try:
                posts = facebook.FacebookClient(token, page).posts_on_day(page, day)
                error = ""
            except facebook.FacebookError as exc:
                posts, error = [], str(exc)

            def done() -> None:
                self._get.configure(state="normal", text="Get post IDs")
                if error:
                    self._say(f"Couldn't get the posts: {error}", theme.DANGER)
                    return
                self._posts = posts
                self._show()
            self._schedule(done)

        threading.Thread(target=work, daemon=True).start()

    def _visible(self) -> list[dict]:
        if not self._only_links.get():
            return self._posts
        return [p for p in self._posts if "http" in p["message"].lower()]

    def _matched(self) -> tuple[list[dict], int]:
        """Posts in Excel row order (by the Shopee link in each caption). Missing rows -> placeholder."""
        try:
            rows = excel.read_rows(Path(self._excel.get()))
        except Exception as exc:
            self._say(f"Couldn't read the Excel file: {exc}", theme.DANGER)
            return self._visible(), 0
        by_link: dict[str, dict] = {}
        for post in self._posts:
            for url in re.findall(r"https?://\S+", post["message"]):
                by_link.setdefault(self._link_key(url), post)       # first (oldest) post with that link
        ordered, missing = [], 0
        for link, sub_id in rows:
            post = by_link.get(self._link_key(link)) if link else None
            if post:
                ordered.append({**post, "sub_id": sub_id})
            else:
                missing += 1
                ordered.append({"id": "", "time": "", "link": "", "sub_id": sub_id,
                                "message": f"NOT FOUND · {link or '(no link)'}\n{sub_id}"})
        return ordered, missing

    def _show(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows = []
        missing = 0
        if self._excel.get().strip():
            posts, missing = self._matched()
        else:
            posts = self._visible()
        if self._reels:
            if self._shops_only.get():
                if not self._excel.get().strip():
                    self._say("Pick the Excel file first: shop names are in the sub IDs.", theme.DANGER)
                posts = [p for p in posts if shop_from_subid(p.get("sub_id", ""))]
            query = self._search.get().strip().lower()
            if query:
                posts = [p for p in posts if query in (p["message"] + " " + p.get("sub_id", "")).lower()]
            missing = sum(1 for p in posts if not p["id"])
        for i, post in enumerate(posts, 1):
            row = ctk.CTkFrame(self._list, fg_color=theme.SURFACE_RAISED, corner_radius=10)
            row.grid(row=i, column=0, columnspan=3, sticky="ew", padx=6, pady=3)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=f"{i:02d}", width=28, font=theme.mono(12),
                         text_color=theme.TEXT_FAINT).grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=8)
            found = bool(post["id"])
            main = (post.get("link") or post["id"]) if self._reels else post["id"]
            ctk.CTkLabel(row, text=main or "✕ not posted on this date", anchor="w", font=theme.mono(13),
                         text_color=theme.ACCENT_TEXT if found else theme.DANGER).grid(
                row=0, column=1, sticky="ew", pady=(8, 0))
            name = " · ".join(line for line in post["message"].splitlines()[1:2]) or post["message"][:60]
            extra = f"  ·  {post['sub_id']}" if post.get("sub_id") else ""
            ctk.CTkLabel(row, text=(f"{post['time']}  ·  {name}{extra}" if found else post["message"].replace("\n", "  ·  ")),
                         anchor="w", font=theme.font(11),
                         text_color=theme.TEXT_FAINT).grid(row=1, column=1, sticky="ew", pady=(0, 8))
            page_id, post_id = facebook.split_id(post["id"])
            url = (post.get("link") or facebook.post_url(page_id, post_id)) if found else ""
            check = GhostButton(row, "Check ↗", lambda u=url: webbrowser.open(u), width=86, height=30)
            check.grid(row=0, column=2, rowspan=2, padx=(0, 8))
            if not found:
                check.configure(state="disabled")
            shop = re.search(r"https?://\S+", post["message"])
            link_btn = GhostButton(row, "Link ↗", lambda u=shop.group(0) if shop else "": webbrowser.open(u),
                                   width=76, height=30)
            link_btn.grid(row=0, column=3, rowspan=2, padx=(0, 8))
            if not shop:
                link_btn.configure(state="disabled")
            copy_value = main if self._reels else post["id"]
            GhostButton(row, "Copy", lambda t=copy_value: self._copy_text(t, f"Copied {t}"), width=64, height=30).grid(
                row=0, column=4, rowspan=2, padx=(0, 12))
            self._rows.append(row)
        self._shown = posts
        self._copy.configure(state="normal" if posts else "disabled")
        hidden = len(self._posts) - len(posts)
        if self._excel.get().strip() and posts:
            self._say(f"Matched with Excel: {len(posts) - missing} of {len(posts)} rows found, in Excel order."
                      + (f" ⚠ {missing} not found on this date (blank lines when copied)." if missing else " ✓"),
                      theme.WARNING if missing else theme.ACCENT_TEXT)
        elif not self._posts:
            self._say("No posts on that date.", theme.WARNING)
        else:
            self._say(f"{len(posts)} posts, oldest first." + (f" {hidden} other post(s) hidden (no link)." if hidden else ""),
                      theme.ACCENT_TEXT)

    def _copy_text(self, text: str, note: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self._say(note, theme.ACCENT_TEXT)

    def _copy_all(self) -> None:
        shown = getattr(self, "_shown", self._visible())
        order = "in Excel order" if self._excel.get().strip() else "oldest first"
        if self._reels:
            links = [p.get("link", "") if p["id"] else "" for p in shown]
            self._copy_text("\n".join(links), f"Copied {sum(1 for l in links if l)} reel links, {order}.")
            return
        ids = [p["id"] for p in shown]
        self._copy_text("\n".join(ids), f"Copied {sum(1 for i in ids if i)} post IDs (pageid_postid), {order}.")
