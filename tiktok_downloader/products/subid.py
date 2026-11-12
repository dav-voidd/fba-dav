"""Affiliate sub ID generator.

    NOV11 + IC + spicesstorage + 1  ->  NOV11ICspicesstorage1
    date    code   product (≤2 words)  #

The number is added only when the same product appears more than once in a batch,
counting in queue order. The code ("IC") is a user setting.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Iterable

from ..models import QueueItem


def date_prefix(when: date | None = None) -> str:
    when = when or date.today()
    return f"{when.strftime('%b').upper()}{when.day}"


def product_slug(short_name: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", short_name.lower())[:2])


def clean_code(text: str) -> str:
    return "".join(re.findall(r"[A-Za-z0-9]+", text or ""))


def make_subid(short_name: str, when: date | None = None, code: str = "IC",
               number: int | None = None) -> str:
    return date_prefix(when) + clean_code(code) + product_slug(short_name) + (str(number) if number else "")


def assign_subids(items: Iterable[QueueItem], code: str = "IC", when: date | None = None) -> None:
    """Give every recognised item its sub ID, numbering repeated products 1, 2, 3…"""
    scanned = [item for item in items if item.product]
    counts: dict[str, int] = {}
    for item in scanned:
        slug = product_slug(item.product.short_name)
        counts[slug] = counts.get(slug, 0) + 1
    seen: dict[str, int] = {}
    for item in scanned:
        slug = product_slug(item.product.short_name)
        number = None
        if counts[slug] > 1:
            seen[slug] = seen.get(slug, 0) + 1
            number = seen[slug]
        item.product.sub_id = make_subid(item.product.short_name, when, code, number)
