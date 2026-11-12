"""Sub IDs window.

A four-step tracker shows exactly where the scan is:
    1 Upload  ->  2 Product names  ->  3 Sub IDs  ->  4 Links
Product names appear on each row as Gemini answers; sub IDs (and their 1, 2 numbering)
are generated once every name is in, and only then are Copy and Shopee switched on.
"""

from __future__ import annotations

import webbrowser
from typing import Callable

import customtkinter as ctk

from ..links import shorten
from ..models import QueueItem, Status
from ..products.shopee import search_url
from . import theme
from .widgets import Eyebrow, GhostButton, PrimaryButton, TextButton

Action = Callable[[], None]

STAGE_TEXT = {
    "": "Waiting to upload",
    "uploading": "Uploading to Gemini…",
    "uploaded": "Uploaded ✓ · waiting for Gemini",
    "analyzing": "Gemini is watching…",
    "done": "",
    "failed": "",
}


class Step(ctk.CTkFrame):
    """One step of the tracker: a numbered dot, a title and a live detail line."""

    def __init__(self, master, number: int, title: str):
        super().__init__(master, fg_color="transparent")
        self._number = str(number)
        self._dot = ctk.CTkLabel(self, text=self._number, width=26, height=26, corner_radius=13,
                                 font=theme.font(12, "bold"))
        self._dot.pack(side="left")
        text = ctk.CTkFrame(self, fg_color="transparent")
        text.pack(side="left", padx=(8, 0))
        self._title = ctk.CTkLabel(text, text=title, font=theme.font(13, "bold"), anchor="w")
        self._title.pack(anchor="w")
        self._detail = ctk.CTkLabel(text, text="", font=theme.font(11), anchor="w",
                                    text_color=theme.TEXT_FAINT)
        self._detail.pack(anchor="w")
        self.set("todo", "")

    def set(self, state: str, detail: str) -> None:
        """state: todo | active | done | failed"""
        fill, text_color, title = {
            "todo": (theme.SURFACE_RAISED, theme.TEXT_FAINT, theme.TEXT_FAINT),
            "active": (theme.ACCENT, "#FFFFFF", theme.TEXT),
            "done": (theme.ACCENT_SOFT, theme.ACCENT_TEXT, theme.TEXT_MUTED),
            "failed": (theme.DANGER_SOFT, theme.DANGER, theme.DANGER),
        }[state]
        self._dot.configure(fg_color=fill, text_color=text_color,
                            text="✓" if state == "done" else "✕" if state == "failed" else self._number)
        self._title.configure(text_color=title)
        self._detail.configure(text=detail)


class ProductsWindow(ctk.CTkToplevel):
    def __init__(self, master, *, get_items: Callable[[], list[QueueItem]], on_scan: Action,
                 on_connect: Action, is_connected: Callable[[], bool], is_scanning: Callable[[], bool],
                 code: ctk.StringVar, on_code_changed: Action):
        super().__init__(master)
        self.title("Sub IDs")
        self.geometry("880x700")
        self.minsize(700, 480)
        self.configure(fg_color=theme.BACKGROUND)
        self._get_items = get_items
        self._is_connected = is_connected
        self._is_scanning = is_scanning
        self._code = code
        self._rows: dict[int, SubIdRow] = {}
        self._status_text = ""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # --- header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 12))
        ctk.CTkLabel(head, text="Sub IDs", font=theme.font(18, "bold"), text_color=theme.TEXT).pack(side="left")
        self._scan = PrimaryButton(head, "Scan with Gemini", on_scan, width=170, height=36)
        self._scan.pack(side="right")
        self._copy_all_btn = GhostButton(head, "Copy all", self._copy_all, width=90)
        self._copy_all_btn.pack(side="right", padx=(0, 8))
        self._connect = TextButton(head, "", on_connect)
        self._connect.pack(side="right", padx=(0, 8))

        # --- tracker card
        card = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                            border_width=1, border_color=theme.BORDER)
        card.grid(row=1, column=0, sticky="ew", padx=24)
        steps = ctk.CTkFrame(card, fg_color="transparent")
        steps.pack(fill="x", padx=18, pady=(16, 10))
        self._steps = [Step(steps, i + 1, title) for i, title in
                       enumerate(("Upload", "Product names", "Sub IDs", "Links"))]
        for i, step in enumerate(self._steps):
            step.grid(row=0, column=i, sticky="w")
            steps.grid_columnconfigure(i, weight=1)
        self._bar = ctk.CTkProgressBar(card, height=6, corner_radius=3, fg_color=theme.BORDER,
                                       progress_color=theme.ACCENT)
        self._bar.pack(fill="x", padx=18)
        self._bar.set(0)
        self._bar_mode = "determinate"
        self._live = ctk.CTkLabel(card, text="", font=theme.font(12), text_color=theme.TEXT_MUTED, anchor="w")
        self._live.pack(fill="x", padx=18, pady=(6, 14))

        # --- code
        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=2, column=0, sticky="ew", padx=24, pady=12)
        Eyebrow(options, "Code").pack(side="left", padx=(0, 8))
        entry = ctk.CTkEntry(options, textvariable=code, width=70, height=30, fg_color=theme.SURFACE,
                             border_color=theme.BORDER_STRONG, text_color=theme.TEXT, font=theme.mono(12))
        entry.pack(side="left")
        entry.bind("<KeyRelease>", lambda _e: on_code_changed())
        self._example = ctk.CTkLabel(options, font=theme.font(11), text_color=theme.TEXT_FAINT)
        self._example.pack(side="left", padx=12)

        # --- rows
        self._list = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                                            border_width=1, border_color=theme.BORDER,
                                            scrollbar_button_color=theme.BORDER)
        self._list.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 24))
        self._list.grid_columnconfigure(0, weight=1)
        self.refresh()
        self.after(150, self.lift)

    # ------------------------------------------------------------------ API

    def refresh(self) -> None:
        items = self._items()
        for index in [k for k in self._rows if k not in {i.index for i in items}]:
            self._rows.pop(index).destroy()
        for item in items:
            row = self._rows.get(item.index)
            if row is None:
                row = self._rows[item.index] = SubIdRow(self._list, item, self)
                row.grid(row=item.index, column=0, sticky="ew", padx=6, pady=3)
            row.render(item, self.subids_ready)
        self.refresh_header()

    def refresh_item(self, item: QueueItem) -> None:
        row = self._rows.get(item.index)
        if row is None:
            self.refresh()
            return
        row.render(item, self.subids_ready)
        self.refresh_header()

    def set_status(self, text: str) -> None:
        self._status_text = text
        self.refresh_header()

    @property
    def subids_ready(self) -> bool:
        items = self._items()
        return bool(items) and not self._is_scanning() and any(i.product for i in items)

    def refresh_header(self) -> None:
        items = self._items()
        total = len(items)
        uploaded = sum(1 for i in items if i.scan_stage in ("uploaded", "analyzing", "done") or i.product)
        named = sum(1 for i in items if i.product)
        failed = sum(1 for i in items if i.scan_stage == "failed" or (i.scan_error and not i.product))
        scanning = self._is_scanning()
        analyzing = sum(1 for i in items if i.scan_stage == "analyzing")
        ready = self.subids_ready

        # Step 1 - upload
        if not total:
            self._steps[0].set("todo", "download videos first")
        elif uploaded + failed >= total and total:
            self._steps[0].set("done", f"{uploaded} / {total}")
        else:
            self._steps[0].set("active" if scanning else "todo", f"{uploaded} / {total}")
        # Step 2 - names
        if named + failed >= total and total and not scanning:
            self._steps[1].set("failed" if failed and not named else "done",
                               f"{named} / {total}" + (f" · {failed} failed" if failed else ""))
        else:
            self._steps[1].set("active" if analyzing or (scanning and uploaded) else "todo",
                               f"{named} / {total}" + (f" · {analyzing} being watched" if analyzing else ""))
        # Steps 3 and 4 - generated together once every name is in
        self._steps[2].set("done" if ready else "todo", f"{named} ready" if ready else "after all names")
        self._steps[3].set("done" if ready else "todo", "Shopee ↗ on each row" if ready else "after sub IDs")

        # Progress bar: moving while Gemini thinks (no partial progress to show)
        if scanning and analyzing and not named:
            if self._bar_mode != "indeterminate":
                self._bar.configure(mode="indeterminate")
                self._bar.start()
                self._bar_mode = "indeterminate"
        else:
            if self._bar_mode != "determinate":
                self._bar.stop()
                self._bar.configure(mode="determinate")
                self._bar_mode = "determinate"
            self._bar.set((uploaded + named) / (2 * total) if total else 0)

        if scanning:
            live = self._status_text or "Scanning…"
        elif ready:
            live = f"Done. {named} sub IDs ready" + (f", {failed} failed (press Scan to retry them)" if failed else "") + "."
        elif total:
            live = "Press Scan with Gemini to start." if not named else ""
        else:
            live = "Download some videos first."
        self._live.configure(text=live, text_color=theme.DANGER if "failed" in live and not named else theme.TEXT_MUTED)

        self._scan.configure(state="disabled" if scanning else "normal",
                             text="Scanning…" if scanning else ("Scan again" if failed else "Scan with Gemini"))
        self._copy_all_btn.configure(state="normal" if ready else "disabled")
        connected = self._is_connected()
        self._connect.configure(text="Gemini connected ✓" if connected else "Connect Gemini",
                                text_color=theme.ACCENT_TEXT if connected else theme.TEXT_MUTED)
        code = "".join(ch for ch in self._code.get() if ch.isalnum())
        self._example.configure(text=f"e.g. NOV11{code}ledflashlight  ·  repeats get 1, 2…  ·  "
                                     "click a sub ID to edit it")

    def copy(self, text: str, note: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self._live.configure(text=note, text_color=theme.ACCENT_TEXT)

    def _items(self) -> list[QueueItem]:
        return [i for i in self._get_items() if i.status is Status.DONE]

    def _copy_all(self) -> None:
        ids = [i.product.display_sub_id for i in self._items() if i.product and i.product.display_sub_id]
        if ids:
            self.copy("\n".join(ids), f"Copied {len(ids)} sub IDs, one per line.")


class SubIdRow(ctk.CTkFrame):
    def __init__(self, master, item: QueueItem, window: ProductsWindow):
        super().__init__(master, fg_color=theme.SURFACE_RAISED, corner_radius=10)
        self._window = window
        self._item = item
        self._editing = False
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text=f"{item.index:02d}", width=28, font=theme.mono(12),
                     text_color=theme.TEXT_FAINT).grid(row=0, column=0, rowspan=3, padx=(12, 8), pady=10)

        self._name = ctk.CTkLabel(self, anchor="w", font=theme.font(14, "bold"), text_color=theme.TEXT)
        self._name.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(10, 0))

        self._value = ctk.StringVar()
        self._entry = ctk.CTkEntry(self, textvariable=self._value, height=28, border_width=0,
                                   fg_color=theme.SURFACE_RAISED, text_color=theme.ACCENT_TEXT,
                                   font=theme.mono(13))
        self._entry.bind("<FocusIn>", lambda _e: setattr(self, "_editing", True))
        self._entry.bind("<FocusOut>", lambda _e: self._save_edit())
        self._entry.bind("<Return>", lambda _e: (self._save_edit(), self.focus()))

        self._detail = ctk.CTkLabel(self, anchor="w", font=theme.font(11), text_color=theme.TEXT_FAINT)
        self._detail.grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(0, 10))

        self._shopee = GhostButton(self, "Shopee ↗", self._open_shopee, width=90, height=30)
        self._shopee.grid(row=0, column=2, rowspan=3, padx=(12, 6))
        self._copy = GhostButton(self, "Copy", self._copy_one, width=70, height=30)
        self._copy.grid(row=0, column=3, rowspan=3, padx=(0, 12))

    def render(self, item: QueueItem, subids_ready: bool) -> None:
        self._item = item
        product = item.product
        caption = item.post.caption if item.post and item.post.caption else item.url
        has_id = bool(product and subids_ready and product.display_sub_id)

        if product:
            self._name.configure(text=shorten(product.name, 64), text_color=theme.TEXT)
        else:
            self._name.configure(text=shorten(caption, 64), text_color=theme.TEXT_MUTED)

        if has_id:
            if not self._editing:  # never overwrite what is being typed
                self._value.set(product.display_sub_id)
            self._entry.grid(row=1, column=1, sticky="ew")
        else:
            self._entry.grid_remove()

        if item.scan_error and not product:
            detail, color = f"✕ {item.scan_error}", theme.DANGER
        elif product and not has_id:
            detail, color = "✓ Named · sub ID comes when every video is named", theme.ACCENT_TEXT
        elif product:
            detail, color = ("edited" if product.custom_sub_id else ""), theme.TEXT_FAINT
        else:
            detail, color = STAGE_TEXT.get(item.scan_stage, ""), (
                theme.ACCENT_TEXT if item.scan_stage in ("analyzing", "uploading") else theme.TEXT_FAINT)
        self._detail.configure(text=detail, text_color=color)
        state = "normal" if has_id else "disabled"
        self._copy.configure(state=state)
        self._shopee.configure(state=state)

    def _save_edit(self) -> None:
        self._editing = False
        product = self._item.product
        if not product:
            return
        text = "".join(ch for ch in self._value.get() if ch.isalnum())
        product.custom_sub_id = "" if not text or text == product.sub_id else text
        self.render(self._item, True)

    def _open_shopee(self) -> None:
        if self._item.product:
            webbrowser.open(search_url(self._item.product.name))

    def _copy_one(self) -> None:
        self._save_edit()
        if self._item.product:
            sub_id = self._item.product.display_sub_id
            self._window.copy(sub_id, f"Copied {sub_id}")
