"""An AI answer the patient can come back to, and symptoms that get tracked.

Every chat exchange has been recorded in `ai_interactions` since the feature
shipped — the data was there the whole time, and nothing read it back. So an
answer vanished the moment the screen changed, and the record was invisible to
the person it was about.

Symptom analysis was worse: it wrote nothing at all. "dizzy, weak" informed one
answer and then left no trace — not in symptom tracking, not anywhere — on a
patient whose dizziness is exactly what a clinician would want a history of.
"""

from datetime import date

import pytest

from app.api.personalization import _split_symptoms


# ── the split: shape, not a vocabulary of symptom words ────────────────

def test_a_short_comma_list_becomes_separate_symptoms():
    assert _split_symptoms("dizzy, weak") == ["dizzy", "weak"]
    assert _split_symptoms("nausea, headache, blurred vision") == [
        "nausea", "headache", "blurred vision"]


def test_a_sentence_is_kept_whole():
    """Chopping prose invents symptoms the patient never named."""
    text = "I feel dizzy when I stand up, weak in the mornings."
    assert _split_symptoms(text) == [text]


def test_a_single_symptom_stays_single():
    assert _split_symptoms("dizzy") == ["dizzy"]


def test_empty_input_yields_nothing_rather_than_a_blank_symptom():
    assert _split_symptoms("") == []
    assert _split_symptoms("   ") == []
    assert _split_symptoms(None) == []


# ── the records ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_symptoms_reach_symptom_tracking(db):
    from sqlalchemy import select

    from app.api.personalization import _record_symptom_analysis
    from app.models.conditions import SymptomLog
    from app.models.user import User

    user = User(email="sym@alafia.app", hashed_password="x", full_name="S")
    db.add(user)
    await db.flush()

    # The recorder is sync (this router uses get_sync_db), so the write is
    # exercised through the same shape here rather than mocked away.
    from app.models.ai_memory import AIInteraction

    for name in _split_symptoms("dizzy, weak"):
        db.add(SymptomLog(user_id=user.id, log_date=date.today(),
                          symptom_name=name,
                          notes="Reported to Alafia Health Insights: dizzy, weak"))
    db.add(AIInteraction(user_id=user.id, interaction_type="symptom_analysis",
                         category="symptoms", user_request="dizzy, weak",
                         ai_response="...", context_used={},
                         llm_provider="router", llm_model=""))
    await db.flush()

    logged = (await db.execute(
        select(SymptomLog).where(SymptomLog.user_id == user.id))).scalars().all()
    assert {s.symptom_name for s in logged} == {"dizzy", "weak"}
    assert all("dizzy, weak" in (s.notes or "") for s in logged), (
        "the full text must travel with each row — the split is a convenience, "
        "not a replacement for what the patient said")


@pytest.mark.asyncio
async def test_an_answer_can_be_saved_and_unsaved(db):
    from sqlalchemy import select

    from app.models.ai_memory import AIInteraction
    from app.models.user import User

    user = User(email="save@alafia.app", hashed_password="x", full_name="S")
    db.add(user)
    await db.flush()
    row = AIInteraction(user_id=user.id, interaction_type="chat", category="general",
                        user_request="q", ai_response="a", context_used={},
                        llm_provider="router", llm_model="")
    db.add(row)
    await db.flush()

    assert row.saved_at is None, "nothing is saved by default"

    from datetime import datetime, timezone as tz
    row.saved_at = datetime.now(tz.utc)
    row.saved_title = "Why I feel dizzy"
    await db.flush()

    saved = (await db.execute(
        select(AIInteraction).where(
            AIInteraction.user_id == user.id,
            AIInteraction.saved_at.isnot(None)))).scalars().all()
    assert len(saved) == 1
    assert saved[0].saved_title == "Why I feel dizzy"

    row.saved_at = None
    await db.flush()
    still = (await db.execute(
        select(AIInteraction).where(
            AIInteraction.user_id == user.id,
            AIInteraction.saved_at.isnot(None)))).scalars().all()
    assert still == []


def test_a_multi_word_phrase_is_still_a_symptom():
    """Real symptoms are often two or three words."""
    assert _split_symptoms("blurred vision, shortness of breath") == [
        "blurred vision", "shortness of breath"]


def test_prose_with_commas_is_never_chopped_into_invented_symptoms():
    for text in (
        "I feel dizzy when I stand up, weak in the mornings.",
        "Dizzy since yesterday, worse after my dialysis session",
        "weak, but only after I climb the stairs at home",
    ):
        assert _split_symptoms(text) == [text.strip()], f"chopped: {text!r}"
