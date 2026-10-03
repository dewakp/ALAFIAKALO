# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

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


#: rxcui -> canonical RxNorm Name. A SEPARATE cache from `_cache`, which is
#: keyed by the typed NAME and holds DrugFacts. Sharing one dict would conflate
#: two key spaces that merely happen to both be strings.
_name_cache: dict[str, tuple[float, str | None]] = {}


async def canonical_name(rxcui: str) -> str | None:
    """RxNorm's own spelling for a concept, or None. Never raises.

    **Deliberately NOT folded into `lookup()`.** That function sits on the
    dose-log write path through `validate_dose`, and this is a third HTTP round
    trip — putting it there would slow a clinical save for every dose logged.
    Only the allergy-resolution path calls it, and that runs in a script or a
    background task.

    Why it is needed at all: a declared term can resolve EXACTLY and still be
    spelled differently from the drug. Measured 2026-10-03 — `Heparine` is a
    real RxNorm synonym (rxcui 5224) whose canonical name is `heparin`, so a
    profile declaring `Heparine` matched only itself and missed a dose logged
    as `Heparin`. That is the `Penicilin` failure pointing the other way.

    > ⚠️ **Comparing rxcuis is NOT a usable matching rule.** The two spellings
    > resolve to DIFFERENT concepts — `Heparine` is 5224 and `Heparin` is
    > 235473 — so equality would have reported them as unrelated drugs. The
    > canonical NAME is what relates them.

    Not every concept has one: rxcui 7986 (penicillin) returns no name property
    at all, so None is an ordinary answer rather than a failure.
    """
    key = str(rxcui or "").strip()
    if not key:
        return None
    hit = _name_cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{BASE_URL}/rxcui/{key}/property.json",
                                    params={"propName": "RxNorm Name"})
            resp.raise_for_status()
            props = ((resp.json().get("propConceptGroup") or {})
                     .get("propConcept")) or []
            name = next((p.get("propValue") for p in props if p.get("propValue")),
                        None)
    except Exception as exc:
        # Unreachable is not an answer, so it is NOT cached — ask again later
        # rather than remembering an outage as "this drug has no name".
        logger.warning("RxNorm canonical name failed for %s (%s: %s)",
                       key, type(exc).__name__, str(exc)[:120])
        return None
    _name_cache[key] = (time.time() + _CACHE_TTL, name)
    return name


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
