"""Curated food/dish catalog — data-driven (loaded from app/data/regional_dishes.json).

Composite and regional dishes that generic USDA search matches poorly (suya →
a peanut product, "mixed rice" → a fortified seasoned product, etc.) live in a
JSON data file so new dishes are *data, not code*. This module loads that file
once and exposes `lookup(food_name)` which the estimator consults after learned
corrections and before USDA.

Match spec per entry (see the JSON's `_comment`):
  - "all_of": every item must match. A string → that token must be present; a
    nested array → at least one of its tokens must be present (an OR-group).
  - "any_of": at least one of the listed tokens is present.
  - "exact":  the normalized name (lowercased, single-spaced) equals a phrase.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "regional_dishes.json"


@lru_cache(maxsize=1)
def _catalog() -> list[tuple[str, dict]]:
    """Load and cache the dish catalog as ordered (key, entry) pairs."""
    try:
        raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover — missing/corrupt data file
        logger.warning("regional_dishes.json unavailable: %s", exc)
        return []
    return [(k, v) for k, v in raw.items()
            if not k.startswith("_") and isinstance(v, dict) and "nutrients" in v]


def _matches(spec: dict, joined: str, tokset: set[str]) -> bool:
    if not spec:
        return False
    if "exact" in spec and joined in set(spec["exact"]):
        return True
    if "any_of" in spec and any(t in tokset for t in spec["any_of"]):
        return True
    if "all_of" in spec:
        for item in spec["all_of"]:
            if isinstance(item, (list, tuple)):
                if not any(alt in tokset for alt in item):
                    return False
            elif item not in tokset:
                return False
        return True
    return False


def lookup(food_name: str) -> tuple[str, dict] | None:
    """Return (canonical_label, per-100 g nutrients) for a curated dish, else None."""
    toks = re.findall(r"[a-z]+", (food_name or "").lower())
    if not toks:
        return None
    joined = " ".join(toks)
    tokset = set(toks)
    for _key, entry in _catalog():
        if _matches(entry.get("match", {}), joined, tokset):
            return (entry.get("label", _key), dict(entry["nutrients"]))
    return None
