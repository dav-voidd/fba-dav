"""Shared pieces of the product scanner."""

from __future__ import annotations


class ScanError(Exception):
    """A product could not be recognised (bad key, no answer, nothing to look at…)."""


def normalise_result(result: dict) -> dict:
    """Clean an AI answer into product_name / short_name / confidence."""
    result["product_name"] = " ".join(str(result.get("product_name", "")).split())
    result["short_name"] = " ".join(str(result.get("short_name", "")).lower().split()[:2])
    try:
        result["confidence"] = max(0.0, min(1.0, float(result.get("confidence") or 0)))
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    if not result["product_name"]:
        raise ScanError("The AI could not tell what the product is.")
    return result
