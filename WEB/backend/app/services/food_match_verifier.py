# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Which retrieved database record IS the food the patient named — or none.

Lexical matching cannot answer that, and the audit of 2026-10-22 measured how
badly it fails. Of 934 cached rows linked to a USDA/branded record, the model
judged **432 (46%) a different food** — and every one had passed the lexical
rule, because that rule only asks whether the TYPED words appear somewhere in
the description:

    sardines        -> "Fish oil, sardine"        902 kcal, 100 g fat, 0 protein
    milk            -> "Crackers, milk"           446 kcal
    water melon     -> "Honeydew melon, raw"
    cow liver       -> "Goose, liver, raw"
    paw paw         -> "PAW FAN WITH CANDY"       400 kcal, 100 g carbs
    egusi soup      -> "Soup, borscht"

No word rule fixes that: the best one tried caught half the wrong matches and
threw away a third of the right ones. What the name MEANS is language
understanding, which is the model's job (§3am); the database's job is the
numbers. So retrieval proposes candidates, the model chooses among them, and
the numbers still come from the record it chose — never from the model.

**Fails CLOSED.** An unverified match is not used: that is precisely the state
that cached sardine oil for four months. A failed verification raises
`Unavailable`; the lookup falls through to the next tier and does not CACHE
that tier's answer, so the next lookup asks again.
"""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar

logger = logging.getLogger(__name__)

_SYSTEM = """You match a food a patient named to records retrieved from a
food-composition database (USDA FoodData Central, branded products).

First decide what the name DENOTES: the species, plant part, animal, cut or
product people mean by it. Names are often regional or colloquial, so identify
the food as it is commonly eaten, not as the words read literally.

Then choose the ONE candidate that IS that food. Any ordinary form of it counts
(raw, cooked, canned, fresh). It is NOT a match when the record is:
- a different species, plant or animal, even a related one;
- an oil, flour, powder, juice or extract made FROM the food;
- a dish or snack that CONTAINS it, or a dish whose main ingredients differ;
- a dried or concentrated form when the name is the ordinary food;
- a variety or specialty when the name is generic — a generic name means its
  ordinary default form, not another animal's or a specialty version.

If the name is not a food (a quantity, an instruction, a fragment), or no
candidate is that food, answer null. A wrong match is worse than none: the
system will estimate the food another way.

Reply with JSON only:
{"denotes": "<what the name means, briefly>", "choice": <candidate number or null>,
 "reason": "<one short sentence>"}"""

_REWRITE = """Give the name a food-composition database (USDA FoodData Central)
would use for the food a patient named — the ordinary form people eat, in the
database's own wording, e.g. "<Food>, raw" or "<Food>, cooked" — and its
scientific (binomial) name when it is a plant or animal. Identify regional or
colloquial names first, as they are used where the patient lives. If it is not
a single food, answer null for both.

Reply with JSON only: {"query": "<database name>" or null, "scientific": "<Genus species>" or null}"""

#: Where the patient lives, set by the meal estimator for the duration of one
#: estimate. A food name means what it means THERE: "paw paw" is papaya in
#: Nigeria and Asimina triloba in Ohio; "bitter leaf" is Vernonia, not bitter
#: gourd. Without it the model guessed the US reading, confidently.
region: ContextVar[str | None] = ContextVar("food_region", default=None)
# ⚠️ The patient's usual foods were tried as context and REMOVED (2026-10-23).
# Measured on 18 known cases x 3 runs: country only 51/54, no context 51/54,
# country + the patient's 15 most-logged foods 42/54 — the history made the
# model accept DISHES loosely ("egusi soup" -> "Soup, peanut"). Residence is
# not cuisine (the record that eats ogbono lives in the USA), but this signal
# measured harmful; see OPEN_ITEMS §58f.


def _where() -> str:
    out = ""
    r = region.get()
    if r:
        out += f"\nThe patient lives in: {r}"
    return out


# One answer per (name, candidate set) for the life of the process. The result
# is cached in food_nutrient_cache anyway; this only stops a meal that names
# the same food twice from asking twice.
_memo: dict[tuple, int | None] = {}


class Unavailable(Exception):
    """The model could not give an answer. NOT the same as "no candidate is
    this food": a caller must not let a fallback's answer be cached as if the
    authority had nothing — that turns a provider outage into a permanent
    downgrade of the shared cache."""


def _fmt(n: dict) -> str:
    parts = []
    for k, label in (("calories", "kcal"), ("protein_g", "protein g"),
                     ("fat_g", "fat g"), ("carbs_g", "carbs g")):
        v = n.get(k)
        if isinstance(v, (int, float)):
            parts.append(f"{label} {round(float(v), 1)}")
    return ", ".join(parts) or "no figures"


async def standard_name(food_name: str) -> list[str]:
    """The database's own name for the food, for a second retrieval.

    Lexical retrieval misses what the patient's words do not spell: USDA's top
    five for "milk" hold no cow's milk, for "water melon" no watermelon, and
    "paw paw" returns nothing. Raises `Unavailable` when the model cannot answer.
    """
    from app.services.alafia_model_service import alafia_chat, ALAFIAModelError
    messages = [{"role": "system", "content": _REWRITE},
                {"role": "user", "content": f'Name: "{food_name}"' + _where()}]
    try:
        raw = await alafia_chat(messages, temperature=0.0, max_tokens=160, json_mode=True)
        body = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except (ALAFIAModelError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise Unavailable(type(exc).__name__) from exc
    out = []
    for q in (body.get("query"), body.get("scientific")):
        q = (q or "").strip() if isinstance(q, str) else ""
        if q and q.lower() != food_name.strip().lower() and q not in out:
            out.append(q)
    return out


async def choose(food_name: str, candidates: list[dict]) -> int | None:
    """Index into `candidates` of the record that IS `food_name`, or None.

    Raises `Unavailable` when the model gives no usable answer.

    Each candidate: {"description", "data_type"?, "category"?, "brand"?,
    "nutrients"?}. Order is the lexical ranking and carries no authority.
    """
    if not candidates:
        return None
    key = (region.get(), re.sub(r"\s+", " ", food_name.strip().lower()),
           tuple((c.get("description") or "").lower() for c in candidates))
    if key in _memo:
        return _memo[key]

    lines = []
    for i, c in enumerate(candidates, 1):
        meta = "; ".join(x for x in (c.get("data_type"), c.get("category"), c.get("brand")) if x)
        lines.append(f'{i}. "{c.get("description")}"' + (f" ({meta})" if meta else "")
                     + f" — per 100 g: {_fmt(c.get('nutrients') or {})}")
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f'Name: "{food_name}"' + _where() + "\nCandidates:\n" + "\n".join(lines)},
    ]

    from app.services.alafia_model_service import alafia_chat, ALAFIAModelError
    try:
        raw = await alafia_chat(messages, temperature=0.0, max_tokens=300, json_mode=True)
        body = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        pick = body.get("choice")
        idx = int(pick) - 1 if pick is not None else None
        if idx is not None and not 0 <= idx < len(candidates):
            raise ValueError(f"choice {pick} outside 1..{len(candidates)}")
    except (ALAFIAModelError, ValueError, TypeError, json.JSONDecodeError) as exc:
        # Not memoised: a provider outage must not pin "no match" for the process.
        logger.warning("Match verification unavailable for %r (%s) — candidate not used",
                       food_name, type(exc).__name__)
        raise Unavailable(type(exc).__name__) from exc

    logger.info("Match verification for %r: %s (%s)", food_name,
                "none" if idx is None else repr(candidates[idx].get("description")),
                (body.get("reason") or "")[:160])
    _memo[key] = idx
    return idx


_PORTION = """A patient described part of a meal. The food has been identified, and the
food-composition database lists the portions it is measured in, each with its
weight in grams. Decide which listed portion the patient's words describe and
how many of it.

- "<n> <units>" with a listed portion "1 <unit>" -> that portion, count n.
- A unit the list names differently but that means the same container or piece
  is the same portion.
- If the words give no amount at all, choose a portion ONLY if the list has one
  that is plainly the ordinary single serving of this food; otherwise null.
- If no listed portion fits the words, answer null. Do not guess a weight.

Reply with JSON only: {"portion": <portion number or null>, "count": <number>}"""


def per_unit_grams(portion: dict) -> float:
    """Grams for ONE of the units a USDA portion names (gramWeight / amount)."""
    amount = portion.get("amount")
    try:
        amount = float(amount) if amount not in (None, "", 0) else 1.0
    except (TypeError, ValueError):
        amount = 1.0
    return float(portion["gram_weight"]) / (amount if amount > 0 else 1.0)


async def choose_portion(text: str, food: str, portions: list[dict]) -> tuple[int, float] | None:
    """(index into `portions`, count) for the amount `text` describes, or None.

    Replaces the parser's 100 g placeholder for a unit it does not know
    ("2 sachets of brown sugar" was 100 g -> 380 kcal; two sachets are ~8 g).
    The weight comes from the database's own portion list; the model only reads
    which portion the words mean. Raises `Unavailable` when it cannot answer.
    """
    usable = [p for p in portions if isinstance(p.get("gram_weight"), (int, float)) and p["gram_weight"] > 0]
    if not usable:
        return None
    # Per ONE unit: USDA records some portions for several units at once —
    # 'slices (1/4" thick)' = 53 g for AMOUNT 10. Read as 53 g a slice, eight
    # slices of fried plantain became 424 g instead of 42 g (2026-10-23).
    lines = [f'{i}. 1 x "{p.get("description")}" = {round(per_unit_grams(p), 2)} g'
             for i, p in enumerate(usable, 1)]
    messages = [{"role": "system", "content": _PORTION},
                {"role": "user", "content": f'Patient wrote: "{text}"\nFood: "{food}"\nPortions:\n' + "\n".join(lines)}]
    from app.services.alafia_model_service import alafia_chat, ALAFIAModelError
    try:
        raw = await alafia_chat(messages, temperature=0.0, max_tokens=120, json_mode=True)
        body = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        pick, count = body.get("portion"), body.get("count", 1)
        if pick is None:
            return None
        idx = int(pick) - 1
        count = float(count)
        if not 0 <= idx < len(usable) or not 0 < count <= 50:
            raise ValueError(f"portion {pick} x {count} out of range")
    except (ALAFIAModelError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise Unavailable(type(exc).__name__) from exc
    chosen = usable[idx]
    return portions.index(chosen), count
