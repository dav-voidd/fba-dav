"""Shopee helpers (no scraping: we only build public search links)."""

from urllib.parse import urlencode

SHOPEE_SEARCH = "https://shopee.ph/search"


def search_url(query: str) -> str:
    """Shopee PH search for ``query``, best sellers first (most sold, usually most reviewed)."""
    return f"{SHOPEE_SEARCH}?{urlencode({'keyword': query, 'sortBy': 'sales'})}"
