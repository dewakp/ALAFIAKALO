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
    """A mismatch is usually ONE segment; 255 unbroken chars hide which."""
    sid = "S1.WOL.AKP.19740315.M.1747887746.PAYLOAD.checksum"
    seg = _decode_sid(sid)
    assert seg == {
        "version": "S1", "first3": "WOL", "last3": "AKP",
        "dob8": "19740315", "gender": "M", "epoch10": "1747887746",
    }


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
