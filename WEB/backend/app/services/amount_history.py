# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The amounts a patient has STATED for a food, proposed back for them to confirm.

TASKS 25. Operator, 2026-10-24: *"The Alafia model for food is to learn from
user input and let users verify the learned data"*, after *"Instead of assuming
portion let user determine. If no portion size exists — surface the error."*

An item logged with no amount is not counted. This module answers the next
question — "what does THIS patient usually have?" — from their own words, and
nothing is applied until they confirm it. Confirming writes the amount into the
meal's text, as theirs; the next proposal then counts it too. That is the whole
learning loop: no model, no shared table, no inference about what anyone eats.

**Only an amount the patient TYPED is history.** The parser reports the amount
text it read (`qty_text`); an amount is stated when that text appears verbatim
in the item's own phrase. That rule — not a list of system labels — excludes
everything the system ever filled in: the old 100 g placeholder ("default"), a
guessed "1 teaspoon" for a bracketed spice, a USDA portion description. Measured
on the reference record: 1,083 meals parse in 0.05 s and yield 971 stated
amounts across 314 foods.

**A bare count is not proposed and not accepted.** "2" for a smoothie names no
weight; the meal would still be uncounted and the patient told it worked. A
count with a food the record can weigh ("2 eggs") already resolves when typed
with the meal.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nutrition import NutritionLog

#: How many alternatives to offer per item. Three: the usual amount, and the
#: two others the patient has used most — enough to cover "half" and "double"
#: days without turning a confirmation into a list to read.
MAX_SUGGESTIONS = 3


class AmountNotUnderstood(ValueError):
    """The amount, placed before the item, does not parse as a measure."""

    def __init__(self, food_name: str, amount: str, reason: str, code: str):
        super().__init__(f"{food_name}: {reason}")
        # `code` is what clients translate; `reason` is the English sentence.
        self.food_name, self.amount, self.reason, self.code = food_name, amount, reason, code


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _is_measure(qty_text: str | None) -> bool:
    from app.services.nutrient_estimator import _weight_is_placeholder
    return bool(qty_text) and not _weight_is_placeholder(qty_text)


def stated_amounts(description: str) -> list[tuple[str, str]]:
    """(food_name, amount) for every item whose amount the patient typed."""
    from app.services.meal_parser import parse_meal_text
    try:
        comps = parse_meal_text(description or "")
    except Exception:  # noqa: BLE001 — one unparseable meal must not hide the rest
        return []
    out = []
    for c in comps:
        q = (c.qty_text or "").strip()
        if _is_measure(q) and _norm(q) in _norm(getattr(c, "source_text", "") or ""):
            out.append((_norm(c.food_name), q))
    return out


async def suggestions(db: AsyncSession, user_id: int, food_names: Iterable[str], *,
                      exclude_log_id: int | None = None) -> dict[str, list[dict]]:
    """For each food name, the amounts this patient has stated for it.

    Ordered by how often, then how recently. Spellings that differ only in case
    or spacing ("8 Fl oz" / "8 fl oz") are one amount, shown as most recently
    written. Keyed by the parser's food name, exactly — "smoothie" does not
    borrow "fruit smoothie"'s history, because a near name is a different food
    often enough that proposing it would be a guess.
    """
    wanted = {_norm(n) for n in food_names if n}
    if not wanted:
        return {}
    rows = (await db.execute(
        select(NutritionLog.id, NutritionLog.food_name, NutritionLog.log_date)
        .where(NutritionLog.user_id == user_id)
        .order_by(NutritionLog.log_date.desc(), NutritionLog.id.desc())
    )).all()
    seen: dict[str, dict[str, dict]] = defaultdict(dict)
    for log_id, text, day in rows:
        if log_id == exclude_log_id:
            continue
        for food, amount in stated_amounts(text):
            if food not in wanted:
                continue
            slot = seen[food].setdefault(_norm(amount), {"amount": amount, "times": 0,
                                                        "last_date": day})
            slot["times"] += 1   # rows are newest first: the first spelling seen is the latest
    out = {}
    for food in wanted:
        ranked = sorted(seen.get(food, {}).values(),
                        key=lambda s: (-s["times"], -(s["last_date"] or date.min).toordinal()))
        out[food] = [{**s, "last_date": s["last_date"].isoformat() if s["last_date"] else None}
                     for s in ranked[:MAX_SUGGESTIONS]]
    return out


#: The estimator's own label for an item it left out because no amount was
#: given (`nutrient_estimator`, "THE PATIENT DETERMINES THE AMOUNT").
NO_AMOUNT_SUFFIX = " (no amount given)"


def left_out_for_amount(nutrients_excluded: list | None) -> list[str]:
    """Food names the estimate excluded for want of an amount."""
    return [_norm(str(x)[: -len(NO_AMOUNT_SUFFIX)]) for x in (nutrients_excluded or [])
            if str(x).endswith(NO_AMOUNT_SUFFIX)]


def missing_amount_items(description: str) -> list[str]:
    """Food names in this meal that carry no measure — what to ask about."""
    from app.services.meal_parser import parse_meal_text
    try:
        comps = parse_meal_text(description or "")
    except Exception:  # noqa: BLE001
        return []
    return [_norm(c.food_name) for c in comps if not _is_measure(c.qty_text)]


def apply_amounts(description: str, amounts: dict[str, str]) -> str:
    """The meal text with each amount written before its item.

    The amount goes where the patient would have typed it — "Smoothie" becomes
    "350 ml Smoothie" — so the record reads as their statement and every later
    re-estimate parses the same thing. The item's own phrase can occur more than
    once ("pepper soup (pepper)"); each occurrence is tried and the first whose
    result parses with THAT item measured, and every other item unchanged, is
    kept. Anything else raises `AmountNotUnderstood` and nothing is written.
    """
    from app.services.meal_parser import parse_meal_text

    text = description
    for food, amount in amounts.items():
        food_key, amount = _norm(food), (amount or "").strip()
        if not amount:
            raise AmountNotUnderstood(food, amount, "no amount was entered", "empty")
        before = parse_meal_text(text)
        target = next((c for c in before if _norm(c.food_name) == food_key
                       and not _is_measure(c.qty_text)), None)
        if target is None:
            raise AmountNotUnderstood(food, amount, "this meal has no item of that name without an amount",
                                      "no_such_item")
        phrase = (target.source_text or target.food_name).strip()
        others = [(_norm(c.food_name), c.qty_text) for c in before if c is not target]
        accepted = None
        for m in re.finditer(re.escape(phrase), text):
            candidate = text[:m.start()] + f"{amount} {phrase}" + text[m.end():]
            after = parse_meal_text(candidate)
            hit = [c for c in after if _norm(c.food_name) == food_key and _is_measure(c.qty_text)]
            rest = [(_norm(c.food_name), c.qty_text) for c in after
                    if not (_norm(c.food_name) == food_key and _is_measure(c.qty_text))]
            if len(hit) == 1 and rest == others and _norm(amount) in _norm(hit[0].qty_text or "") + " " + _norm(hit[0].source_text or ""):
                accepted = candidate
                break
        if accepted is None:
            raise AmountNotUnderstood(
                food, amount, "that is not a weight or measure — try e.g. 200 g, 1 cup or 350 ml",
                "not_a_measure")
        text = accepted
    return text
