"""The parser learns what reviewers decide — end to end, or not at all.

WHY THE ROUND TRIP IS THE TEST THAT MATTERS. `telemetry.register_sink` was
built, documented as the corpus ALAFIA distils from, and never called: every
pair hit `if not _sinks: return` and was dropped, and nothing failed (§3ay). A
learning store fails the same silent way — it records lessons nobody reads, or
reads keys nobody wrote, and presents as "it just never fires".

Two real defects in this very feature were caught by reasoning about that, and
both are pinned below:

  * `record_review_decisions` originally RECOMPUTED the signature from the
    staged payload, while staging computed it from the parsed row. The payload
    keeps parsed low/high bounds; staging sees the range as the document printed
    it. A range the parser cannot read is present in one and absent in the
    other, so the two derived different digests for the same row.

  * `confirm()` never wrote the reviewer's choice back to `accepted`, so the
    learning step would have recorded what the PARSER proposed rather than what
    the PERSON decided.

Neither would have failed a unit test of either half.
"""

import pytest
from httpx import AsyncClient

from app.services.import_learning import (
    MIN_CONFIRMATIONS,
    SIGNATURE_KEY,
    row_signature,
)
from tests.test_docparse import wrapped_range_pdf


# ── The signature describes a SHAPE, never a measurement ─────────────────────

def test_the_same_shape_with_different_values_matches():
    """Haemoglobin 9.4 and 14.1 are the same SHAPE.

    This is the property that lets one patient's review help the next patient's
    import without either seeing the other's data.
    """
    a = row_signature("HEMOGLOBIN", 9.4, None, "g/dL", "11.7-15.5")[0]
    b = row_signature("HEMOGLOBIN", 14.1, None, "g/dL", "11.7-15.5")[0]
    assert a == b


def test_case_and_spacing_do_not_change_the_signature():
    assert (row_signature("Performing  Laboratory", None, "Information:")[0]
            == row_signature("performing laboratory", None, "Information:")[0])


def test_a_different_structure_is_a_different_signature():
    """A row with a unit and a range is not the same row without them."""
    bare = row_signature("WBC", None, "NONE SEEN")[0]
    structured = row_signature("WBC", None, "NONE SEEN", "/HPF", "< OR = 5")[0]
    assert bare != structured


def test_a_numeric_value_and_a_word_are_different_shapes():
    assert (row_signature("X", 2.0, None)[0]) != (row_signature("X", None, "two")[0])


# ── The loop: stage -> confirm -> the next import knows ──────────────────────

async def _token(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register",
                      json={"email": email, "password": "SecureP@ss123",
                            "full_name": "Test User", "date_of_birth": "1990-01-01"})
    r = await client.post("/api/v1/auth/login",
                          data={"username": email, "password": "SecureP@ss123"})
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _upload(content: bytes, name: str = "labs.pdf"):
    return {"file": (name, content, "application/pdf")}


async def _import_rejecting(client: AsyncClient, token: str, reject_name: str) -> dict:
    """Upload a report, UNTICK one row, confirm. Returns the parse body."""
    parsed = await client.post("/api/v1/pdf/parse-document",
                               files=_upload(wrapped_range_pdf()), headers=_auth(token))
    body = parsed.json()
    keep = [i["item_id"] for i in body["items"] if i["test_name"] != reject_name]
    await client.post(f"/api/v1/pdf/imports/{body['import_id']}/confirm",
                      json={"accepted_item_ids": keep}, headers=_auth(token))
    return body


@pytest.mark.asyncio
class TestTheLoopCloses:
    async def test_staging_stamps_a_signature_on_every_row(self, client: AsyncClient, db):
        """Confirm reads this key back. If staging stops writing it the whole
        loop goes quiet, so it is asserted directly rather than inferred.

        Uses the `db` FIXTURE. `from tests.conftest import TestSession`
        re-executes conftest as a module, which re-runs `_ensure_test_database()`
        and its `new_event_loop().run_until_complete(...)` inside the already
        running loop: `RuntimeError: Cannot run the event loop while another
        loop is running`. Same hazard as a nested `asyncio.run()`.
        """
        from sqlalchemy import select
        from app.models.document_import import DocumentImportItem

        token = await _token(client, "learn1@example.com")
        parsed = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(wrapped_range_pdf()), headers=_auth(token))
        import_id = parsed.json()["import_id"]

        rows = (await db.execute(
            select(DocumentImportItem).where(
                DocumentImportItem.import_id == import_id)
        )).scalars().all()
        assert rows
        assert all((r.payload or {}).get(SIGNATURE_KEY) for r in rows), (
            "a staged row carries no signature — confirm will learn nothing"
        )

    async def test_one_reviewer_is_not_enough_to_act(self, client: AsyncClient):
        """One person's slip must not teach the parser to hide an analyte from
        everybody else."""
        token = await _token(client, "learn2@example.com")
        await _import_rejecting(client, token, "Albumin")

        again = await client.post("/api/v1/pdf/parse-document",
                                  files=_upload(wrapped_range_pdf()), headers=_auth(token))
        albumin = next(i for i in again.json()["items"] if i["test_name"] == "Albumin")
        assert albumin["accepted"] is True, (
            f"a single rejection already changed the default (min {MIN_CONFIRMATIONS})"
        )

    async def test_two_agreeing_reviewers_untick_the_row_next_time(self, client: AsyncClient):
        """The whole point: the parser gets better at THIS lab's template."""
        token = await _token(client, "learn3@example.com")
        await _import_rejecting(client, token, "Albumin")
        await _import_rejecting(client, token, "Albumin")

        again = await client.post("/api/v1/pdf/parse-document",
                                  files=_upload(wrapped_range_pdf()), headers=_auth(token))
        albumin = next(i for i in again.json()["items"] if i["test_name"] == "Albumin")
        assert albumin["accepted"] is False, "the learned verdict did not reach staging"
        assert albumin["note"], "a refusal that cannot explain itself gets ticked past"
        assert "previous reviewers" in albumin["note"].lower()

    async def test_a_row_reviewers_KEPT_is_never_unticked_BY_LEARNING(self, client: AsyncClient):
        """Learning may only ever untick rows reviewers REJECTED.

        Asserted on the NOTE, not on `accepted`. By the third upload the rows
        that were accepted have been written twice, so they arrive as
        DEDUPE_DUPLICATE and are unticked BY DESIGN — nothing to do with
        learning. An earlier version of this test asserted `accepted` and failed
        for that reason: it was measuring dedupe and blaming the learning store.
        """
        token = await _token(client, "learn4@example.com")
        await _import_rejecting(client, token, "Albumin")
        await _import_rejecting(client, token, "Albumin")

        again = await client.post("/api/v1/pdf/parse-document",
                                  files=_upload(wrapped_range_pdf()), headers=_auth(token))
        others = [i for i in again.json()["items"] if i["test_name"] != "Albumin"]
        assert others, "precondition: the document has other rows"
        for item in others:
            assert "previous reviewers" not in (item["note"] or "").lower(), (
                f"learning claimed a verdict on {item['test_name']!r}, which "
                f"reviewers accepted every time"
            )

    async def test_one_patients_lesson_helps_another(self, client: AsyncClient):
        """The signature carries no measurement, so a verdict is shareable.

        This is the reason the table stores a shape and not a value.
        """
        mine = await _token(client, "learn5@example.com")
        theirs = await _token(client, "learn6@example.com")
        await _import_rejecting(client, mine, "Albumin")
        await _import_rejecting(client, mine, "Albumin")

        parsed = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(wrapped_range_pdf()), headers=_auth(theirs))
        albumin = next(i for i in parsed.json()["items"] if i["test_name"] == "Albumin")
        assert albumin["accepted"] is False


@pytest.mark.asyncio
class TestWhatIsNotLearned:
    async def test_a_duplicate_teaches_nothing(self, client: AsyncClient, db):
        """A duplicate arrives unticked BY DESIGN, so leaving it unticked says
        nothing about whether the row is a result."""
        from sqlalchemy import select
        from app.models.import_judgment import DocumentRowJudgment

        token = await _token(client, "learn7@example.com")
        # Import everything twice: the second pass is all duplicates.
        for _ in range(2):
            parsed = await client.post("/api/v1/pdf/parse-document",
                                       files=_upload(wrapped_range_pdf()),
                                       headers=_auth(token))
            body = parsed.json()
            await client.post(f"/api/v1/pdf/imports/{body['import_id']}/confirm",
                              json={}, headers=_auth(token))

        judgments = (await db.execute(select(DocumentRowJudgment))).scalars().all()
        # The first pass may teach "result"; the duplicate pass must add nothing
        # and must never record a furniture verdict.
        assert not [j for j in judgments if j.verdict == "furniture"], (
            "a duplicate was read as a reviewer rejecting the row"
        )

    async def test_a_learning_outage_never_fails_the_import(self, client: AsyncClient, monkeypatch):
        """The rows are already written by then. Losing a lesson costs far less
        than losing the import — §3ah, applied to the learning step."""
        import app.services.document_import_service as svc

        async def _boom(*_a, **_k):
            raise RuntimeError("learning store is down")

        monkeypatch.setattr(svc, "record_review_decisions", _boom)

        token = await _token(client, "learn8@example.com")
        parsed = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(wrapped_range_pdf()), headers=_auth(token))
        confirmed = await client.post(
            f"/api/v1/pdf/imports/{parsed.json()['import_id']}/confirm",
            json={}, headers=_auth(token))
        assert confirmed.status_code == 200
        assert confirmed.json()["total_imported"] > 0

        labs = (await client.get("/api/v1/labs/", headers=_auth(token))).json()
        assert labs, "the import was lost because the learning step failed"
