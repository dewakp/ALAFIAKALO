"""Mood / Mental Health CRUD endpoints."""

import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.mood import MoodEntry
from app.schemas.mood import MoodEntryCreate, MoodEntryUpdate, MoodEntryResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=list[MoodEntryResponse])
async def list_mood_entries(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(MoodEntry).where(MoodEntry.user_id == current_user.id)
    if start_date:
        query = query.where(MoodEntry.entry_date >= start_date)
    if end_date:
        query = query.where(MoodEntry.entry_date <= end_date)
    query = query.order_by(MoodEntry.entry_date.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=MoodEntryResponse, status_code=201)
async def create_mood_entry(
    entry_in: MoodEntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = MoodEntry(**entry_in.model_dump(), user_id=current_user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


class MoodScoreRequest(BaseModel):
    notes: str = Field(..., min_length=1, max_length=4000)


class MoodScoreSuggestion(BaseModel):
    mood_score: int | None = None
    energy_level: int | None = None
    rationale: str
    # False when the model could not be reached or answered unusably. The UI
    # must then leave the user to set the slider themselves rather than
    # inventing a number.
    available: bool = True


_SCORING_PROMPT = (
    "You read one short journal entry and rate the writer's mood.\n"
    "Reply with ONLY a JSON object, no prose, no code fence:\n"
    '{"mood_score": <1-10>, "energy_level": <1-10 or null>, '
    '"rationale": "<one short sentence quoting the words that decided it>"}\n\n'
    "The scale: 1 is despairing, 5 is neutral, 10 is elated. Rate what the\n"
    "writer actually describes, not how you would like them to feel. Exhaustion,\n"
    "pain and hopelessness are LOW numbers. Do not soften them.\n"
    "energy_level is separate from mood: someone can be content but depleted."
)


@router.post("/suggest-score", response_model=MoodScoreSuggestion)
async def suggest_mood_score(
    body: MoodScoreRequest,
    current_user: User = Depends(get_current_user),
):
    """Read what the patient wrote and propose a score for it.

    The form used to pre-fill 7/10 — "Good" — and record that for anyone who
    typed their entry without dragging the slider. An entry reading "exhausted
    and fatigued" was therefore filed as Good, and every trend, summary and
    clinician view downstream inherited the lie. A default is not a measurement.

    This only ever PROPOSES (canon 3aj: inference proposes, it never writes).
    The number is shown with the reason it was chosen and the user still presses
    save, so a wrong read is visible and correctable rather than silent.

    Unreachable is not zero: `available=False` tells the client to fall back to
    asking the user, never to a made-up number.

    ⚠️ This sends a NEW kind of free text to the provider chain. Redaction runs
    centrally at the egress point (canon 3al), so name, email, phone and DOB are
    stripped here as everywhere — but a bare first name in passing ("told Bola I
    was tired") is pattern-undetectable and documented as such. A journal entry
    is the surface most likely to contain one. It goes out under the same
    consent gate as the rest of the AI tier; nothing about this route weakens
    that, and nothing about it closes the known gap either.
    """
    from app.services.alafia_model_service import alafia_chat

    try:
        raw = (await alafia_chat(
            [{"role": "system", "content": _SCORING_PROMPT},
             {"role": "user", "content": body.notes.strip()}],
            temperature=0.0, max_tokens=200, json_mode=True, task="mood_score",
        )).strip()
    except Exception as exc:  # noqa: BLE001 - any provider failure is "ask the user"
        logger.warning("Mood scoring unavailable: %s", type(exc).__name__)
        return MoodScoreSuggestion(
            available=False,
            rationale="Scoring is unavailable right now — set the slider yourself.",
        )

    # Models wrap JSON in prose or a fence often enough that parsing the first
    # object out is the reliable path, not an optimisation.
    match = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(match.group(0) if match else raw)
    except (json.JSONDecodeError, AttributeError):
        logger.warning("Mood scoring returned unusable output: %r", raw[:200])
        return MoodScoreSuggestion(
            available=False,
            rationale="Could not read a score from that — set the slider yourself.",
        )

    def _clamp(value) -> int | None:
        try:
            n = int(round(float(value)))
        except (TypeError, ValueError):
            return None
        return min(10, max(1, n))

    score = _clamp(data.get("mood_score"))
    if score is None:
        return MoodScoreSuggestion(
            available=False,
            rationale="Could not read a score from that — set the slider yourself.",
        )

    rationale = str(data.get("rationale") or "").strip()[:300]
    return MoodScoreSuggestion(
        mood_score=score,
        energy_level=_clamp(data.get("energy_level")),
        rationale=rationale or "Suggested from what you wrote.",
    )


@router.get("/{entry_id}", response_model=MoodEntryResponse)
async def get_mood_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MoodEntry).where(MoodEntry.id == entry_id, MoodEntry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Mood entry not found")
    return entry


@router.patch("/{entry_id}", response_model=MoodEntryResponse)
async def update_mood_entry(
    entry_id: int,
    updates: MoodEntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MoodEntry).where(MoodEntry.id == entry_id, MoodEntry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Mood entry not found")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_mood_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MoodEntry).where(MoodEntry.id == entry_id, MoodEntry.user_id == current_user.id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Mood entry not found")
    raise HTTPException(
        status_code=403,
        detail="Mood entries cannot be deleted. You can modify this entry instead.",
    )
