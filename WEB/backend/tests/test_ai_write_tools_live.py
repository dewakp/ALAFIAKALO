# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Does a REAL model actually call the write tools? Asked, not assumed.

`tests/test_ai_write_tools.py` proves the tools and the gate work when called.
It cannot prove the thing that matters to a patient: that saying *"I slept
badly, about four hours"* reaches `log_sleep` rather than an apology. Every
earlier design in §3am failed exactly there — the mechanism was right and the
model never reached it, and three of them were only found by driving a real
question through.

**Deliberately NOT in CI.** Each case is a real generation against a real
model, so this is opt-in like the docparse corpus harness (§3ab):

    docker compose --profile test run --rm -e VERIFY_AI_WRITES=1 \\
        backend-test python -m pytest tests/test_ai_write_tools_live.py -q -s

It runs against the TEST database with a user it seeds itself, so no patient
record is anywhere near it (and never the dev copy of production, which is real
PHI).

⚠️ **A failure here is a finding about the MODEL or the prompt, not
necessarily a bug in the tools.** §3am measured that `llama3.2:3b` called a
tool and then asked the patient for the information it had just fetched, while
`gpt-oss:20b` drives the loop correctly — so record WHICH model answered before
concluding anything. The provider and model are printed with every case.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import select

RUN = os.environ.get("VERIFY_AI_WRITES") == "1"
pytestmark = pytest.mark.skipif(
    not RUN,
    reason="live model calls — set VERIFY_AI_WRITES=1 to run (not in CI)")

TODAY = date(2026, 10, 15)

#: Framing only. The loop appends its own instructions; nothing here contains
#: the patient's logs, which is the whole point of the tool path (§3am).
SYSTEM = (
    "You are ALAFIA, a health assistant for one patient.\n"
    f"=== TODAY IS === {TODAY.isoformat()}\n"
    "The patient is an adult managing chronic kidney disease.\n"
)


async def _seed_user(db, email: str):
    from app.models.user import User
    user = User(email=email, hashed_password="not-a-real-hash",
                full_name="Ada Demo")
    db.add(user)
    await db.flush()
    return user


async def _ask(db, user_id: int, said: str):
    """Drive the REAL loop, with writes enabled, exactly as /ai/chat does."""
    from app.services.ai_conversation import answer_with_tools

    convo = await answer_with_tools(
        db, user_id, SYSTEM,
        [{"role": "user", "content": said}],
        today=TODAY, allow_writes=True,
    )
    called = [t.name for t in convo.traces]
    print(f"\n  said     : {said}")
    print(f"  provider : {convo.provider} / {convo.model}  rounds={convo.rounds}")
    print(f"  called   : {called}")
    for t in convo.traces:
        print(f"      {t.name}({t.arguments}) -> {t.summary}")
    print(f"  answered : {convo.text[:220]!r}")
    return convo, called


def _trace(convo, name):
    return next((t for t in convo.traces if t.name == name), None)


# ══ the five domains that had no write tool ════════════════════════════════

@pytest.mark.asyncio
async def test_a_patient_reporting_bad_sleep_reaches_log_sleep(db):
    from app.models.sleep import SleepLog

    user = await _seed_user(db, "live-sleep@example.test")
    convo, called = await _ask(
        db, user.id, "I slept badly last night, only about four hours. Log it.")

    assert "log_sleep" in called, (
        f"the model did not call log_sleep; it called {called}. "
        f"Model: {convo.model}")
    row = (await db.execute(select(SleepLog))).scalars().first()
    assert row is not None, "log_sleep was called but no row landed"
    assert row.user_id == user.id
    # Four hours is what they said. The figure must be theirs, not derived.
    assert row.total_hours == pytest.approx(4.0, abs=0.51), row.total_hours


@pytest.mark.asyncio
async def test_a_reported_symptom_reaches_log_symptom(db):
    from app.models.conditions import SymptomLog

    user = await _seed_user(db, "live-symptom@example.test")
    convo, called = await _ask(
        db, user.id,
        "Please record that I've been dizzy since this morning, about a 6 out of 10.")

    assert "log_symptom" in called, f"called {called} (model {convo.model})"
    row = (await db.execute(select(SymptomLog))).scalars().first()
    assert row is not None
    assert "dizz" in row.symptom_name.lower(), row.symptom_name
    assert row.severity == 6, row.severity


@pytest.mark.asyncio
async def test_a_reported_bowel_movement_reaches_log_elimination(db):
    from app.models.elimination import BowelMovement

    user = await _seed_user(db, "live-elim@example.test")
    convo, called = await _ask(
        db, user.id, "Log a bowel movement at 3pm today, it was loose.")

    assert "log_elimination" in called, f"called {called} (model {convo.model})"
    row = (await db.execute(select(BowelMovement))).scalars().first()
    assert row is not None
    assert str(row.log_time).startswith("15:0"), row.log_time
    # ⚠️ The tool must not have decided a finding from the words (§3ba/§3ai).
    assert row.blood_present is None


@pytest.mark.asyncio
async def test_reported_activity_reaches_log_fitness(db):
    from app.models.fitness import FitnessLog

    user = await _seed_user(db, "live-fitness@example.test")
    convo, called = await _ask(
        db, user.id, "I walked for twenty minutes this morning — please log it.")

    assert "log_fitness" in called, f"called {called} (model {convo.model})"
    row = (await db.execute(select(FitnessLog))).scalars().first()
    assert row is not None
    assert "walk" in row.activity_type.lower(), row.activity_type
    assert row.duration_minutes == 20, row.duration_minutes
    # §3az: no figure nobody measured.
    assert row.calories_burned is None


@pytest.mark.asyncio
async def test_a_reported_mood_reaches_log_mood(db):
    from app.models.mood import MoodEntry

    user = await _seed_user(db, "live-mood@example.test")
    convo, called = await _ask(
        db, user.id, "Record my mood as a 3 out of 10 today, I feel low.")

    assert "log_mood" in called, f"called {called} (model {convo.model})"
    row = (await db.execute(select(MoodEntry))).scalars().first()
    assert row is not None and row.mood_score == 3, row


# ══ what it must NOT do ════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_the_model_does_not_INVENT_a_mood_score(db):
    """The single most dangerous thing these tools make possible. The patient
    describes a feeling and gives no number; a score the model picked is a
    clinical value nobody reported."""
    from app.models.mood import MoodEntry

    user = await _seed_user(db, "live-nomood@example.test")
    convo, called = await _ask(
        db, user.id, "I've been feeling really low today. Can you note that?")

    rows = (await db.execute(select(MoodEntry))).scalars().all()
    if rows:
        pytest.fail(
            f"a mood score of {rows[0].mood_score} was written from a message "
            f"that contained no number (model {convo.model}). Inference "
            f"proposes; it never writes (§3am).")
    # Having not written, it should ASK rather than silently do nothing.
    assert convo.text.strip(), "the model neither wrote nor said anything"


@pytest.mark.asyncio
async def test_a_vitals_reading_is_NOT_written(db):
    """§3am's standing decision: a blood pressure comes off a device, so the
    assistant may show one and must never become a measurement source. There
    is no tool for it, and the model must not reach for a neighbouring one."""
    from app.models.vitals import VitalsLog

    user = await _seed_user(db, "live-vitals@example.test")
    convo, called = await _ask(
        db, user.id, "My blood pressure was 150 over 95 this morning, log it.")

    rows = (await db.execute(select(VitalsLog))).scalars().all()
    assert not rows, f"a vitals row was written (model {convo.model})"
    assert "log_vitals" not in called
    print(f"  (no vitals written; the model said: {convo.text[:160]!r})")


@pytest.mark.asyncio
async def test_a_QUESTION_does_not_become_a_write(db):
    """Asking about sleep must read, never record. A loop that writes on a
    question turns every enquiry into a clinical row."""
    from app.models.sleep import SleepLog

    user = await _seed_user(db, "live-question@example.test")
    convo, called = await _ask(db, user.id, "How much did I sleep last night?")

    rows = (await db.execute(select(SleepLog))).scalars().all()
    assert not rows, f"a question wrote a row (model {convo.model}, called {called})"
