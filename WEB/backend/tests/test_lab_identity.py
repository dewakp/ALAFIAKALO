"""A lab analyte is one thing, whatever the report called it.

Reports print alkaline phosphatase as ALP, ALK PHOS or in full. On the dev copy
of production one patient's history is stored as "ALP" until July 2025 and
"Alk Phos" after, because the report format changed, and every reader compared
the stored wording. The Liver Enzymes chart named only "ALP", so the six most
recent results (August 2025 to April 2026) never appeared on it; the clinician
board drew two short trends; and a re-imported report could not recognise a
result already on file under the other spelling.

Stored names stay as the document printed them. Readers compare `analyte_key`.
"""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.labs import LabResult
from app.models.user import User
from app.services import patient_board
from app.services.docparse.dictionaries import (
    analyte_key,
    canonical_name,
    category_for,
    display_name,
    preferred_name,
)
from tests.test_docparse import wrapped_range_pdf

EMAIL = "alp.history@example.com"


@pytest.mark.parametrize("printed", ["ALP", "Alk Phos", "ALK PHOS", "Alkaline Phosphatase",
                                     "alkaline  phosphatase"])
def test_every_way_a_report_prints_it_is_alkaline_phosphatase(printed):
    assert canonical_name(printed) == ("Alkaline Phosphatase", True)
    assert display_name(printed) == "Alkaline Phosphatase"
    assert analyte_key(printed) == analyte_key("ALP")


def test_it_is_filed_as_a_liver_enzyme():
    assert category_for("Alkaline Phosphatase") == "Liver & Protein"


def test_an_unknown_name_keeps_its_wording_and_only_case_is_folded():
    assert display_name("HEIGHT IN INCHES") == "HEIGHT IN INCHES"
    assert analyte_key("HEIGHT IN INCHES") == analyte_key("Height in Inches")
    assert analyte_key("ALP") != analyte_key("ALT/SGPT")


def test_a_merged_series_takes_the_vocabulary_name_not_the_newest_spelling():
    # Newer reports print MAGNESIUM, which the vocabulary has no entry for; the
    # older ones print MG, which it does.
    assert preferred_name(["MG", "Magnesium", "MAGNESIUM"]) == "Magnesium"
    assert preferred_name(["Total Cholesterol"], fallback="Total Cholesterol") == "Total Cholesterol"
    assert preferred_name(["HEIGHT IN INCHES", "Height in Inches"]) == "Height in Inches"


async def _patient(client: AsyncClient, db) -> tuple[str, int]:
    await client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": "SecureP@ss123",
              "full_name": "Liver Tester", "date_of_birth": "1970-01-01"},
    )
    r = await client.post("/api/v1/auth/login", data={"username": EMAIL, "password": "SecureP@ss123"})
    user = (await db.execute(select(User).where(User.email == EMAIL))).scalar_one()
    return r.json()["access_token"], user.id


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _result(user_id: int, when: date, value: float, name: str) -> LabResult:
    return LabResult(user_id=user_id, test_date=when, test_name=name, value=value, unit="U/L",
                     reference_range_low=46.0, reference_range_high=116.0, status="final")


async def _both_spellings(db, user_id: int) -> None:
    db.add_all([_result(user_id, date(2025, 1, 27), 412.0, "ALP"),
                _result(user_id, date(2025, 8, 18), 618.0, "Alk Phos")])
    await db.commit()


@pytest.mark.asyncio
async def test_the_chart_draws_one_series_across_both_spellings(client: AsyncClient, db):
    token, uid = await _patient(client, db)
    await _both_spellings(db, uid)

    r = await client.get("/api/v1/lab-charts/groups", headers=_auth(token))

    assert r.status_code == 200, r.text[:300]
    liver = next(g for g in r.json() if g["group_name"] == "Liver Enzymes")
    (series,) = liver["series"]
    assert series["test_name"] == "Alkaline Phosphatase"
    assert [(p["date"], p["value"]) for p in series["data"]] == [("2025-01-27", 412.0), ("2025-08-18", 618.0)]


@pytest.mark.asyncio
async def test_the_list_names_the_analyte_and_keeps_the_report_wording(client: AsyncClient, db):
    token, uid = await _patient(client, db)
    db.add(_result(uid, date(2025, 1, 27), 412.0, "ALP"))
    await db.commit()

    r = await client.get("/api/v1/labs/", headers=_auth(token))

    assert r.status_code == 200, r.text[:300]
    (row,) = r.json()
    assert row["test_name"] == "ALP"
    assert row["display_name"] == "Alkaline Phosphatase"


@pytest.mark.asyncio
async def test_the_clinician_board_draws_one_trend(client: AsyncClient, db):
    _, uid = await _patient(client, db)
    await _both_spellings(db, uid)

    detail = await patient_board._labs_detail(db, uid, 90)

    assert [s["label"] for s in detail.series] == ["Alkaline Phosphatase"]
    assert len(detail.series[0]["points"]) == 2


@pytest.mark.asyncio
async def test_a_reimported_report_finds_the_result_on_file_under_the_other_spelling(client: AsyncClient, db):
    token, uid = await _patient(client, db)
    # The fixture report was collected 03/14/2026 and prints ALK PHOS 637 U/L.
    db.add(_result(uid, date(2026, 3, 14), 637.0, "ALP"))
    await db.commit()

    r = await client.post("/api/v1/pdf/parse-document",
                          files={"file": ("labs.pdf", wrapped_range_pdf(), "application/pdf")},
                          headers=_auth(token))

    assert r.status_code == 200, r.text[:300]
    alk = next(i for i in r.json()["items"] if i["test_name"] == "Alkaline Phosphatase")
    assert alk["dedupe_status"] == "duplicate"
    assert alk["accepted"] is False
