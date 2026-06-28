"""Keep a user's Profile insurance fields and their Insurance Plans in sync.

Profile holds a single insurance (``users.insurance_id/insurance_provider/
insurance_country``); the Insurance Plans page holds richer ``insurances`` rows.
We mirror them both ways:
  - Profile saved  → upsert the user's PRIMARY plan (sync_profile_to_plan).
  - Plan saved     → write the primary plan back to Profile (sync_plan_to_profile).
  - Plans listed   → if none exist but Profile has insurance, materialise one
                     (ensure_plan_from_profile) so existing data shows up.
Each API path calls only ONE direction, so there is no feedback loop.
"""
from __future__ import annotations

import re

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insurance import Insurance, COUNTRIES_BY_REGION

# Common country aliases → ISO 3166-1 alpha-2.
_COUNTRY_ALIASES = {
    "USA": "US", "U.S.": "US", "U.S.A.": "US", "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US", "AMERICA": "US",
    "UK": "GB", "U.K.": "GB", "UNITED KINGDOM": "GB", "ENGLAND": "GB", "BRITAIN": "GB",
    "UAE": "AE",
}


def _resolve_country(raw: str | None) -> tuple[str, str, str]:
    """Return (region, country_code, country_name) for a country string, best-effort."""
    if not raw or not raw.strip():
        return ("other", "XX", "Unknown")
    s = raw.strip()
    up = _COUNTRY_ALIASES.get(s.upper(), s.upper())
    for region, countries in COUNTRIES_BY_REGION.items():
        for c in countries:
            if up == c["code"].upper() or s.lower() == c["name"].lower():
                return (region, c["code"], c["name"])
    code = up[:2] if len(up) >= 2 else "XX"
    return ("other", code, s)


def _slug(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "insurance"


def _profile_has_insurance(user) -> bool:
    return bool(user.insurance_provider or user.insurance_id)


async def _primary_or_first_plan(db: AsyncSession, user_id: int) -> Insurance | None:
    res = await db.execute(
        select(Insurance).where(Insurance.user_id == user_id)
        .order_by(Insurance.is_primary.desc(), Insurance.id.asc())
    )
    return res.scalars().first()


def _apply_profile_to_plan(plan: Insurance, user) -> None:
    region, code, name = _resolve_country(user.insurance_country)
    if user.insurance_provider:
        plan.provider_name = user.insurance_provider
        plan.provider_code = _slug(user.insurance_provider)
    if user.insurance_id is not None:
        plan.member_id = user.insurance_id
    if user.insurance_country:
        plan.region, plan.country_code, plan.country_name = region, code, name


async def sync_profile_to_plan(db: AsyncSession, user) -> None:
    """Upsert the user's primary plan from their Profile insurance fields."""
    if not _profile_has_insurance(user):
        return
    plan = await _primary_or_first_plan(db, user.id)
    if plan is None:
        region, code, name = _resolve_country(user.insurance_country)
        plan = Insurance(
            user_id=user.id, region=region, country_code=code, country_name=name,
            provider_code=_slug(user.insurance_provider),
            provider_name=user.insurance_provider or "Insurance",
            member_id=user.insurance_id, is_primary=True, is_active=True,
        )
        db.add(plan)
    else:
        _apply_profile_to_plan(plan, user)
    await db.flush()


async def ensure_plan_from_profile(db: AsyncSession, user) -> None:
    """If the user has NO plans but Profile has insurance, create one (lazy backfill)."""
    if not _profile_has_insurance(user):
        return
    count = await db.scalar(
        select(func.count(Insurance.id)).where(Insurance.user_id == user.id))
    if count and count > 0:
        return
    await sync_profile_to_plan(db, user)


async def sync_plan_to_profile(db: AsyncSession, user, plan: Insurance) -> None:
    """Mirror a (primary) plan back into the Profile insurance fields."""
    user.insurance_id = plan.member_id or plan.policy_number
    user.insurance_provider = plan.provider_name
    user.insurance_country = plan.country_name or plan.country_code
    await db.flush()
