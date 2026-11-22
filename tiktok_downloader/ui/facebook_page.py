"""📘 Facebook tab: post the numbered videos as Reels, in order, and comment each link.

Video 1 pairs with Excel row 1 (link + sub ID), video 2 with row 2, and so on.
Caption and first comment: "Dito mabibili: <link>" + the product name (editable per video).
"""

from __future__ import annotations

import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from ..errors import log_line
from ..products import excel, facebook
from ..products.gemini import nice_names
from ..products.subid import caption_name, slug_from_subid, split_known, split_words
from . import theme
from .widgets import Card, Eyebrow, GhostButton, PrimaryButton, Switch, TextButton

EXPLORER_URL = "https://developers.facebook.com/tools/explorer/"
GUIDE = ("How to get your Page token: 1) developers.facebook.com → My Apps → Create app (type: Business). "
         "2) Tools → Graph API Explorer → pick your app → add permissions pages_show_list, pages_read_engagement, "
         "pages_manage_posts, pages_manage_engagement → Generate Access Token. "
         "3) In 'User or Page', choose your Page → copy the token → paste it here.")


@dataclass
class Job:
    video: Path
    link: str
    sub_id: str
    product: str
    post_id: str = ""
    state: str = "waiting"   # waiting | working | done | failed
    video_id: str = ""       # the Reel's video ID (to fetch a missing post ID later)


class FacebookPage(ctk.CTkFrame):
    def __init__(self, master, *, settings, get_products: Callable[[], dict[str, str]],
                 get_scan_names: Callable[[], dict[str, str]],
                 output_dir: Callable[[], str], schedule: Callable[[Callable[[], None]], None]):
        super().__init__(master, fg_color="transparent")
        self._settings = settings
        self._get_products = get_products
        self._get_scan_names = get_scan_names
        self._schedule = schedule
        self._jobs: list[Job] = []
        self._rows: list[JobRow] = []
        self._running = False
        self._stop = threading.Event()
        self._folder = ctk.StringVar(value=output_dir())
        self._excel = ctk.StringVar(value="")
        self._delay = ctk.StringVar(value=str(settings.fb_delay))
        self._comment = ctk.BooleanVar(value=True)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # --- header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(head, text="Facebook Reels", font=theme.font(18, "bold"), text_color=theme.TEXT).pack(side="left")
        self._start = PrimaryButton(head, "Start posting", self.start, width=160, height=36)
        self._start.pack(side="right")
        self._stop_btn = GhostButton(head, "Stop", self.stop, width=70)
        self._stop_btn.pack(side="right", padx=(0, 8))
        self._copy_ids = GhostButton(head, "Copy post IDs", self._copy_post_ids, width=120)
        self._copy_ids.pack(side="right", padx=(0, 8))
        GhostButton(head, "Fix post IDs", self.fix_post_ids, width=110).pack(side="right", padx=(0, 8))

        # --- page connection
        page = Card(self)
        page.grid(row=1, column=0, sticky="ew")
        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x", padx=theme.PAD, pady=14)
        Eyebrow(row, "Page token").pack(side="left", padx=(0, 8))
        self._token = ctk.CTkEntry(row, width=260, height=30, show="•", fg_color=theme.BACKGROUND,
                                   border_color=theme.BORDER_STRONG, text_color=theme.TEXT, font=theme.mono(12),
                                   placeholder_text="paste your Page access token")
        self._token.pack(side="left")
        for event in ("<KeyRelease>", "<FocusOut>", "<<Paste>>"):
            self._token.bind(event, lambda _e: self.after(50, self._save_token))
        PrimaryButton(row, "Connect", self.connect, width=100, height=30).pack(side="left", padx=8)
        Eyebrow(row, "Page ID").pack(side="left", padx=(8, 8))
        self._page_id = ctk.CTkEntry(row, width=160, height=30, fg_color=theme.BACKGROUND,
                                     border_color=theme.BORDER_STRONG, text_color=theme.TEXT, font=theme.mono(12),
                                     placeholder_text="filled in by Connect")
        self._page_id.pack(side="left")
        if settings.fb_page_id:
            self._page_id.insert(0, settings.fb_page_id)
        for event in ("<KeyRelease>", "<FocusOut>"):
            self._page_id.bind(event, lambda _e: self._save_page_id())
        TextButton(row, "How to get it", self._guide).pack(side="left")
        self._page_label = ctk.CTkLabel(row, text="", font=theme.font(12, "bold"), text_color=theme.TEXT_MUTED)
        self._page_label.pack(side="right")

        # --- inputs
        inputs = Card(self)
        inputs.grid(row=2, column=0, sticky="ew", pady=12)
        inputs.grid_columnconfigure(1, weight=1)
        self._path_row(inputs, 0, "Videos", self._folder, self._pick_folder)
        self._path_row(inputs, 1, "Links file", self._excel, self._pick_excel)
        Eyebrow(inputs, "Caption").grid(row=2, column=0, sticky="nw", padx=(theme.PAD, 8), pady=(6, 0))
        self._template = ctk.CTkTextbox(inputs, height=52, fg_color=theme.BACKGROUND, border_color=theme.BORDER,
                                        border_width=1, corner_radius=8, font=theme.mono(12), text_color=theme.TEXT)
        self._template.grid(row=2, column=1, sticky="ew", pady=(6, 0))
        self._template.insert("1.0", settings.fb_template or facebook.DEFAULT_TEMPLATE)
        options = ctk.CTkFrame(inputs, fg_color="transparent")
        options.grid(row=3, column=0, columnspan=3, sticky="ew", padx=theme.PAD, pady=(8, 14))
        PrimaryButton(options, "Load videos + links", self.load, width=170, height=30).pack(side="left")
        Switch(options, "Comment the caption on each post", self._comment).pack(side="left", padx=16)
        Eyebrow(options, "Wait between posts (s)").pack(side="left", padx=(8, 6))
        ctk.CTkEntry(options, textvariable=self._delay, width=52, height=28, fg_color=theme.BACKGROUND,
                     border_color=theme.BORDER_STRONG, text_color=theme.TEXT, font=theme.mono(12)).pack(side="left")
        ctk.CTkLabel(options, text="{link} and {product} get filled in", font=theme.font(11),
                     text_color=theme.TEXT_FAINT).pack(side="right")

        # --- list
        self._list = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                                            border_width=1, border_color=theme.BORDER,
                                            scrollbar_button_color=theme.BORDER)
        self._list.grid(row=3, column=0, sticky="nsew")
        self._list.grid_columnconfigure(0, weight=1)
        progress = ctk.CTkFrame(self, fg_color="transparent")
        progress.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        progress.grid_columnconfigure(1, weight=1)
        self._progress_label = ctk.CTkLabel(progress, text="Nothing loaded", width=230, anchor="w",
                                            font=theme.font(12, "bold"), text_color=theme.TEXT_MUTED)
        self._progress_label.grid(row=0, column=0, sticky="w")
        self._progress = ctk.CTkProgressBar(progress, height=10, corner_radius=5, fg_color=theme.SURFACE_RAISED,
                                            progress_color=theme.ACCENT)
        self._progress.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self._progress.set(0)
        self._status = ctk.CTkLabel(self, text="", font=theme.font(12), text_color=theme.TEXT_MUTED, anchor="w")
        self._status.grid(row=5, column=0, sticky="ew", pady=(6, 12))

        if settings.fb_token:
            self._token.insert(0, settings.fb_token)
            self._page_label.configure(text=f"Connected: {settings.fb_page_name} ✓" if settings.fb_page_name else "",
                                       text_color=theme.ACCENT_TEXT)
        self._refresh_buttons()
        self._say("Connect your Page, pick the videos folder and the Excel file, then Load.", theme.TEXT_MUTED)

    def _path_row(self, card, row: int, label: str, variable: ctk.StringVar, pick) -> None:
        Eyebrow(card, label).grid(row=row, column=0, sticky="w", padx=(theme.PAD, 8), pady=(14 if row == 0 else 6, 0))
        ctk.CTkEntry(card, textvariable=variable, height=30, fg_color=theme.BACKGROUND, border_color=theme.BORDER,
                     text_color=theme.TEXT_MUTED, font=theme.font(12)).grid(
            row=row, column=1, sticky="ew", pady=(14 if row == 0 else 6, 0))
        GhostButton(card, "Choose", pick, width=80, height=30).grid(
            row=row, column=2, padx=(8, theme.PAD), pady=(14 if row == 0 else 6, 0))

    # ------------------------------------------------------------- helpers

    def _say(self, text: str, color: str = theme.TEXT_MUTED) -> None:
        self._status.configure(text=text, text_color=color)

    def _job_ready(self, index: int) -> bool:
        """Has a converted link and a product name line in its caption."""
        job, row = self._jobs[index], self._rows[index]
        needs_name = "{product}" in self._template.get("1.0", "end")
        return bool(job.link) and (not needs_name or len(row.caption().splitlines()) >= 2)

    def refresh_progress(self) -> None:
        """Before posting: how many videos are ready. While posting: how many are done."""
        total = len(self._jobs)
        if not total:
            self._progress.set(0)
            self._progress_label.configure(text="Nothing loaded", text_color=theme.TEXT_MUTED)
            return
        done = sum(1 for j in self._jobs if j.state == "done")
        failed = sum(1 for j in self._jobs if j.state == "failed")
        if self._running or done:
            self._progress.configure(progress_color=theme.SUCCESS if done == total else theme.ACCENT)
            self._progress.set(done / total)
            text = f"Posted {done} / {total}" + (f" · {failed} failed" if failed else "")
            if done == total:
                text = f"All {total} posted ✓"
            self._progress_label.configure(text=text, text_color=theme.DANGER if failed else
                                           (theme.SUCCESS if done == total else theme.TEXT))
            return
        ready = sum(1 for i in range(total) if self._job_ready(i))
        self._progress.configure(progress_color=theme.SUCCESS if ready == total else theme.WARNING)
        self._progress.set(ready / total)
        self._progress_label.configure(
            text=f"Ready to post: {ready} / {total}" + (" ✓" if ready == total else f" · {total - ready} need a fix"),
            text_color=theme.SUCCESS if ready == total else theme.WARNING)
        for i, row in enumerate(self._rows):
            if self._jobs[i].state == "waiting":
                if not self._jobs[i].link:
                    row.show("⚠ no converted link", theme.DANGER)
                elif not self._job_ready(i):
                    row.show("⚠ add the product name", theme.WARNING)
                else:
                    row.show("Ready ✓", theme.SUCCESS)

    def _refresh_buttons(self) -> None:
        ready = bool(self._jobs) and not self._running
        self._start.configure(state="normal" if ready else "disabled",
                              text="Posting…" if self._running else "Start posting")
        self._stop_btn.configure(state="normal" if self._running else "disabled")
        self._copy_ids.configure(state="normal" if any(j.state == "done" for j in self._jobs) else "disabled")

    def _guide(self) -> None:
        webbrowser.open(EXPLORER_URL)
        self._say(GUIDE, theme.TEXT_MUTED)
        self._status.configure(wraplength=1100, justify="left")

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self, initialdir=self._folder.get() or None)
        if folder:
            self._folder.set(folder)

    def _pick_excel(self) -> None:
        path = filedialog.askopenfilename(parent=self, initialdir=self._folder.get() or None,
                                          filetypes=[("Excel file", "*.xlsx")])
        if path:
            self._excel.set(path)

    # --------------------------------------------------------------- actions

    def _save_page_id(self) -> None:
        page = "".join(ch for ch in self._page_id.get() if ch.isdigit())
        if page != self._settings.fb_page_id:
            self._settings.fb_page_id = page
            self._settings.save()

    def _save_token(self) -> None:
        """Keep the token as soon as it's pasted (encrypted), even before Connect."""
        token = self._token.get().strip()
        if token != self._settings.fb_token:
            self._settings.fb_token = token
            if not token:
                self._settings.fb_page_id = self._settings.fb_page_name = ""
            self._settings.save()

    def connect(self) -> None:
        self._save_token()
        token = self._token.get().strip()
        self._page_label.configure(text="Checking…", text_color=theme.TEXT_MUTED)

        def work() -> None:
            try:
                page = facebook.FacebookClient(token).connect()
            except Exception as exc:
                message = str(exc) or "Couldn't connect."
                log_line("facebook connect failed", message[:300])
                self._schedule(lambda: self._page_label.configure(text=message, text_color=theme.DANGER))
                return

            def done() -> None:
                self._settings.fb_token, self._settings.fb_page_id = token, page.id
                self._settings.fb_page_name = page.name
                self._settings.save()
                self._page_label.configure(text=f"Connected: {page.name} ✓", text_color=theme.ACCENT_TEXT)
                self._page_id.delete(0, "end")
                self._page_id.insert(0, page.id)   # each person's token fills in their own Page
            self._schedule(done)

        threading.Thread(target=work, daemon=True).start()

    def load(self) -> None:
        folder, sheet = Path(self._folder.get()), Path(self._excel.get())
        if not folder.is_dir():
            self._say("Choose the folder with your numbered videos.", theme.DANGER)
            return
        if not sheet.is_file():
            self._say("Choose the converted links Excel file from your boss.", theme.DANGER)
            return
        try:
            pairs = excel.read_rows(sheet)
        except Exception as exc:
            self._say(f"Couldn't read the Excel file: {exc}", theme.DANGER)
            return
        videos = facebook.video_files(folder)
        by_file, by_slug = self._get_products(), self._get_scan_names()
        self._jobs = []
        for i, video in enumerate(videos):
            link, sub_id = pairs[i] if i < len(pairs) else ("", "")
            slug = slug_from_subid(sub_id)
            name = by_slug.get(slug) or (by_file.get(video.name.lower(), "") if not sub_id else "")
            self._jobs.append(Job(video, link, sub_id, caption_name(sub_id, name)))
        template = self._template.get("1.0", "end").strip()
        self._settings.fb_template = template
        self._settings.save()
        for row in self._rows:
            row.destroy()
        self._rows = []
        for i, job in enumerate(self._jobs):
            row = JobRow(self._list, i + 1, job, facebook.caption(template, job.link, job.product),
                         on_edit=self.refresh_progress)
            row.grid(row=i, column=0, sticky="ew", padx=6, pady=3)
            self._rows.append(row)
        note = "" if len(videos) == len(pairs) else f"  ⚠ {len(videos)} videos but {len(pairs)} links: check the order."
        missing = sum(1 for j in self._jobs if not j.product)
        hint = f"  {missing} without a product name: type it in the caption." if missing else ""
        self._say(f"{len(self._jobs)} videos loaded. Check the captions, then Start posting.{note}{hint}",
                  theme.DANGER if note else theme.TEXT_MUTED)
        self._restore_posted()
        self._refresh_buttons()
        self.refresh_progress()
        self._name_missing(template)

    def _restore_posted(self) -> None:
        """Videos posted before (even before the app was closed) show as posted, never post twice."""
        log = facebook.load_log()
        earlier = 0
        for job, row in zip(self._jobs, self._rows):
            entry = log.get(str(job.video.resolve()).lower())
            if not entry:
                continue
            earlier += 1
            job.state, job.video_id, job.post_id = "done", entry.get("video_id", ""), entry.get("post_id", "")
            if job.post_id:
                number = facebook.split_id(job.post_id)[1]
                row.enable_check(facebook.post_url(entry.get("page_id") or self._settings.fb_page_id, number))
                row.show(f"✓ Posted earlier · {number}", theme.SUCCESS)
            else:
                row.enable_check(f"https://www.facebook.com/reel/{job.video_id}")
                row.show("✓ Posted earlier · post ID pending (press Fix post IDs)", theme.WARNING)
        if earlier:
            self._say(f"{earlier} of these were already posted (they won't be posted again).", theme.TEXT_MUTED)

    def _name_missing(self, template: str) -> None:
        """Ask Gemini for proper names ("spicesstorage" -> "Spices Storage") the scan doesn't know."""
        missing = {slug_from_subid(j.sub_id) for j in self._jobs if not j.product and j.sub_id}
        missing.discard("")
        if not missing:
            return
        key = self._settings.gemini_api_key
        self._say(f"Making product names for {len(missing)} sub ID(s)…")

        def work() -> None:
            # Offline first (no Gemini quota used); Gemini only for words the app doesn't know.
            names = {slug: split_known(slug) for slug in missing}
            unknown = sorted(slug for slug, name in names.items() if not name)
            if unknown and key:
                try:
                    names.update({k: v for k, v in nice_names(key, unknown).items() if v})
                except Exception as exc:
                    log_line("gemini names failed", str(exc)[:300])
            for slug in missing:                     # still nothing: best offline guess
                names[slug] = names.get(slug) or split_words(slug)

            def apply() -> None:
                fixed = 0
                for job, row in zip(self._jobs, self._rows):
                    name = caption_name(job.sub_id, names.get(slug_from_subid(job.sub_id), ""))
                    if not job.product and name:
                        job.product = name
                        row.set_caption(facebook.caption(template, job.link, name))
                        fixed += 1
                self.refresh_progress()
                left = sum(1 for j in self._jobs if not j.product)
                self._say(f"{len(self._jobs)} videos loaded, {fixed} product names filled in."
                          + (f" {left} still without a name: type it in the caption." if left else
                             " Check the captions, then Start posting."),
                          theme.DANGER if left else theme.TEXT_MUTED)
            self._schedule(apply)

        threading.Thread(target=work, daemon=True).start()

    def start(self) -> None:
        token = self._token.get().strip() or self._settings.fb_token
        if not token:
            self._say("Connect your Page first.", theme.DANGER)
            return
        try:
            delay = max(0, min(int(self._delay.get()), 3600))
        except ValueError:
            delay = 30
        self._settings.fb_delay = delay
        self._settings.save()
        captions = [row.caption() for row in self._rows]
        if "{product}" in self._template.get("1.0", "end"):
            short = [i + 1 for i, (job, text) in enumerate(zip(self._jobs, captions))
                     if job.state != "done" and len(text.splitlines()) < 2]
            if short and not getattr(self, "_warned", False):
                self._warned = True
                self._say(f"⚠ Video {', '.join(map(str, short[:8]))} has no product name in its caption. "
                          "Type it in, or press Start posting again to post anyway.", theme.DANGER)
                return
        self._warned = False
        comment = self._comment.get()
        todo = [i for i, job in enumerate(self._jobs) if job.state != "done"]
        self._running = True
        self.refresh_progress()
        self._stop.clear()
        self._refresh_buttons()

        def work() -> None:
            client = facebook.FacebookClient(token, self._settings.fb_page_id)
            for n, i in enumerate(todo):
                if self._stop.is_set():
                    break
                job, row = self._jobs[i], self._rows[i]
                job.state = "working"
                self._schedule(lambda r=row: r.show("Starting…", theme.ACCENT_TEXT))
                try:
                    result = client.post_reel(job.video, captions[i], captions[i] if comment else "",
                                              on_stage=lambda s, r=row: self._schedule(
                                                  lambda: r.show(s, theme.ACCENT_TEXT)))
                    job.post_id, job.state, job.video_id = result.post_id, "done", result.video_id
                    facebook.save_to_log(job.video, result.video_id, result.post_id, self._settings.fb_page_id)
                    page_id = self._settings.fb_page_id
                    post_number = facebook.split_id(result.post_id)[1] if result.post_id else ""
                    if post_number:
                        url = facebook.post_url(page_id, post_number) if page_id else \
                            f"https://www.facebook.com/{post_number}"
                    else:
                        url = f"https://www.facebook.com/reel/{result.video_id}"
                    self._schedule(lambda r=row, u=url: r.enable_check(u))
                    text = f"✓ Posted · {post_number}" if post_number else "✓ Posted · post ID pending"
                    color = theme.SUCCESS
                    if result.note:
                        text, color = f"{text}\n⚠ {result.note}", theme.WARNING
                    self._schedule(lambda r=row, t=text, c=color: (r.show(t, c), self._refresh_buttons()))
                except facebook.FacebookError as exc:
                    job.state = "failed"
                    message = str(exc)
                    self._schedule(lambda r=row, m=message: r.show(f"✕ {m}", theme.DANGER))
                    if "token" in message.lower() or "permission" in message.lower():
                        break   # every next post would fail the same way
                except Exception as exc:
                    job.state = "failed"
                    message = str(exc) or "unexpected error"
                    self._schedule(lambda r=row, m=message: r.show(f"✕ {m}", theme.DANGER))
                done = sum(1 for j in self._jobs if j.state == "done")
                self._schedule(lambda d=done: (self._say(f"Posted {d} of {len(self._jobs)}.", theme.TEXT_MUTED),
                                               self.refresh_progress()))
                if n < len(todo) - 1 and not self._stop.is_set():
                    self._schedule(lambda: self._say(
                        f"Waiting {delay}s before the next post (keeps your Page safe from spam limits)…"))
                    self._stop.wait(delay)
            self._fix_missing_ids(client)        # one more try for any post ID Facebook was slow to give
            self._schedule(self._finished)

        threading.Thread(target=work, daemon=True).start()

    def _fix_missing_ids(self, client: "facebook.FacebookClient") -> int:
        """Runs in a worker thread. Fills in post IDs that were still pending. Returns how many it fixed."""
        fixed = 0
        for job, row in zip(self._jobs, self._rows):
            if job.state != "done" or job.post_id or not job.video_id:
                continue
            try:
                post_id = client.find_post_id(job.video_id)
            except facebook.FacebookError:
                post_id = ""
            if post_id:
                job.post_id, fixed = post_id, fixed + 1
                facebook.save_to_log(job.video, job.video_id, post_id, self._settings.fb_page_id)
                post_number = facebook.split_id(post_id)[1]
                url = facebook.post_url(self._settings.fb_page_id, post_number)
                self._schedule(lambda r=row, u=url, n=post_number: (
                    r.enable_check(u), r.show(f"✓ Posted · {n}", theme.SUCCESS), self._refresh_buttons()))
        return fixed

    def fix_post_ids(self) -> None:
        """Button: fetch post IDs that are still pending (e.g. Facebook was slow)."""
        token = self._token.get().strip() or self._settings.fb_token
        pending = [j for j in self._jobs if j.state == "done" and not j.post_id and j.video_id]
        if not pending:
            self._say("Every posted video already has its post ID ✓", theme.ACCENT_TEXT)
            return
        self._say(f"Getting {len(pending)} missing post ID(s) from Facebook…")

        def work() -> None:
            fixed = self._fix_missing_ids(facebook.FacebookClient(token, self._settings.fb_page_id))
            left = len(pending) - fixed
            self._schedule(lambda: self._say(
                f"Fixed {fixed} post ID(s)." + (f" {left} still pending: try again in a few minutes." if left else " ✓"),
                theme.WARNING if left else theme.ACCENT_TEXT))

        threading.Thread(target=work, daemon=True).start()

    def _finished(self) -> None:
        self._running = False
        self.refresh_progress()
        done = sum(1 for j in self._jobs if j.state == "done")
        failed = sum(1 for j in self._jobs if j.state == "failed")
        self._say(f"Done: {done} posted" + (f", {failed} failed (press Start posting to retry them)" if failed else "")
                  + ". Copy post IDs copies them in video order.", theme.ACCENT_TEXT if not failed else theme.DANGER)
        self._refresh_buttons()

    def stop(self) -> None:
        self._stop.set()
        self._say("Stopping after the current video…")

    def posted_ids(self) -> list[str]:
        return [facebook.split_id(j.post_id)[1] for j in self._jobs if j.post_id]

    def _copy_post_ids(self) -> None:
        """Full IDs for your boss: 584817111379300_122219645510763039, one per line in video order."""
        ids = []
        for job in self._jobs:
            if not job.post_id:
                ids.append("")          # blank line keeps the order for videos that didn't post
                continue
            page_id = "".join(ch for ch in self._page_id.get() if ch.isdigit()) or self._settings.fb_page_id
            _, post = facebook.split_id(job.post_id)
            ids.append(f"{page_id}_{post}" if page_id else post)
        self.clipboard_clear()
        self.clipboard_append("\n".join(ids))
        pending = sum(1 for j in self._jobs if j.state == "done" and not j.post_id)
        self._say(f"Copied {sum(1 for i in ids if i)} post IDs (pageid_postid), one per line in video order."
                  + (f" ⚠ {pending} still pending (blank lines): press Fix post IDs." if pending else ""),
                  theme.WARNING if pending else theme.ACCENT_TEXT)


class JobRow(ctk.CTkFrame):
    def __init__(self, master, number: int, job: Job, text: str, on_edit=None):
        super().__init__(master, fg_color=theme.SURFACE_RAISED, corner_radius=10)
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=f"{number:02d}", width=28, font=theme.mono(12),
                     text_color=theme.TEXT_FAINT).grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=10)
        ctk.CTkLabel(self, text=job.video.name, anchor="w", font=theme.font(12, "bold"),
                     text_color=theme.TEXT).grid(row=0, column=1, sticky="ew", pady=(8, 2))
        self._caption = ctk.CTkTextbox(self, height=60, fg_color=theme.BACKGROUND, border_width=0,
                                       corner_radius=6, font=theme.font(12), text_color=theme.TEXT_MUTED)
        self._caption.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        self._caption.insert("1.0", text)
        if on_edit:
            self._caption.bind("<KeyRelease>", lambda _e: on_edit())
        self._state = ctk.CTkLabel(self, text="Waiting", width=230, anchor="e", font=theme.font(11),
                                   text_color=theme.TEXT_FAINT, wraplength=230)
        self._state.grid(row=0, column=2, rowspan=2, padx=12)
        self._check = GhostButton(self, "Check ↗", lambda: webbrowser.open(self._url), width=86, height=30)
        self._url = ""
        if not job.link:
            self.show("⚠ no converted link for this video", theme.DANGER)

    def enable_check(self, url: str) -> None:
        """Show the [Check ↗] button that opens the post on Facebook."""
        self._url = url
        self._check.grid(row=0, column=3, rowspan=2, padx=(0, 12))

    def set_caption(self, text: str) -> None:
        self._caption.delete("1.0", "end")
        self._caption.insert("1.0", text)

    def caption(self) -> str:
        return self._caption.get("1.0", "end").strip()

    def show(self, text: str, color: str) -> None:
        self._state.configure(text=text, text_color=color)
