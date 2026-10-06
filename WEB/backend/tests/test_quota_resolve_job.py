# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""The clock the quota store never had.

`condition_nutrient_quotas` (ap001) resolves a figure once, cites it, and
sharpens `times_confirmed` on re-resolution. Nothing ever called it a second
time, which is why every learning store in this codebase sits at n=1
(OPEN_ITEMS §8a). `_quota_resolve_job` is that second call.

**Guards vs coverage, stated because the distinction keeps being worth it.**
One test here is a real guard against a shipped default: if
`QUOTA_RESOLVE_ENABLED` ever becomes True, every deploy starts provider
traffic nobody asked for, and that is a cost regression no behavioural test
would catch. The rest is coverage for a function that did not exist.

The §3aa rule — never query `ChronicCondition` directly — is NOT re-tested
here. `test_clinical_sources.py` already scans every file in the tree, so
duplicating it would be a second place to keep in step.
"""

import pytest

from app import main
from app.core.config import settings


class _Ctx:
    """Stands in for `async_session()`, handing the job the test session."""

    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


class _Cond:
    """Minimal stand-in for clinical_sources.ConditionView (field is `name`)."""

    def __init__(self, name: str):
        self.name = name


class _Resolver:
    """Records what the job asked for, and with which nutrients."""

    def __init__(self, result=None):
        self.calls: list[tuple[str, tuple]] = []
        self.result = result if result is not None else ["row"]

    async def __call__(self, db, label, *, icd11_code=None, nutrient_keys=None):
        self.calls.append((label, tuple(nutrient_keys or ())))
        return list(self.result)


@pytest.fixture
def wired(db, monkeypatch):
    """Point the job at the test session and stub its collaborators."""
    from app.services import clinical_sources as sources
    from app.services import nutrient_quota_service as nqs

    monkeypatch.setattr(main, "async_session", lambda: _Ctx(db))

    state = {"conditions": [], "stored": {}}

    async def _conditions(_db, _uid, active_only=False):
        return list(state["conditions"])

    async def _stored(_db, labels, **kw):
        # Keyed on the LABEL the job passes, not on the repr of the list it
        # wraps it in — getting that wrong made every condition look unresolved
        # and the test fail for a reason that had nothing to do with the job.
        first = next(iter(labels), "")
        return list(state["stored"].get(str(first), []))

    monkeypatch.setattr(sources, "conditions", _conditions)
    monkeypatch.setattr(nqs, "stored_quotas", _stored)
    return state


_user_seq = 0


async def _one_active_user(db):
    """The job selects active users; add one more each call.

    The email must be unique per call: `users.email` is uniquely indexed, and a
    hardcoded address made the "two patients, one condition" test violate it —
    which does not merely fail that assertion, it poisons the session and the
    fixture's teardown commit then raises PendingRollbackError on top. That is
    the rollback-expiry hazard in a new disguise: one bad flush turns a clear
    failure into two confusing ones.
    """
    global _user_seq
    _user_seq += 1

    from app.core.security import hash_password
    from app.models.user import User

    u = User(email=f"clock{_user_seq}@example.com",
             hashed_password=hash_password("x"),
             full_name=f"Clock User {_user_seq}", is_active=True)
    db.add(u)
    await db.flush()
    return u


# ─────────────────────────────────────────────────────────────────────
# GUARD — a shipped default that starts provider traffic is a regression
# ─────────────────────────────────────────────────────────────────────

def test_quota_resolution_is_off_by_default():
    """Every model call this job makes costs money and leaves the building.

    `FIREBASE_SYNC_ENABLED` is False for the same reason. Flipping this
    default would start LLM traffic on every deploy, in every environment,
    without anyone choosing it.
    """
    assert settings.QUOTA_RESOLVE_ENABLED is False
    assert settings.QUOTA_RESOLVE_MAX_PER_RUN >= 1
    assert settings.QUOTA_RESOLVE_INTERVAL_HOURS >= 1


def test_the_job_is_registered_only_behind_its_flag():
    """The scheduler block must gate on the setting, and log either way."""
    import inspect

    src = inspect.getsource(main)
    assert "if settings.QUOTA_RESOLVE_ENABLED:" in src
    assert 'id="quota_resolve"' in src
    # §3ae's lesson: a disabled path that says nothing is indistinguishable
    # from a broken one for as long as nobody looks.
    assert "Nutrient quota resolution disabled" in src
    # Never overlap, and never let a restart loop become a traffic burst.
    assert "max_instances=1" in src


# ─────────────────────────────────────────────────────────────────────
# Coverage for the job body
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_it_asks_only_about_conditions_with_no_quota(wired, db, monkeypatch):
    from app.services import nutrient_quota_service as nqs

    await _one_active_user(db)
    wired["conditions"] = [_Cond("Chronic kidney disease"), _Cond("Coeliac disease")]
    wired["stored"] = {"Chronic kidney disease": ["existing"]}

    resolver = _Resolver()
    monkeypatch.setattr(nqs, "resolve_quota", resolver)
    await main._quota_resolve_job()

    asked = [label for label, _ in resolver.calls]
    assert asked == ["Coeliac disease"], (
        "a condition that already has a cited quota must not cost a model call")


@pytest.mark.asyncio
async def test_the_nutrients_come_from_compute_goals_not_a_typed_list(
    wired, db, monkeypatch
):
    """A hardcoded nutrient list here would drift from the ladder it feeds."""
    from app.services import nutrient_quota_service as nqs
    from app.services.nutrient_goals_service import compute_goals

    await _one_active_user(db)
    wired["conditions"] = [_Cond("Coeliac disease")]
    resolver = _Resolver()
    monkeypatch.setattr(nqs, "resolve_quota", resolver)
    await main._quota_resolve_job()

    expected = {g["key"] for g in compute_goals()["goals"]}
    assert set(resolver.calls[0][1]) == expected
    assert "calcium_mg" in expected, "the §8a case must be among them"


@pytest.mark.asyncio
async def test_it_stops_at_the_per_run_budget(wired, db, monkeypatch):
    from app.services import nutrient_quota_service as nqs

    await _one_active_user(db)
    wired["conditions"] = [_Cond(f"Condition {i}") for i in range(10)]
    resolver = _Resolver()
    monkeypatch.setattr(nqs, "resolve_quota", resolver)
    monkeypatch.setattr(settings, "QUOTA_RESOLVE_MAX_PER_RUN", 3)

    await main._quota_resolve_job()
    assert len(resolver.calls) == 3


@pytest.mark.asyncio
async def test_one_condition_is_asked_once_however_many_patients_have_it(
    wired, db, monkeypatch
):
    """A quota is a fact about a condition, not about a patient."""
    from app.services import nutrient_quota_service as nqs

    await _one_active_user(db)
    await _one_active_user(db)
    wired["conditions"] = [_Cond("Coeliac disease")]
    resolver = _Resolver()
    monkeypatch.setattr(nqs, "resolve_quota", resolver)

    await main._quota_resolve_job()
    assert len(resolver.calls) == 1


@pytest.mark.asyncio
async def test_a_condition_with_no_cited_figure_is_not_an_error(
    wired, db, monkeypatch
):
    """KDIGO states no calcium figure for dialysis. Empty is a real answer."""
    from app.services import nutrient_quota_service as nqs

    await _one_active_user(db)
    wired["conditions"] = [_Cond("Something no guideline quantifies")]
    monkeypatch.setattr(nqs, "resolve_quota", _Resolver(result=[]))

    await main._quota_resolve_job()  # must not raise


@pytest.mark.asyncio
async def test_a_failing_resolver_never_escapes_the_job(wired, db, monkeypatch):
    """A scheduled job that raises takes the next run with it."""
    from app.services import nutrient_quota_service as nqs

    await _one_active_user(db)
    wired["conditions"] = [_Cond("Coeliac disease")]

    async def _boom(*a, **kw):
        raise RuntimeError("all providers failed")

    monkeypatch.setattr(nqs, "resolve_quota", _boom)
    await main._quota_resolve_job()  # swallowed and logged, not raised


@pytest.mark.asyncio
async def test_an_unnamed_condition_is_skipped_not_resolved(wired, db, monkeypatch):
    from app.services import nutrient_quota_service as nqs

    await _one_active_user(db)
    wired["conditions"] = [_Cond(""), _Cond("   ")]
    resolver = _Resolver()
    monkeypatch.setattr(nqs, "resolve_quota", resolver)

    await main._quota_resolve_job()
    assert resolver.calls == []
