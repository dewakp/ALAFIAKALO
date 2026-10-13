# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Which screens a patient's record justifies.

Operator, 2026-10-12, having asked before:

  *"Primary goal == patient specific surfacing. for example someone who has
  listed no condition need not see therapies. they still do despite my repeated
  request. HD patient need not see PD in navigation."*

The web sidebar was a static 62-entry list, so every account saw HD Flowsheet,
PD Report and Therapy History whatever their record held. Measured on
production 2026-10-12: **2,035 therapy sessions, every one `HEMODIALYSIS`,
belonging to one user; zero peritoneal sessions exist for any account** — so
"PD Report" had never been a live screen for anybody, and it sat one row under
the screen the one dialysis patient actually uses.

Seeds its own users. Never reads a real record (dev holds real PHI).
"""

from datetime import datetime

import pytest

from app.models.chronic_conditions import (TherapySession, TherapyStatus,
                                           TherapyType)
from app.models.user import User
from app.services import patient_surfaces


async def _seed_user(db, email: str) -> User:
    user = User(email=email, hashed_password="not-a-real-hash",
                full_name="Ada Demo")
    db.add(user)
    await db.flush()
    return user


async def _seed_session(db, user, therapy_type: TherapyType) -> None:
    db.add(TherapySession(
        user_id=user.id, therapy_type=therapy_type,
        therapy_name="seeded", status=TherapyStatus.COMPLETED,
        scheduled_date=datetime(2026, 10, 1, 9, 0)))
    await db.flush()


@pytest.mark.asyncio
async def test_a_patient_with_no_therapy_sees_no_therapies(db):
    """The operator's first example. An account with nothing on record must not
    be offered a dialysis flowsheet."""
    user = await _seed_user(db, "no-conditions@example.test")
    s = await patient_surfaces.for_user(db, user.id)
    assert "therapies" not in s.offered
    assert "hemodialysis" not in s.offered
    assert "peritoneal_dialysis" not in s.offered
    assert "therapy_history" not in s.offered


@pytest.mark.asyncio
async def test_an_HD_patient_is_not_offered_PD(db):
    """The operator's second example, and the one with production behind it:
    zero peritoneal sessions exist anywhere, so that entry was dead for every
    user while sitting beside the screen the HD patient uses daily."""
    user = await _seed_user(db, "hd@example.test")
    await _seed_session(db, user, TherapyType.HEMODIALYSIS)
    s = await patient_surfaces.for_user(db, user.id)
    assert "hemodialysis" in s.offered
    assert "peritoneal_dialysis" not in s.offered
    assert "therapies" in s.offered
    assert "session" in s.because["hemodialysis"]


@pytest.mark.asyncio
async def test_a_PD_patient_is_not_offered_HD(db):
    """Symmetry matters: the rule must be about the record, not a preference
    for the modality that happens to be commoner here."""
    user = await _seed_user(db, "pd@example.test")
    await _seed_session(db, user, TherapyType.PERITONEAL_DIALYSIS)
    s = await patient_surfaces.for_user(db, user.id)
    assert "peritoneal_dialysis" in s.offered
    assert "hemodialysis" not in s.offered


@pytest.mark.asyncio
async def test_a_therapy_the_map_does_not_name_is_never_DROPPED(db):
    """Chemotherapy, infusion, phototherapy are real therapies. A modality
    missing from `_MODALITY_SURFACE` must still open the Therapies group —
    silently discarding it would hide a cancer patient's own sessions."""
    user = await _seed_user(db, "chemo@example.test")
    await _seed_session(db, user, TherapyType.CHEMOTHERAPY)
    s = await patient_surfaces.for_user(db, user.id)
    assert "therapies" in s.offered
    assert "therapy_history" in s.offered
    assert "therapy_other" in s.offered
    assert "hemodialysis" not in s.offered


@pytest.mark.asyncio
async def test_core_surfaces_are_never_gated(db):
    """You cannot hide the screen where a condition would be ADDED, or a new
    account has nowhere to begin."""
    user = await _seed_user(db, "empty@example.test")
    s = await patient_surfaces.for_user(db, user.id)
    for name in ("dashboard", "conditions", "labs", "medications", "profile"):
        assert name in s.offered


@pytest.mark.asyncio
async def test_every_offered_surface_says_WHY(db):
    """The reason travels so a client can explain itself and the decision is
    auditable rather than mysterious."""
    user = await _seed_user(db, "why@example.test")
    await _seed_session(db, user, TherapyType.HEMODIALYSIS)
    s = await patient_surfaces.for_user(db, user.id)
    assert s.offered and set(s.offered) == set(s.because)
    payload = s.as_payload()
    assert payload["offered"] == sorted(s.offered)


@pytest.mark.asyncio
async def test_DATA_beats_the_absence_of_a_diagnosis(db):
    """The rule that keeps this safe. A patient whose conditions were never
    coded still has their own sessions, and hiding the screen would hide their
    history from them — §3aa, absence of a diagnosis is not absence of records.
    """
    user = await _seed_user(db, "uncoded@example.test")
    await _seed_session(db, user, TherapyType.HEMODIALYSIS)
    s = await patient_surfaces.for_user(db, user.id)
    assert "conditions_active" not in s.offered     # nothing diagnosed
    assert "hemodialysis" in s.offered              # …and the screen still shows
    assert "session" in s.because["hemodialysis"], (
        "the reason must cite the DATA, not a diagnosis that does not exist")


# ── A DECLARED therapy, not a guessed one ───────────────────────────────────
#
# Operator, 2026-10-13: *"Only PD patients must see PD. Let user add Therapy
# types in Condition and profile. Same as other health conditions. use condition
# to determine the Therapy switch."*

from app.models.chronic_conditions import (                     # noqa: E402
    ChronicCondition, ConditionCategory, ConditionSeverity,
)
from app.services.patient_surfaces import (                     # noqa: E402
    declared_therapy_types, validate_therapy_types,
)


async def _seed_condition(db, user, name: str, therapy_types: str | None,
                          category=ConditionCategory.RENAL):
    # `category` AND `severity` are both NOT NULL on this table. Omitting
    # either raised NotNullViolationError, which then poisoned the session for
    # every later assertion in the same test — each omission only revealed the
    # next, one run at a time.
    db.add(ChronicCondition(user_id=user.id, condition_name=name,
                            category=category,
                            severity=ConditionSeverity.MODERATE,
                            is_active=True, therapy_types=therapy_types))
    await db.flush()


@pytest.mark.asyncio
async def test_a_declared_PD_opens_PD_before_any_session_exists(db):
    """The patient starting peritoneal dialysis next week needs the screen NOW,
    and the record holds no session yet — which is exactly when session-derived
    surfacing offers them nothing."""
    user = await _seed_user(db, "declared-pd@example.test")
    await _seed_condition(db, user, "End-Stage Renal Disease", "peritoneal_dialysis")
    s = await patient_surfaces.for_user(db, user.id)
    assert "peritoneal_dialysis" in s.offered
    assert "hemodialysis" not in s.offered, "declaring PD must not open HD"
    assert "therapies" in s.offered
    assert "declared therapy" in s.because["peritoneal_dialysis"]


@pytest.mark.asyncio
async def test_only_PD_patients_see_PD(db):
    """The instruction, stated as a test. An HD patient — declared OR with
    sessions — is never offered the peritoneal screen."""
    hd = await _seed_user(db, "declared-hd@example.test")
    await _seed_condition(db, hd, "ESRD", "hemodialysis")
    s = await patient_surfaces.for_user(db, hd.id)
    assert "hemodialysis" in s.offered
    assert "peritoneal_dialysis" not in s.offered


@pytest.mark.asyncio
async def test_a_condition_with_NO_declared_therapy_opens_nothing(db):
    """⚠️ This is the behaviour change. A hand-typed keyword dict used to match
    `("hemodialysis", "haemodialysis", "end-stage renal", "esrd", "dialysis")`
    against the condition's WORDING, so "End-Stage Renal Disease" silently
    opened the HD flowsheet and "ESKD" opened nothing — §3an's forbidden shape
    deciding which clinical screen a patient could reach.

    A condition that declares no therapy now offers no therapy screen. The
    patient says what they are on; the app does not guess from a name.
    """
    user = await _seed_user(db, "no-declared@example.test")
    await _seed_condition(db, user, "End-Stage Renal Disease (ESRD)", None)
    s = await patient_surfaces.for_user(db, user.id)
    assert "hemodialysis" not in s.offered
    assert "peritoneal_dialysis" not in s.offered
    assert "therapies" not in s.offered


@pytest.mark.asyncio
async def test_sessions_still_win_when_nothing_was_declared(db):
    """Data beats a missing declaration, the same way it beats a missing
    diagnosis (§3aa). A patient with 2,035 HD sessions and no `therapy_types`
    must keep the screen holding their own history."""
    user = await _seed_user(db, "sessions-only@example.test")
    await _seed_condition(db, user, "ESRD", None)
    await _seed_session(db, user, TherapyType.HEMODIALYSIS)
    s = await patient_surfaces.for_user(db, user.id)
    assert "hemodialysis" in s.offered
    assert "session" in s.because["hemodialysis"]


@pytest.mark.asyncio
async def test_a_declared_therapy_the_map_does_not_name_opens_the_group(db):
    """Chemotherapy has no dedicated surface, and must not vanish for it."""
    user = await _seed_user(db, "declared-chemo@example.test")
    await _seed_condition(db, user, "Lymphoma", "chemotherapy",
                          category=ConditionCategory.CANCER)
    s = await patient_surfaces.for_user(db, user.id)
    assert "therapy_other" in s.offered and "therapies" in s.offered
    assert "hemodialysis" not in s.offered


def test_the_server_decides_what_a_therapy_NAME_means():
    """§3ad: the client never decides what a code means. A typo must not become
    a modality nobody offers a screen for."""
    assert validate_therapy_types(["Peritoneal Dialysis"]) == "peritoneal_dialysis"
    assert set(validate_therapy_types(
        ["PERITONEAL_DIALYSIS", "hemodialysis"]).split(",")) == {
            "hemodialysis", "peritoneal_dialysis"}
    assert validate_therapy_types(["not-a-therapy"]) is None
    # Empty is NULL — "not stated", a different fact from "no therapy" (§3aa).
    assert validate_therapy_types([]) is None


def test_a_stored_value_that_is_not_an_enum_member_is_ignored():
    """Reading is as strict as writing, so a row edited by hand or arriving
    from an older import cannot open a screen."""
    class _C:
        name = "X"
        therapy_types = "garbage,peritoneal_dialysis"
    assert declared_therapy_types(_C()) == {"peritoneal_dialysis"}


def test_the_keyword_dict_is_gone():
    """A guard against it coming back. The dict decided clinical navigation
    from the spelling of a diagnosis."""
    import inspect

    # ⚠️ Ask the MODULE, not its source text. The first two versions grepped
    # `inspect.getsource(...)` for "_CONDITION_HINTS" and failed on the
    # DOCSTRING that explains the removal — a guard tripping over its own
    # documentation, for the second time in one day (the recommendations guard
    # did the identical thing with "**recs"). §3av: a scan is evidence only
    # once it is shown to see what it claims to, and a guard that reads prose
    # is reading the wrong artifact.
    assert not hasattr(patient_surfaces, "_CONDITION_HINTS"), (
        "the keyword dict decided clinical navigation from the spelling of a "
        "diagnosis; the patient declares the therapy instead")
    # …and nothing matches a condition's WORDING to pick a surface.
    import ast
    import inspect as _inspect
    tree = ast.parse(_inspect.getsource(patient_surfaces.for_user))
    assert not [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Compare)
        and any(isinstance(o, ast.In) for o in n.ops)
        and isinstance(n.left, ast.Name) and n.left.id in {"h", "hint"}
    ], "surfacing must not be decided by substring-matching a diagnosis"
