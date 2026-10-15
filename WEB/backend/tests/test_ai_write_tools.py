# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The assistant's write tools, and the gate that decides whether they run.

Operator, 2026-10-14: *"a gated, secure set of write tools."*

Five domains had none at all — elimination, mood, sleep, symptoms, fitness —
so a patient who said "log that I slept badly" got an apology while the label
on the surface had just been changed to invite exactly that.

⚠️ **The gate mattered more than the tools.** `WRITE_TOOLS` existed for weeks
declaring which calls may alter a patient's chart, and **nothing read it**:
`run_tool` dispatched `log_meal` for any caller that named it. That is §3ay's
never-plugged-in sink on the most consequential switch in the module. Adding
five more writers behind an unwired gate would have multiplied it by five.
"""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.services import record_tools as rt

TODAY = date(2026, 10, 14)


async def _seed_user(db, email: str):
    from app.models.user import User
    user = User(email=email, hashed_password="not-a-real-hash",
                full_name="Ada Demo")
    db.add(user)
    await db.flush()
    return user


async def _count(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# ══ the gate ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_a_write_is_REFUSED_unless_the_caller_asked_for_writes(db):
    """The gate fails CLOSED. A caller that does not opt in gets a read-only
    assistant — so forgetting the flag makes the product less capable, never
    silently able to alter a chart (§3at: which way a default fails)."""
    user = await _seed_user(db, "gate-closed@example.test")
    from app.models.mood import MoodEntry

    out = await rt.run_tool(db, user.id, "log_mood",
                            {"mood_score": 7}, TODAY)      # no allow_writes
    assert out.get("refused") is True
    assert "cannot write" in out["error"]
    assert await _count(db, MoodEntry) == 0, "a refused write must write nothing"


@pytest.mark.asyncio
async def test_the_refusal_is_SAID_not_swallowed(db):
    """§3am: an error must never become an answer. The model has to be able to
    tell the patient nothing was saved, rather than replying as if it had."""
    user = await _seed_user(db, "gate-says@example.test")
    out = await rt.run_tool(db, user.id, "log_symptom",
                            {"symptom": "dizzy"}, TODAY)
    assert "Nothing was written" in out["tell_the_patient"] \
        or "Nothing was written." in out["tell_the_patient"] \
        or "nothing" in out["tell_the_patient"].lower()


@pytest.mark.asyncio
async def test_a_READ_tool_is_never_gated(db):
    """The asymmetry is the point: reading a record is what the assistant is
    for, and gating it would break every question to protect nothing."""
    user = await _seed_user(db, "gate-read@example.test")
    out = await rt.run_tool(db, user.id, "get_meals", {}, TODAY)
    assert out.get("refused") is not True


@pytest.mark.asyncio
async def test_the_gate_covers_EVERY_declared_write_tool(db):
    """Not just the two that existed when it was wired."""
    user = await _seed_user(db, "gate-all@example.test")
    for name in sorted(rt.WRITE_TOOLS):
        out = await rt.run_tool(db, user.id, name, {}, TODAY)
        assert out.get("refused") is True, f"{name} was not gated"


def test_vitals_and_labs_are_declared_UNWRITABLE_with_a_reason():
    """§3am decided this and the decision must stay visible: a vitals reading
    comes off a device and a lab result comes from a laboratory, so writing
    either here would make the assistant a measurement source."""
    assert rt.NEVER_WRITABLE == {"vitals", "labs"}
    assert not {"log_vitals", "log_labs", "log_lab"} & set(rt.TOOLS)


def test_every_write_tool_is_declared_in_WRITE_TOOLS():
    """A `log_*` function that is not in the set would run ungated."""
    writers = {n for n in rt.TOOLS if n.startswith("log_")}
    assert writers == set(rt.WRITE_TOOLS), (
        f"ungated writers: {sorted(writers - set(rt.WRITE_TOOLS))}")


def test_every_tool_carries_a_spec_and_a_label():
    """A tool with no spec is unreachable by the model; one with no label
    shows a generic status chip the backend is supposed to own (§3am)."""
    named = {t["name"] for t in rt.TOOL_SPECS}
    assert set(rt.TOOLS) == named
    assert set(rt.TOOLS) <= set(rt.TOOL_LABELS)


# ══ the contract ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_a_scale_outside_its_range_is_REFUSED_never_clamped(db):
    """§3am: a bad argument that becomes a wrong clinical number is worse than
    an error. Clamping 50 to 10 records a severity nobody stated."""
    user = await _seed_user(db, "scale@example.test")
    from app.models.conditions import SymptomLog

    out = await rt.log_symptom(db, user.id, symptom="headache", severity=50,
                               today=TODAY)
    assert out.get("refused") is True
    assert any("1-10" in p for p in out["problems"])
    assert await _count(db, SymptomLog) == 0


@pytest.mark.asyncio
async def test_an_unreadable_TIME_is_refused_not_dropped(db):
    """§3av: the web flowsheet silently discarded a reading whose time would
    not parse. A value that cannot be read is refused by name."""
    user = await _seed_user(db, "clock@example.test")
    out = await rt.log_elimination(db, user.id, description="loose",
                                   time="half past something", today=TODAY)
    assert out.get("refused") is True
    assert any("not a time" in p for p in out["problems"])


@pytest.mark.asyncio
async def test_text_longer_than_the_column_is_refused_not_TRUNCATED(db):
    """A clinical sentence stored with its end cut off reads as a complete
    statement."""
    user = await _seed_user(db, "long@example.test")
    out = await rt.log_symptom(db, user.id, symptom="x" * 400, today=TODAY)
    assert out.get("refused") is True
    assert any("characters" in p for p in out["problems"])


@pytest.mark.asyncio
async def test_a_tool_cannot_be_talked_into_setting_an_UNDECLARED_column(db):
    """The contract: only columns the spec names are ever written. An argument
    the model invents is ignored rather than reaching the model object."""
    user = await _seed_user(db, "contract@example.test")
    out = await rt.run_tool(
        db, user.id, "log_mood",
        {"mood_score": 6, "gratitude": "SHOULD NOT BE WRITTEN",
         "user_id": 999999},
        TODAY, allow_writes=True)
    # Unknown kwargs are a TypeError the dispatcher reports, which is the safe
    # direction — nothing is written and the model is told.
    if out.get("logged"):
        from app.models.mood import MoodEntry
        row = (await db.execute(select(MoodEntry))).scalars().first()
        assert row.gratitude is None
        assert row.user_id == user.id
    else:
        assert "bad arguments" in out.get("error", "")


# ══ the writes themselves ══════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mood_needs_a_score_the_PATIENT_gave(db):
    """Inference proposes; it never writes (§3am). 'They sound low, call it 3'
    would be the assistant entering a clinical score nobody stated."""
    user = await _seed_user(db, "mood-ask@example.test")
    out = await rt.log_mood(db, user.id, note="rough day", today=TODAY)
    assert "no mood score" in out["error"]
    assert "ask_the_patient" in out


@pytest.mark.asyncio
async def test_mood_is_written_with_the_PATIENTS_date(db):
    """§3am: the containers run UTC, so the server's date is already tomorrow
    for a patient in the Americas from early evening."""
    user = await _seed_user(db, "mood-ok@example.test")
    from app.models.mood import MoodEntry

    out = await rt.log_mood(db, user.id, mood_score=4, energy_level=2,
                            note="tired", today=TODAY)
    assert out["logged"] is True
    row = (await db.execute(select(MoodEntry))).scalars().one()
    assert row.entry_date == TODAY           # NOT date.today()
    assert row.mood_score == 4 and row.energy_level == 2
    assert row.journal_entry == "tired"


@pytest.mark.asyncio
async def test_elimination_stores_the_WORDS_and_derives_no_finding(db):
    """⚠️ The one that is easy to get wrong. `blood_present` stays NULL even
    when the patient says "bloody": `elimination_text` already reads those
    words for every consumer, and §3ba's rule is that a SET column wins while
    only NULL falls through to the text. Writing the boolean too would put a
    second interpreter beside the first (§3ai)."""
    user = await _seed_user(db, "elim@example.test")
    from app.models.elimination import BowelMovement

    out = await rt.log_elimination(db, user.id, kind="bowel",
                                   description="very bloody, painful",
                                   time="3 pm", today=TODAY)
    assert out["logged"] is True
    row = (await db.execute(select(BowelMovement))).scalars().one()
    assert row.notes == "very bloody, painful"
    assert row.blood_present is None, (
        "the tool must not decide a clinical finding from the words; "
        "elimination_text is the one reader that interprets them")
    assert str(row.log_time) == "15:00:00"


@pytest.mark.asyncio
async def test_sleep_does_not_COMPUTE_hours_from_the_two_clocks(db):
    """§3av: a night crossing midnight is exactly where every client rolled
    over for DISPLAY and none for STORAGE, and four production sessions stored
    a negative duration. Nothing derives one from the other here."""
    user = await _seed_user(db, "sleep@example.test")
    from app.models.sleep import SleepLog

    out = await rt.log_sleep(db, user.id, bedtime="11 pm", wake_time="6:30 am",
                             today=TODAY)
    assert out["logged"] is True
    row = (await db.execute(select(SleepLog))).scalars().one()
    assert str(row.bedtime) == "23:00:00"
    assert str(row.wake_time) == "06:30:00"
    assert row.total_hours is None, "an uncomputed figure must stay absent"


@pytest.mark.asyncio
async def test_a_symptom_is_stored_WHOLE(db):
    """§3am: splitting on a vocabulary of symptom words invented two symptoms
    from one sentence."""
    user = await _seed_user(db, "symptom@example.test")
    from app.models.conditions import SymptomLog

    sentence = "I feel dizzy when I stand up, weak in the mornings"
    await rt.log_symptom(db, user.id, symptom=sentence, severity=6,
                         body_part="head", today=TODAY)
    row = (await db.execute(select(SymptomLog))).scalars().one()
    assert row.symptom_name == sentence
    assert row.severity == 6


@pytest.mark.asyncio
async def test_fitness_derives_no_calories(db):
    """§3az: a figure with no authority must not be presented as the patient's
    own. Calories need weight, heart rate and a formula nobody here cited."""
    user = await _seed_user(db, "fitness@example.test")
    from app.models.fitness import FitnessLog

    await rt.log_fitness(db, user.id, activity="walking",
                         duration_minutes=20, today=TODAY)
    row = (await db.execute(select(FitnessLog))).scalars().one()
    assert row.activity_type == "walking" and row.duration_minutes == 20
    assert row.calories_burned is None


# ══ idempotence ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_a_repeat_call_does_not_double_write(db):
    """A tool loop retries — a provider hiccup, a round that re-reads the
    request — and a duplicated clinical row is indistinguishable from a second
    real event."""
    user = await _seed_user(db, "idem@example.test")
    from app.models.conditions import SymptomLog

    first = await rt.log_symptom(db, user.id, symptom="nausea", today=TODAY)
    again = await rt.log_symptom(db, user.id, symptom="nausea", today=TODAY)
    assert first["logged"] is True
    assert again.get("already_logged") is True
    assert again["id"] == first["id"]
    assert await _count(db, SymptomLog) == 1


@pytest.mark.asyncio
async def test_a_DIFFERENT_event_on_the_same_day_is_not_a_duplicate(db):
    """Two bowel movements in one day are two events. Over-matching would
    discard a real one."""
    user = await _seed_user(db, "idem2@example.test")
    from app.models.elimination import BowelMovement

    await rt.log_elimination(db, user.id, description="first", time="00:40",
                             today=TODAY)
    await rt.log_elimination(db, user.id, description="second", time="10:30",
                             today=TODAY)
    assert await _count(db, BowelMovement) == 2


# ══ scope ══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_every_write_is_scoped_to_the_signed_in_patient(db):
    """`user_id` comes from the session, never from the model."""
    a = await _seed_user(db, "scope-a@example.test")
    b = await _seed_user(db, "scope-b@example.test")
    from app.models.conditions import SymptomLog

    await rt.log_symptom(db, a.id, symptom="itching", today=TODAY)
    rows = (await db.execute(select(SymptomLog))).scalars().all()
    assert [r.user_id for r in rows] == [a.id]
    assert b.id not in [r.user_id for r in rows]


# ══ the loop must TELL the model these exist ═══════════════════════════════

def test_the_instructions_name_every_write_tool():
    """A tool the model is never told about is a tool it never calls — the
    §3ar shape one level up, where the capability exists and nothing surfaces
    it. That is exactly how this feature arrived: five domains had write tools
    in nobody's reach because they had none at all."""
    from app.services.ai_conversation import _TOOL_LOOP_INSTRUCTIONS as I

    for name in ("log_meal", "log_medication"):
        assert name in I, f"{name} is not named in the loop instructions"
    # The five new domains are described by what the patient SAYS, not by tool
    # name, because that is what the model matches against.
    for word in ("Elimination", "mood", "sleep", "symptom", "activity"):
        assert word.lower() in I.lower(), f"{word} is not mentioned"


def test_the_instructions_forbid_choosing_a_number_for_the_patient():
    """The single most dangerous thing these tools make possible."""
    from app.services.ai_conversation import _TOOL_LOOP_INSTRUCTIONS as I

    assert "NEVER choose a number for them" in I


def test_the_instructions_still_say_vitals_and_labs_are_read_only():
    from app.services.ai_conversation import _TOOL_LOOP_INSTRUCTIONS as I

    assert "READ-ONLY" in I.upper()


def test_the_instructions_say_what_to_do_with_a_refusal():
    """§3am: an error must never become an answer."""
    from app.services.ai_conversation import _TOOL_LOOP_INSTRUCTIONS as I

    assert "refused" in I and "NOTHING was saved" in I


# ══ the gate must be OPEN where the patient is, and only there ═════════════

def test_the_patients_own_chat_opts_INTO_writes_on_BOTH_paths():
    """The gate fails closed, so these two lines are what make "log my meal"
    work at all. Drop one and writes keep working on whichever path you
    happened to test — §3am's "wire the endpoint the product uses": the loop
    went into `/ai/chat` first and the STREAM, which every client actually
    uses, kept the old behaviour for a while.

    Checked with the AST rather than a grep: a string search would match the
    comment that explains the flag, which is the mistake two guards in this
    codebase have already made (§3av — a scan is evidence only once it is
    shown to see what it claims to).
    """
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "app" / "api" / "ai.py"
    tree = ast.parse(src.read_text())

    opened = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = getattr(fn, "id", None) or getattr(fn, "attr", None)
        if name not in ("answer_with_tools", "stream_with_tools"):
            continue
        flag = next((k for k in node.keywords if k.arg == "allow_writes"), None)
        opened[name] = bool(flag and getattr(flag.value, "value", False) is True)

    assert opened.get("answer_with_tools") is True, (
        "the buffered chat path no longer enables writes — `log_meal` would "
        "be refused for every patient")
    assert opened.get("stream_with_tools") is True, (
        "the STREAMING path no longer enables writes — and that is the path "
        "web, iOS and Android all use")


def test_nothing_else_in_the_app_turns_writes_on():
    """A capability granted in one place is auditable; granted in five it is
    not. If another caller legitimately needs writes, add it here with its
    reason — the same shape as `test_clinical_sources`'s ALLOWED set."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    allowed = {"api/ai.py"}        # the patient's own conversation
    found = set()
    for path in root.rglob("*.py"):
        if "allow_writes=True" in path.read_text():
            found.add(str(path.relative_to(root)))
    assert found == allowed, f"writes are enabled somewhere unreviewed: {found - allowed}"
