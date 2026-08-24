"""RxNorm (NLM RxNav) — the authority on what is actually a medication.

Free, public, no API key. https://rxnav.nlm.nih.gov/

This exists because the alternative was a 23-row seeded table, and a hand-written
list of drugs is a list of the drugs somebody remembered. Measured against RxNorm:

    calcitriol           -> rxcui 1894      known
    calcium calcitriol   -> NONE            correctly not a drug
    sevelamer carbonate  -> rxcui 660890    known — and NOT in our seed table,
                                            so the seeded check waved it through
                                            as "unrecognised, allow"

RxNorm also carries real marketed strengths, which removes the need to hand-write
dose ceilings — the largest marketed oral calcitriol is 0.0005 MG (0.5 mcg), so
"calcitriol 1000 mg" is two million times the biggest pill made. A number derived
from what is actually sold beats a number somebody typed from memory.

**Fails open.** If RxNav is unreachable we return "unknown", never "invalid" —
blocking every dose log in the app because a third-party API is down would be a
far worse failure than the one this guards against.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://rxnav.nlm.nih.gov/REST"
_TIMEOUT = 6.0
_CACHE_TTL = 86_400.0            # a drug's identity does not change daily
_NEGATIVE_TTL = 3600.0           # re-ask sooner about a name we could not resolve

_cache: dict[str, tuple[float, "DrugFacts"]] = {}


@dataclass(frozen=True)
class DrugFacts:
    """What RxNorm says about a typed name."""
    query: str
    rxcui: str | None = None          # set when the name resolves exactly
    suggestion: str | None = None     # best approximate match when it does not
    max_strength_mg: float | None = None   # largest marketed single unit
    reachable: bool = True            # False when RxNav could not be consulted

    @property
    def known(self) -> bool:
        return self.rxcui is not None


def _cached(key: str) -> DrugFacts | None:
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    return None


def _store(key: str, facts: DrugFacts) -> DrugFacts:
    ttl = _CACHE_TTL if facts.known else _NEGATIVE_TTL
    _cache[key] = (time.time() + ttl, facts)
    return facts


def _max_strength_mg(payload: dict) -> float | None:
    """Largest single-unit strength in MG across this drug's marketed products.

    RxNorm SCD names carry the strength inline: "calcitriol 0.0005 MG Oral
    Capsule". Concentrations ("0.001 MG/ML Injection") are skipped — they are
    per-mL, not per-dose, so treating them as a unit strength would inflate the
    ceiling and defeat the check.
    """
    best: float | None = None
    for group in (payload.get("relatedGroup") or {}).get("conceptGroup") or []:
        for concept in group.get("conceptProperties") or []:
            for m in re.finditer(r"(\d*\.?\d+)\s*MG(?!\s*/)", concept.get("name", ""), re.I):
                try:
                    value = float(m.group(1))
                except ValueError:
                    continue
                if best is None or value > best:
                    best = value
    return best


async def lookup(name: str) -> DrugFacts:
    """Resolve a typed medication name against RxNorm. Never raises."""
    query = (name or "").strip()
    if not query:
        return DrugFacts(query="", reachable=True)

    key = query.lower()
    hit = _cached(key)
    if hit is not None:
        return hit

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            exact = await client.get(f"{BASE_URL}/rxcui.json", params={"name": query})
            exact.raise_for_status()
            ids = ((exact.json().get("idGroup") or {}).get("rxnormId")) or []
            rxcui = str(ids[0]) if ids else None

            if rxcui is None:
                approx = await client.get(
                    f"{BASE_URL}/approximateTerm.json",
                    params={"term": query, "maxEntries": 5},
                )
                approx.raise_for_status()
                candidates = (approx.json().get("approximateGroup") or {}).get("candidate") or []
                named = [c for c in candidates if (c.get("name") or "").strip()]
                suggestion = named[0]["name"] if named else None
                return _store(key, DrugFacts(query=query, suggestion=suggestion))

            related = await client.get(
                f"{BASE_URL}/rxcui/{rxcui}/related.json", params={"tty": "SCD"}
            )
            related.raise_for_status()
            return _store(key, DrugFacts(
                query=query, rxcui=rxcui, max_strength_mg=_max_strength_mg(related.json()),
            ))
    except Exception as exc:
        # Fail OPEN — unreachable is not the same as invalid.
        logger.warning("RxNorm lookup failed for %r (%s: %s)",
                       query, type(exc).__name__, str(exc)[:120])
        return DrugFacts(query=query, reachable=False)
