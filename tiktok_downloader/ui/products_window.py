"""Sub IDs window.

A four-step tracker shows exactly where the scan is:
    1 Upload  ->  2 Product names  ->  3 Sub IDs  ->  4 Links
Product names appear on each row as Gemini answers; sub IDs (and their 1, 2 numbering)
are generated once every name is in, and only then are Copy and Shopee switched on.
"""

from __future__ import annotations

import webbrowser
from datetime import date, timedelta
from typing import Callable

import customtkinter as ctk

from ..links import shorten
from ..models import QueueItem, Status
from ..products.shopee import search_url
from ..products.subid import date_prefix
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


class ProductsWindow(ctk.CTkFrame):
    """The Sub IDs page, shown as a tab inside the main window."""

    def __init__(self, master, *, get_items: Callable[[], list[QueueItem]], on_scan: Action,
                 on_scan_folder: Action | None = None,
                 on_connect: Action, is_connected: Callable[[], bool], is_scanning: Callable[[], bool],
                 code: ctk.StringVar, on_code_changed: Action,
                 date: ctk.StringVar, on_date_changed: Action):
        super().__init__(master, fg_color="transparent")
        self._get_items = get_items
        self._is_connected = is_connected
        self._is_scanning = is_scanning
        self._code = code
        self._date = date
        self._on_date_changed = on_date_changed
        self._rows: dict[int, SubIdRow] = {}
        self.selected: set[int] = set()
        self._last_clicked: int | None = None
        self._status_text = ""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        # --- header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(head, text="Sub IDs", font=theme.font(18, "bold"), text_color=theme.TEXT).pack(side="left")
        self._scan = PrimaryButton(head, "Scan with Gemini", on_scan, width=170, height=36)
        self._scan.pack(side="right")
        if on_scan_folder:
            GhostButton(head, "📁 Scan a folder", on_scan_folder, width=140).pack(side="right", padx=(0, 8))
        self._copy_all_btn = GhostButton(head, "Copy all", self._copy_all, width=90)
        self._copy_all_btn.pack(side="right", padx=(0, 8))
        self._connect = TextButton(head, "", on_connect)
        self._connect.pack(side="right", padx=(0, 8))

        # --- tracker card
        card = ctk.CTkFrame(self, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                            border_width=1, border_color=theme.BORDER)
        card.grid(row=1, column=0, sticky="ew")
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

        # --- date + code
        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=2, column=0, sticky="ew", pady=(12, 6))
        Eyebrow(options, "Date").pack(side="left", padx=(0, 8))
        date_entry = ctk.CTkEntry(options, textvariable=date, width=80, height=30, fg_color=theme.SURFACE,
                                  border_color=theme.BORDER_STRONG, text_color=theme.TEXT, font=theme.mono(12))
        date_entry.pack(side="left")
        date_entry.bind("<KeyRelease>", lambda _e: on_date_changed())
        TextButton(options, "Today", lambda: self._set_date(0)).pack(side="left", padx=(4, 0))
        TextButton(options, "Tomorrow", lambda: self._set_date(1)).pack(side="left", padx=(0, 18))
        Eyebrow(options, "Code").pack(side="left", padx=(0, 8))
        entry = ctk.CTkEntry(options, textvariable=code, width=70, height=30, fg_color=theme.SURFACE,
                             border_color=theme.BORDER_STRONG, text_color=theme.TEXT, font=theme.mono(12))
        entry.pack(side="left")
        entry.bind("<KeyRelease>", lambda _e: on_code_changed())
        self._example = ctk.CTkLabel(options, font=theme.font(11), text_color=theme.TEXT_FAINT)
        self._example.pack(side="left", padx=12)

        # shop tag for the selected rows (own line, so nothing gets squeezed)
        shop_row = ctk.CTkFrame(self, fg_color="transparent")
        shop_row.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        Eyebrow(shop_row, "Shop").pack(side="left", padx=(0, 8))
        self._shop = ctk.CTkEntry(shop_row, width=220, height=30, fg_color=theme.SURFACE,
                                  border_color=theme.BORDER_STRONG, text_color=theme.TEXT, font=theme.mono(12),
                                  placeholder_text="FOODCART")
        self._shop.pack(side="left")
        self._shop.bind("<Return>", lambda _e: self._add_shop())
        self._apply_shop = PrimaryButton(shop_row, "Add to selected", self._add_shop, width=170, height=30)
        self._apply_shop.pack(side="left", padx=(8, 4))
        TextButton(shop_row, "Remove", self._remove_shop).pack(side="left")
        self._select_all = TextButton(shop_row, "Select all", self._toggle_select_all)
        self._select_all.pack(side="left", padx=(14, 0))
        ctk.CTkLabel(shop_row, text="Click 01, 02… to pick rows · Shift+click for a range",
                     font=theme.font(11), text_color=theme.TEXT_FAINT).pack(side="left", padx=12)

        # --- rows
        self._list = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE, corner_radius=theme.RADIUS_CARD,
                                            border_width=1, border_color=theme.BORDER,
                                            scrollbar_button_color=theme.BORDER)
        self._list.grid(row=4, column=0, sticky="nsew", pady=(0, 12))
        self._list.grid_columnconfigure(0, weight=1)
        self.refresh()

    # ------------------------------------------------------------------ API

    def refresh(self) -> None:
        items = self._items()
        for index in [k for k in self._rows if k not in {i.index for i in items}]:
            self._rows.pop(index).destroy()
        for item in items:
            row = self._rows.get(item.index)
            if row is None:
                row = self._rows[item.index] = SubIdRow(self._list, item, self)
                row.set_selected(item.index in self.selected)
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
        day = "".join(ch for ch in self._date.get() if ch.isalnum()).upper() or date_prefix()
        self._example.configure(text=f"e.g. {day}{code}ledflashlight  ·  repeats get 1, 2…")

    def _set_date(self, days_ahead: int) -> None:
        self._date.set(date_prefix(date.today() + timedelta(days=days_ahead)))
        self._on_date_changed()

    def copy(self, text: str, note: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self._live.configure(text=note, text_color=theme.ACCENT_TEXT)

    def _items(self) -> list[QueueItem]:
        return [i for i in self._get_items() if i.status is Status.DONE]

    # ------------------------------------------------------------ selection

    def click_row(self, index: int, shift: bool) -> None:
        """Click a row to select it; Shift+click selects everything in between."""
        if shift and self._last_clicked is not None:
            order = [i.index for i in self._items()]
            if index in order and self._last_clicked in order:
                a, b = sorted((order.index(index), order.index(self._last_clicked)))
                self.selected.update(order[a:b + 1])
        elif index in self.selected:
            self.selected.discard(index)
        else:
            self.selected.add(index)
        self._last_clicked = index
        self._render_selection()

    def _toggle_select_all(self) -> None:
        ids = {i.index for i in self._items() if i.product}
        self.selected = set() if ids and ids <= self.selected else ids
        self._render_selection()

    def _render_selection(self) -> None:
        self.selected &= {i.index for i in self._items()}
        for index, row in self._rows.items():
            row.set_selected(index in self.selected)
        count = len(self.selected)
        self._apply_shop.configure(text=f"Add to selected ({count})" if count else "Add to selected")
        all_ids = {i.index for i in self._items() if i.product}
        self._select_all.configure(text="Clear selection" if all_ids and all_ids <= self.selected else "Select all")

    def _chosen(self) -> list[QueueItem]:
        return [i for i in self._items() if i.index in self.selected and i.product]

    def _add_shop(self) -> None:
        tag = "".join(ch for ch in self._shop.get() if ch.isascii() and ch.isalnum()).upper()
        chosen = self._chosen()
        if not chosen:
            self._live.configure(text="Click the rows (01, 02…) you want first. Shift+click selects a range.",
                                 text_color=theme.DANGER)
            return
        if not tag:
            self._live.configure(text="Type the shop name first.", text_color=theme.DANGER)
            return
        for item in chosen:
            item.product.shop = tag
        self._finish_shop(f"Added {tag} to {len(chosen)} sub ID(s).")

    def _remove_shop(self) -> None:
        chosen = self._chosen()
        for item in chosen:
            item.product.shop = ""
        self._finish_shop(f"Removed the shop from {len(chosen)} sub ID(s)." if chosen
                          else "Select the rows to remove the shop from.")

    def _finish_shop(self, note: str) -> None:
        self.selected.clear()
        self.refresh()
        self._render_selection()
        self._live.configure(text=note, text_color=theme.ACCENT_TEXT)

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

        self._number = ctk.CTkLabel(self, text=f"{item.index:02d}", width=34, height=26, corner_radius=8,
                                    font=theme.mono(12), text_color=theme.TEXT_FAINT, cursor="hand2")
        self._number.grid(row=0, column=0, rowspan=3, padx=(12, 8), pady=10)
        for widget in (self, self._number):
            widget.bind("<Button-1>", lambda e: self._window.click_row(self._item.index, bool(e.state & 0x0001)))

        self._name = ctk.CTkLabel(self, anchor="w", font=theme.font(14, "bold"), text_color=theme.TEXT,
                                  cursor="hand2")
        self._name.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(10, 0))
        self._name.bind("<Button-1>", lambda e: self._window.click_row(self._item.index, bool(e.state & 0x0001)))

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

    def set_selected(self, selected: bool) -> None:
        background = theme.ACCENT_SOFT if selected else theme.SURFACE_RAISED
        self.configure(fg_color=background)
        self._entry.configure(fg_color=background)
        self._number.configure(text=("✓ " if selected else "") + f"{self._item.index:02d}",
                               fg_color=theme.ACCENT if selected else "transparent",
                               text_color="#FFFFFF" if selected else theme.TEXT_FAINT)

    def _save_edit(self) -> None:
        self._editing = False
        product = self._item.product
        if not product:
            return
        text = "".join(ch for ch in self._value.get() if ch.isalnum())
        if product.shop and text.endswith(product.shop):
            text = text[: -len(product.shop)]   # the shop tag is kept separately
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
