# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""TASKS 25: an item with no amount is proposed the amounts THIS patient has
stated for that food, and nothing is applied until they confirm.

Operator, 2026-10-24: "The Alafia model for food is to learn from user input
and let users verify the learned data".
"""

import datetime
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.nutrition import NutritionLog
from app.models.user import User
from app.services import amount_history as ah

pytestmark = pytest.mark.asyncio


# ── what counts as a stated amount ────────────────────────────────────────

def test_only_an_amount_the_patient_typed_is_history():
    assert ah.stated_amounts("350 ml smoothie, toast") == [("smoothie", "350 ml")]
    # a bracketed spice once got a guessed "1 teaspoon"; nothing typed it
    assert ah.stated_amounts("jollof rice (rice, 50 g tomato, pepper)") == [("tomato", "50 g")]
    # a bare count names no weight
    assert ah.stated_amounts("2 eggs") == []


def test_the_items_missing_an_amount_are_named():
    assert ah.missing_amount_items("Smoothie, 200 g rice") == ["smoothie"]


def test_only_what_the_estimate_left_out_is_asked_about():
    assert ah.left_out_for_amount(["Smoothie (no amount given)", "sardines", "raw (no amount given)"]) == [
        "smoothie", "raw"]
    assert ah.left_out_for_amount(None) == []


# ── writing a confirmed amount into the meal ──────────────────────────────

def test_the_amount_goes_where_the_patient_would_have_typed_it():
    assert ah.apply_amounts("Smoothie, 200 g rice", {"smoothie": "350 ml"}) == "350 ml Smoothie, 200 g rice"


def test_a_bracketed_ingredient_takes_its_amount_inside_the_brackets():
    out = ah.apply_amounts("jollof rice (rice, 50 g tomato, pepper)", {"pepper": "5 g"})
    assert out == "jollof rice (rice, 50 g tomato, 5 g pepper)"


@pytest.mark.parametrize("amount", ["2", "lots", ""])
def test_anything_that_is_not_a_measure_is_refused(amount):
    with pytest.raises(ah.AmountNotUnderstood):
        ah.apply_amounts("Smoothie", {"smoothie": amount})


def test_an_item_that_already_has_an_amount_is_not_overwritten():
    with pytest.raises(ah.AmountNotUnderstood):
        ah.apply_amounts("200 g rice", {"rice": "1 cup"})


# ── proposals from the patient's own history ─────────────────────────────

async def _user(db) -> User:
    u = User(email=f"amt{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", full_name="T")
    db.add(u)
    await db.flush()
    return u


async def _meal(db, user, text, day):
    log = NutritionLog(user_id=user.id, log_date=day, meal_type="lunch", food_name=text,
                       nutrient_status="done")
    db.add(log)
    await db.flush()
    return log


async def test_suggestions_are_this_patients_ranked_by_use(db):
    u, other = await _user(db), await _user(db)
    d = datetime.date(2026, 10, 1)
    await _meal(db, u, "350 ml Smoothie", d)
    await _meal(db, u, "350 ML smoothie, toast", d + datetime.timedelta(days=1))
    await _meal(db, u, "250 ml smoothie", d + datetime.timedelta(days=2))
    await _meal(db, other, "900 ml smoothie", d)          # someone else's history
    got = await ah.suggestions(db, u.id, ["smoothie"])
    assert [(s["amount"], s["times"]) for s in got["smoothie"]] == [("350 ML", 2), ("250 ml", 1)]
    assert got["smoothie"][0]["last_date"] == "2026-10-02"


async def test_no_history_is_an_empty_list_not_a_guess(db):
    u = await _user(db)
    assert await ah.suggestions(db, u.id, ["egusi"]) == {"egusi": []}


# ── the endpoints ─────────────────────────────────────────────────────────

async def _token(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"email": email, "password": "SecureP@ss123",
                                                     "full_name": "Amount User", "date_of_birth": "1990-01-01"})
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": "SecureP@ss123"})
    return r.json()["access_token"]


async def test_the_endpoints_propose_then_write_only_what_was_confirmed(client: AsyncClient, db, monkeypatch):
    import app.api.nutrition as api_mod
    queued = []
    monkeypatch.setattr(api_mod, "enrich_log", lambda log_id, **k: queued.append((log_id, k)))
    email = f"amt{uuid.uuid4().hex[:6]}@example.com"
    h = {"Authorization": f"Bearer {await _token(client, email)}"}
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    await _meal(db, user, "350 ml smoothie", datetime.date(2026, 10, 1))
    log = await _meal(db, user, "Smoothie, 200 g rice", datetime.date(2026, 10, 24))
    log.calories, log.nutrients_excluded = 260.0, ["smoothie (no amount given)"]
    await db.commit()

    listed = await client.get("/api/v1/nutrition/", headers=h)
    assert next(x for x in listed.json() if x["id"] == log.id)["needs_amount"] == ["smoothie"]

    r = await client.get(f"/api/v1/nutrition/{log.id}/missing-amounts", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["items"] == [{"food_name": "smoothie", "suggestions": [
        {"amount": "350 ml", "times": 1, "last_date": "2026-10-01"}]}]

    bad = await client.post(f"/api/v1/nutrition/{log.id}/amounts", json={"amounts": {"smoothie": "2"}}, headers=h)
    assert bad.status_code == 422 and bad.json()["detail"]["food_name"] == "smoothie"
    assert bad.json()["detail"]["code"] == "not_a_measure"
    await db.refresh(log)
    assert log.food_name == "Smoothie, 200 g rice" and log.calories == 260.0, "a refusal writes nothing"

    ok = await client.post(f"/api/v1/nutrition/{log.id}/amounts", json={"amounts": {"smoothie": "350 ml"}}, headers=h)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["food_name"] == "350 ml Smoothie, 200 g rice"
    assert body["nutrient_status"] == "pending" and body["calories"] is None
    assert body["nutrients_excluded"] is None and body["needs_amount"] == []
    assert queued == [(log.id, {"notify": True})]


async def test_another_patients_meal_is_404(client: AsyncClient, db):
    other = await _user(db)
    log = await _meal(db, other, "Smoothie", datetime.date(2026, 10, 24))
    await db.commit()
    h = {"Authorization": f"Bearer {await _token(client, f'amx{uuid.uuid4().hex[:6]}@example.com')}"}
    assert (await client.get(f"/api/v1/nutrition/{log.id}/missing-amounts", headers=h)).status_code == 404
    assert (await client.post(f"/api/v1/nutrition/{log.id}/amounts", json={"amounts": {"smoothie": "1 cup"}},
                              headers=h)).status_code == 404
