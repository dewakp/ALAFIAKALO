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
    await _seed_condition(db, user, "End-Stage Renal Disease", "QB94.2")
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
    await _seed_condition(db, hd, "ESRD", "QB94.1")
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
    await _seed_condition(db, user, "Lymphoma", "QB97",
                          category=ConditionCategory.CANCER)
    s = await patient_surfaces.for_user(db, user.id)
    assert "therapy_other" in s.offered and "therapies" in s.offered
    assert "hemodialysis" not in s.offered


def test_the_server_decides_what_a_therapy_NAME_means():
    """§3ad: the client never decides what a code means. A typo must not become
    a modality nobody offers a screen for."""
    assert validate_therapy_types(["QB94.2"]) == "QB94.2"
    assert validate_therapy_types(["qb94.2"]) == "QB94.2"      # case-folded
    assert set(validate_therapy_types(["QB94.2", "QB94.1"]).split(",")) == {
        "QB94.1", "QB94.2"}
    # A value stored before the codes existed still reads, and normalises.
    assert validate_therapy_types(["peritoneal_dialysis"]) == "QB94.2"
    assert validate_therapy_types(["not-a-therapy"]) is None
    # A real-looking code outside the option set is refused too.
    assert validate_therapy_types(["QB99.9"]) is None
    # Empty is NULL — "not stated", a different fact from "no therapy" (§3aa).
    assert validate_therapy_types([]) is None


def test_a_stored_value_that_is_not_an_enum_member_is_ignored():
    """Reading is as strict as writing, so a row edited by hand or arriving
    from an older import cannot open a screen."""
    class _C:
        name = "X"
        therapy_types = "garbage,QB94.2"
    assert declared_therapy_types(_C()) == {"QB94.2"}


def test_the_keyword_dict_is_gone():
    """A guard against it coming back. The dict decided clinical navigation
    from the spelling of a diagnosis."""
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


# ── The declaration GOVERNS; sessions are history ───────────────────────────
#
# Operator, 2026-10-13: *"user can choose the therapy or therapies they undergo
# and only those therapies are surfaced in navigation."*

@pytest.mark.asyncio
async def test_a_declaration_OVERRULES_sessions_in_another_modality(db):
    """The case that forced this rule. Measured on the reference record: user 63
    declared ONLY peritoneal dialysis and was still offered the HD flowsheet,
    because 2,035 HD sessions opened it regardless — both modalities on screen
    for a patient who had just said which one they are on.

    **A declaration the navigation overrules is not a choice.**
    """
    user = await _seed_user(db, "switched@example.test")
    await _seed_session(db, user, TherapyType.HEMODIALYSIS)
    await _seed_condition(db, user, "ESRD", "QB94.2")
    s = await patient_surfaces.for_user(db, user.id)
    assert "peritoneal_dialysis" in s.offered
    assert "hemodialysis" not in s.offered, (
        "declaring PD must retire the HD flowsheet, whatever the history shows")


@pytest.mark.asyncio
async def test_but_the_PAST_is_never_hidden(db):
    """Losing the screen you work in daily and losing your past are different
    harms, and only the first is what a declaration should cause. A patient who
    moved from haemodialysis to PD stops needing the HD flowsheet and never
    stops owning their HD record (§3aa)."""
    user = await _seed_user(db, "history@example.test")
    await _seed_session(db, user, TherapyType.HEMODIALYSIS)
    await _seed_condition(db, user, "ESRD", "QB94.2")
    s = await patient_surfaces.for_user(db, user.id)
    assert "therapy_history" in s.offered
    assert "session" in s.because["therapy_history"], (
        "history must cite the sessions, not the declaration that replaced them")


@pytest.mark.asyncio
async def test_declaring_BOTH_offers_both(db):
    """Some patients genuinely run both — PD at home with HD support."""
    user = await _seed_user(db, "both@example.test")
    await _seed_condition(db, user, "ESRD", "QB94.1,QB94.2")
    s = await patient_surfaces.for_user(db, user.id)
    assert {"hemodialysis", "peritoneal_dialysis"} <= s.offered


@pytest.mark.asyncio
async def test_declaring_an_UNRELATED_therapy_retires_the_dialysis_screens(db):
    """A patient whose only declaration is chemotherapy is not on dialysis,
    whatever sessions the record holds from before. The group and the history
    stay; the dialysis flowsheets do not."""
    user = await _seed_user(db, "chemo-now@example.test")
    await _seed_session(db, user, TherapyType.HEMODIALYSIS)
    await _seed_condition(db, user, "Lymphoma", "QB97",
                          category=ConditionCategory.CANCER)
    s = await patient_surfaces.for_user(db, user.id)
    assert "therapy_other" in s.offered
    assert "hemodialysis" not in s.offered
    assert "therapy_history" in s.offered


# ── The option set is WHO's, not ours ───────────────────────────────────────

def test_every_offered_therapy_code_EXISTS_in_the_WHO_catalog():
    """Operator, 2026-10-13: *"against the rule"*.

    §3ad: *"Never type an ICD code from memory. The catalog is GENERATED from
    WHO's published MMS linearization… `tests/test_icd11_catalog.py` fails the
    build if a hand-written alias points at a code that is not in the file."*

    The first version of this feature was a hand-typed enum mirrored into FOUR
    files — the backend, web, iOS and Android — while WHO already coded every
    entry. This is the same guard that file applies to condition aliases.
    """
    from app.services.icd11_catalog import get_icd11_by_code
    from app.services.patient_surfaces import THERAPY_CODE_SURFACE

    missing = [c for c in THERAPY_CODE_SURFACE if get_icd11_by_code(c) is None]
    assert not missing, f"codes absent from the bundled catalog: {missing}"


def test_the_LABELS_come_from_WHO_and_are_not_written_here():
    """A title typed beside a code is a second source of truth that drifts from
    the first. `therapy_options()` reads every title out of the catalog."""
    from app.services.icd11_catalog import get_icd11_by_code
    from app.services.patient_surfaces import therapy_options

    options = therapy_options()
    assert options, "the option set must not be empty"
    for o in options:
        assert o["title"] == get_icd11_by_code(o["code"]).title


def test_the_modality_codes_are_the_ones_WHO_actually_separates():
    """QB94.1 and QB94.2 are what let "only PD patients see PD" be expressible
    at all. Pinned by code AND by what WHO calls them, so a renumbering or a
    mis-paste fails here rather than on a patient's navigation."""
    from app.services.icd11_catalog import get_icd11_by_code
    from app.services.patient_surfaces import THERAPY_CODE_SURFACE

    assert THERAPY_CODE_SURFACE["QB94.1"] == "hemodialysis"
    assert THERAPY_CODE_SURFACE["QB94.2"] == "peritoneal_dialysis"
    assert "extracorporeal" in get_icd11_by_code("QB94.1").title.lower()
    assert "peritoneal" in get_icd11_by_code("QB94.2").title.lower()


def test_no_client_needs_a_therapy_list_of_its_own():
    """The endpoint exists so none of the three clients carries a copy."""
    from app.api.chronic_conditions import get_therapy_options
    assert callable(get_therapy_options)


# ── A comprehensive list, and a SWITCH that can hold a zero ─────────────────
#
# Operator, 2026-10-14: *"hard-coded enum for therapy will need a comprehensive
# list with items zeroed out (no impact) when not present (like a switch) and a
# mechanism for compounded therapies. current model lacks comprehensive list
# and does not include switch mechanism."*

from app.models.chronic_conditions import ConditionTherapy          # noqa: E402
from app.services.patient_surfaces import (                         # noqa: E402
    THERAPY_BRANCHES, regimens, therapy_codes, therapy_switches,
)


async def _switch(db, condition_id, code, receiving, regimen=None):
    db.add(ConditionTherapy(condition_id=condition_id, therapy_code=code,
                            receiving=receiving, regimen=regimen))
    await db.flush()


async def _condition_id(db, user, name="ESRD"):
    from sqlalchemy import select
    from app.models.chronic_conditions import ChronicCondition
    await _seed_condition(db, user, name, None)
    return (await db.execute(select(ChronicCondition.id)
            .where(ChronicCondition.user_id == user.id)
            .order_by(ChronicCondition.id.desc()).limit(1))).scalar_one()


def test_the_list_is_COMPREHENSIVE_not_curated():
    """The previous version named 10 codes while the branch they came from
    holds 31. Picking ten of thirty-one is typing them with extra steps."""
    codes = therapy_codes()
    assert len(codes) >= 30, f"only {len(codes)} codes — the set is curated again"
    # Things a patient could not previously say at all:
    for code in ("QB99", "QB9B", "QB95.0", "QB41"):
        assert code in codes, f"{code} missing — someone narrowed the branches"


def test_the_branch_roots_each_carry_a_REASON():
    """A root with no stated reason is a curation decision nobody can audit."""
    for root, reason in THERAPY_BRANCHES.items():
        assert reason and len(reason) > 20, f"{root} has no stated reason"


def test_a_three_character_root_still_matches_its_children():
    """⚠️ The first predicate tested `code.startswith(root + ".")`, right for
    QB94 -> QB94.1 and SILENTLY WRONG for QB4 -> QB40: every dependence code
    was dropped and the "comprehensive" list quietly lost six entries."""
    codes = therapy_codes()
    assert {"QB40", "QB41", "QB42", "QB43", "QB44"} <= set(codes)


@pytest.mark.asyncio
async def test_an_explicit_ZERO_retires_the_screen(db):
    """The switch. A set could never express this: absence meant "not on it"
    AND "nobody asked" at once (§3at's checkbox, on a therapy picture)."""
    user = await _seed_user(db, "switch-off@example.test")
    cid = await _condition_id(db, user)
    await _switch(db, cid, "QB94.2", receiving=True)
    s = await patient_surfaces.for_user(db, user.id)
    assert "peritoneal_dialysis" in s.offered

    # …now say explicitly that they are NOT on it.
    from sqlalchemy import update
    await db.execute(update(ConditionTherapy)
                     .where(ConditionTherapy.condition_id == cid)
                     .values(receiving=False))
    await db.flush()
    s = await patient_surfaces.for_user(db, user.id)
    assert "peritoneal_dialysis" not in s.offered, (
        "a stated zero must retire the screen, not read as never-asked")


@pytest.mark.asyncio
async def test_never_asked_and_stated_zero_are_different_facts(db):
    """`receiving=False` is EVIDENCE; no row is the absence of evidence. They
    must not be the same value in the payload (§3aa)."""
    user = await _seed_user(db, "tri-state@example.test")
    cid = await _condition_id(db, user)
    await _switch(db, cid, "QB94.1", receiving=False)

    switches = await therapy_switches(db, user.id)
    assert switches["QB94.1"]["receiving"] is False     # a measured zero
    assert "QB94.2" not in switches                     # never asked


@pytest.mark.asyncio
async def test_a_stated_zero_OVERRULES_the_legacy_column(db):
    """A statement always beats a membership. The old comma-separated column
    cannot say "no", so the switch must win where it has an answer."""
    user = await _seed_user(db, "zero-beats-legacy@example.test")
    await _seed_condition(db, user, "ESRD", "QB94.1")     # legacy: on HD
    from sqlalchemy import select
    from app.models.chronic_conditions import ChronicCondition
    cid = (await db.execute(select(ChronicCondition.id)
           .where(ChronicCondition.user_id == user.id))).scalars().first()
    await _switch(db, cid, "QB94.1", receiving=False)     # switch: NOT on HD

    s = await patient_surfaces.for_user(db, user.id)
    assert "hemodialysis" not in s.offered


@pytest.mark.asyncio
async def test_RECEIVING_on_any_condition_wins(db):
    """A patient on dialysis for ESRD is on dialysis, whatever a second
    condition's row happens to say."""
    user = await _seed_user(db, "two-conditions@example.test")
    a = await _condition_id(db, user, "ESRD")
    b = await _condition_id(db, user, "Diabetes")
    await _switch(db, a, "QB94.1", receiving=True)
    await _switch(db, b, "QB94.1", receiving=False)
    switches = await therapy_switches(db, user.id)
    assert switches["QB94.1"]["receiving"] is True


@pytest.mark.asyncio
async def test_COMPOUNDED_therapies_are_grouped_by_regimen(db):
    """The compounding mechanism: therapies sharing a label are given as ONE
    treatment, so a reader can tell a combination from a coincidence."""
    user = await _seed_user(db, "regimen@example.test")
    cid = await _condition_id(db, user)
    await _switch(db, cid, "QB94.1", True, regimen="anaemia management")
    await _switch(db, cid, "QB98", True, regimen="anaemia management")
    await _switch(db, cid, "QB95.1", True)              # not part of it

    groups = regimens(await therapy_switches(db, user.id))
    assert groups == {"anaemia management": ["QB94.1", "QB98"]}


@pytest.mark.asyncio
async def test_a_regimen_never_includes_a_therapy_that_is_OFF(db):
    """A compound is what the patient is actually given. A zeroed member is
    not part of a current regimen."""
    user = await _seed_user(db, "regimen-off@example.test")
    cid = await _condition_id(db, user)
    await _switch(db, cid, "QB94.1", True, regimen="combined")
    await _switch(db, cid, "QB98", False, regimen="combined")
    groups = regimens(await therapy_switches(db, user.id))
    assert groups == {"combined": ["QB94.1"]}
