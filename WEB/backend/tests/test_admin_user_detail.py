"""The admin user detail: identifiers an operator can reconcile, and real activity.

Built because the console showed a user as "—" with no way to see why. Two things
it must get right:

  * the **System Identifier** is the cross-system key — `system_id.py` says it
    mirrors the FLOWSHEET portal's `user_identity_sid_log`, so an operator
    reconciling an account against FLOWSHEET reads it here. It was not displayed
    anywhere before.
  * a domain whose lookup FAILS must not report zero. "0 meals" and "we could not
    ask" are different findings, and only one of them is about the patient
    (canon 3aa: an error is not an empty state).
"""

import pytest
from sqlalchemy import select

from app.api.admin import _decode_sid, _subject_token, _user_activity
from app.models.user import User


# ── The SID an operator has to compare against FLOWSHEET ─────────────────────

def test_a_sid_is_split_into_comparable_segments():
    """A mismatch is usually ONE segment; 255 unbroken chars hide which.

    Date of birth and gender are MASKED. They are SID segments, so printing them
    here would have moved the health disclosure out of `profile` rather than
    ended it. The structure stays legible — a missing segment is still a
    finding — without the values.
    """
    sid = "S1.WOL.AKP.19740315.M.1747887746.PAYLOAD.checksum"
    seg = _decode_sid(sid)
    assert seg == {
        "version": "S1", "first3": "WOL", "last3": "AKP",
        "dob8": "••••••••", "dob_present": True,
        "gender": "•", "gender_present": True,
        "epoch10": "1747887746",
    }


def test_the_sid_never_prints_a_date_of_birth():
    """The regression guard: no real DOB or gender may appear in the segments."""
    seg = _decode_sid("S1.WOL.AKP.19740315.M.1747887746.PAYLOAD.checksum")
    rendered = repr(seg)
    assert "19740315" not in rendered
    # "M" alone is too short to search for safely; assert the field directly.
    assert seg["gender"] == "•"
    assert seg["dob8"] == "••••••••"


def test_a_sid_missing_a_segment_still_reads_as_missing():
    """Masking must not make an absent DOB look present."""
    seg = _decode_sid("S1.WOL.AKP...1747887746.PAYLOAD.checksum")
    assert seg["dob_present"] is False
    assert seg["gender_present"] is False


def test_a_malformed_sid_is_reported_not_invented():
    """Guessing segments for a broken SID hides the very thing worth seeing."""
    seg = _decode_sid("nonsense-without-dots")
    assert seg["malformed"] is True
    assert "nonsense" in seg["raw"]


def test_no_sid_is_none_not_a_fake():
    assert _decode_sid(None) is None
    assert _decode_sid("") is None


def test_the_subject_token_is_the_ai_handle(monkeypatch):
    """Same value the AI egress sends, so the console can be cross-referenced."""
    monkeypatch.setenv("ALAFIA_PSEUDONYM_SECRET", "test-secret")
    from alafia_model import privacy
    assert _subject_token(63) == privacy.subject_token(63)


# ── Activity ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_activity_counts_and_dates_are_reported(db):
    user = User(email="activity@example.com", hashed_password="x", full_name="A B")
    db.add(user)
    await db.flush()

    activity = await _user_activity(db, user.id)

    # Every domain answers, even with nothing logged.
    for domain in ("meals", "medication_doses", "conditions", "lab_results",
                   "therapy_sessions", "documents", "vitals", "notifications"):
        assert domain in activity, domain
        assert activity[domain]["count"] == 0
        assert activity[domain]["last"] is None


@pytest.mark.asyncio
async def test_a_failed_lookup_is_not_reported_as_zero(db, monkeypatch):
    """The whole point. A missing table must read "unavailable", never "0".

    A zero says "this patient logs nothing", which is a clinical statement. If
    the query could not run we have not learned that.
    """
    import app.api.admin as admin_mod

    original = admin_mod._user_activity.__globals__["text"]

    def _boom(sql):
        if "nutrition_logs" in sql:
            raise RuntimeError("relation does not exist")
        return original(sql)

    monkeypatch.setitem(admin_mod._user_activity.__globals__, "text", _boom)

    user = User(email="broken@example.com", hashed_password="x", full_name="C D")
    db.add(user)
    await db.flush()

    activity = await _user_activity(db, user.id)

    assert activity["meals"]["count"] is None, activity["meals"]
    assert activity["meals"].get("unavailable") is True
    # …and one failure must not take the rest of the page with it.
    assert activity["vitals"]["count"] == 0


# ── The console is not a back door into health data ──────────────────────────

def test_the_admin_detail_serves_no_clinical_field():
    """ADMIN_CONSOLE.md: "counts and metadata only — never clinical records".

    The code broke its own documented contract: the `profile` block served
    `allergies`, `height_cm`, `current_weight_kg`, `date_of_birth` and `gender`
    to an operator, none of which are needed to answer "is this account healthy
    and who is using it". An operator is the one reader a patient never granted
    access to — a clinician has an explicit DataGrant, an admin has an allowlist.

    Read off the source rather than a live response so this fails the moment a
    field is added back, with or without a database.
    """
    import inspect
    from app.api import admin

    src = inspect.getsource(admin.admin_user_detail)
    profile = src.split('"profile": {', 1)[1].split("},", 1)[0]

    for field in (
        "allergies",
        "height_cm",
        "current_weight_kg",
        "date_of_birth",
        "gender",
        "blood_type",
        "family_history",
        "dietary_restrictions",
        "food_intolerances",
    ):
        assert field not in profile, (
            f"{field!r} is clinical and must not be served by the admin console"
        )


def test_the_admin_detail_keeps_what_an_operator_needs():
    """Removing clinical data must not strip the administrative fields with it."""
    import inspect
    from app.api import admin

    src = inspect.getsource(admin.admin_user_detail)
    profile = src.split('"profile": {', 1)[1].split("},", 1)[0]

    for field in ("country", "timezone", "phone_number"):
        assert field in profile, f"{field!r} is administrative and should remain"


def test_the_raw_sid_does_not_leak_what_the_segments_mask():
    """Masking the segments alone moved the disclosure; it did not end it.

    The raw `system_id` sits beside `system_id_segments` in the same response,
    and it reads `S1.IOS.REV.19850615.F....` — the date of birth and gender in
    plain text. Found by reading an actual response, not the diff.
    """
    from app.api.admin import _mask_sid

    sid = "S1.WOL.AKP.19740315.M.1747887746.PAYLOAD.checksum"
    masked = _mask_sid(sid)

    assert "19740315" not in masked
    assert masked.split(".")[3] == "••••••••"
    assert masked.split(".")[4] == "•"
    # The cross-system key itself must survive, or reconciliation breaks.
    assert masked.endswith(".PAYLOAD.checksum")
    assert masked.startswith("S1.WOL.AKP.")


def test_a_malformed_sid_is_still_truncated_not_exploded():
    from app.api.admin import _mask_sid

    assert _mask_sid("garbage") == "garbage"
    assert _mask_sid(None) is None
