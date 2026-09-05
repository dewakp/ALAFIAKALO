"""The chat context must let the model answer the question it is asked.

A patient asked "what food contributed the most to my sugar intake today?" and
was told *"I don't have a nutrition log entry dated today in your record"* —
while that morning's breakfast sat in the log at 23 g of sugar, over their 19 g
limit. The model then listed foods from other days as what "typically"
contributed sugar, none of which were that day's meal.

Two separate gaps produced that, and either alone is enough to break it:

1. **The context never said what day it was.** `date.today()` appeared only in
   query cutoffs. Every dated row was absolute and nothing anchored them, so
   "today", "yesterday" and "this week" were unresolvable.

2. **The meal lines carried only calories and the three macros.** Sugar,
   sodium, potassium and phosphorus — the nutrients this app exists to manage,
   and the ones DAILY NUTRIENT TARGETS sets limits for — were absent. Asked for
   a sugar figure, the model had none to cite and produced one from memory.

The second is the more dangerous: an answer invented from remembered meals
reads exactly like an answer computed from the record.
"""

from datetime import date

import pytest

from app.api.ai import _fetch_patient_context
from app.models.nutrition import NutritionLog
from app.models.user import User


async def _context_for(db) -> str:
    """Seed a patient WITH a meal logged today, then build their context.

    Seeded rather than looked up: the first version of this file skipped when
    no user id 1 existed, so all six tests passed by not running. A suite that
    cannot reach the thing it tests is not evidence.
    """
    user = User(email="ctx-probe@alafia.app", hashed_password="x",
                full_name="Context Probe")
    db.add(user)
    await db.flush()

    # Today's meal, carrying every nutrient the question could be about.
    db.add(NutritionLog(
        user_id=user.id, log_date=date.today(), meal_type="breakfast",
        food_name="Rice, beef, onions, fried plantain, cherry tomatoes",
        calories=489.0, protein_g=26.0, carbs_g=56.0, fat_g=19.0,
        sugar_g=23.0, sodium_mg=706.0, potassium_mg=840.0, phosphorus_mg=262.0,
        nutrient_status="done",
    ))
    await db.flush()
    return await _fetch_patient_context(user, db)


def _section(ctx: str, header_prefix: str) -> str:
    """The BODY of a section, not the tail of its header line.

    The header is "=== NUTRITION LOGS (last 14 days) ===", so a naive
    split on "===" returns " (last 14 days) " and every assertion below it
    passes or fails for the wrong reason.
    """
    out, on = [], False
    for line in ctx.splitlines():
        if line.startswith(header_prefix):
            on = True
            continue
        if on and line.startswith("==="):
            break
        if on:
            out.append(line)
    return "\n".join(out)


# ── 1. the model must know what day it is ──────────────────────────────


@pytest.mark.asyncio
async def test_context_states_todays_date(db):
    ctx = await _context_for(db)
    assert str(date.today()) in ctx, (
        "the context never states today's date, so no relative-time question "
        "('today', 'yesterday', 'this week') can be answered")


@pytest.mark.asyncio
async def test_the_date_anchor_is_near_the_top(db):
    """After 200 lines of clinical detail it is far less likely to be used."""
    ctx = await _context_for(db)
    head = "\n".join(ctx.splitlines()[:12])
    assert "TODAY IS" in head


@pytest.mark.asyncio
async def test_context_tells_the_model_not_to_substitute_another_day(db):
    """The failure was not only "I don't know" — it then answered from other
    days and called it typical."""
    ctx = await _context_for(db)
    lowered = ctx.lower()
    assert "do not" in lowered or "do NOT" in ctx
    assert "typically" in lowered


# ── 2. the nutrients the app is about must be in the log lines ─────────


@pytest.mark.asyncio
async def test_meal_lines_carry_sugar(db):
    """The question was about sugar. Calories, protein, carbs and fat cannot
    answer it."""
    ctx = await _context_for(db)
    assert "=== NUTRITION LOGS" in ctx, "the seeded meal did not reach the context"
    section = _section(ctx, "=== NUTRITION LOGS")
    assert "sugar:" in section, "meal lines omit sugar"


@pytest.mark.asyncio
async def test_meal_lines_carry_the_renal_nutrients(db):
    """Sodium, potassium and phosphorus are the ones DAILY NUTRIENT TARGETS
    caps for a renal patient — a question about any of them had the same gap."""
    ctx = await _context_for(db)
    assert "=== NUTRITION LOGS" in ctx, "the seeded meal did not reach the context"
    section = _section(ctx, "=== NUTRITION LOGS")
    for marker in ("Na:", "K:", "PO4:"):
        assert marker in section, f"meal lines omit {marker}"


@pytest.mark.asyncio
async def test_meal_lines_are_not_malformed(db):
    """Guards the formatting: an empty label produced ':290 kcal'."""
    ctx = await _context_for(db)
    assert "=== NUTRITION LOGS" in ctx, "the seeded meal did not reach the context"
    section = _section(ctx, "=== NUTRITION LOGS")
    assert "— :" not in section and " :" not in section.replace(" : ", "")
