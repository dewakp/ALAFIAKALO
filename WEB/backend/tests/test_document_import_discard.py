"""Taking a bad import back out — and touching nothing else.

WHY THIS ENDPOINT EXISTS. §3ab: a parser fix does not repair what it already
imported, and re-importing makes it worse. Dedupe is keyed on
`(test_date, lower(test_name))` and the commit path only ever INSERTS, so a
corrected reading lands beside the wrong one and the patient holds two
contradictory values for one date. The documented remedy has always been
"delete first, then re-import" — and until now the only way to do that was
somebody running SQL against production.

WHY THIS FILE IS LONGER THAN THE FEATURE. `discard` is the only code in the
import pipeline that DELETES from a clinical table. Every test here is about
what it must NOT take with it: a reading the patient typed by hand, a reading
from a different document, and above all another patient's record. The
`user_id` clause in that delete is belt-and-braces — the import is already
loaded for this patient — and belt-and-braces is exactly the kind of thing that
gets "simplified" later by someone who has not read this docstring.
"""

import pytest
from httpx import AsyncClient

from tests.test_docparse import wrapped_range_pdf


async def _token(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123",
              "full_name": "Test User", "date_of_birth": "1990-01-01"},
    )
    r = await client.post("/api/v1/auth/login",
                          data={"username": email, "password": "SecureP@ss123"})
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _upload(content: bytes, name: str = "labs.pdf"):
    return {"file": (name, content, "application/pdf")}


async def _import_a_document(client: AsyncClient, token: str, content: bytes) -> int:
    """Upload, confirm, and return the import id. Leaves rows on the record."""
    parsed = await client.post("/api/v1/pdf/parse-document",
                               files=_upload(content), headers=_auth(token))
    import_id = parsed.json()["import_id"]
    confirmed = await client.post(f"/api/v1/pdf/imports/{import_id}/confirm",
                                  json={}, headers=_auth(token))
    assert confirmed.json()["total_imported"] > 0, "nothing was imported to discard"
    return import_id


@pytest.mark.asyncio
class TestDiscardRemovesWhatItWrote:
    async def test_the_rows_this_import_created_are_deleted(self, client: AsyncClient):
        token = await _token(client, "disc1@example.com")
        import_id = await _import_a_document(client, token, wrapped_range_pdf())

        before = (await client.get("/api/v1/labs/", headers=_auth(token))).json()
        assert before, "precondition: the import wrote rows"

        r = await client.post(f"/api/v1/pdf/imports/{import_id}/discard",
                              headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert body["total_removed"] == len(before)
        assert body["status"] == "discarded"

        after = (await client.get("/api/v1/labs/", headers=_auth(token))).json()
        assert after == [], "rows survived the discard"

    async def test_the_message_says_what_was_removed(self, client: AsyncClient):
        """A destructive action that reports nothing is the §3ab shell failure."""
        token = await _token(client, "disc2@example.com")
        import_id = await _import_a_document(client, token, wrapped_range_pdf())

        body = (await client.post(f"/api/v1/pdf/imports/{import_id}/discard",
                                  headers=_auth(token))).json()
        assert body["removed"].get("lab_results", 0) > 0
        assert "lab_results" in (body["message"] or "")


@pytest.mark.asyncio
class TestDiscardTouchesNothingElse:
    async def test_a_hand_entered_result_survives(self, client: AsyncClient):
        """The patient typed this one. No import may ever remove it."""
        token = await _token(client, "disc3@example.com")
        mine = await client.post(
            "/api/v1/labs/",
            json={"test_date": "2026-01-01", "test_name": "Typed By Hand",
                  "value": 1.23, "unit": "mg/dL"},
            headers=_auth(token),
        )
        assert mine.status_code == 201

        import_id = await _import_a_document(client, token, wrapped_range_pdf())
        await client.post(f"/api/v1/pdf/imports/{import_id}/discard", headers=_auth(token))

        names = {r["test_name"] for r in
                 (await client.get("/api/v1/labs/", headers=_auth(token))).json()}
        assert names == {"Typed By Hand"}, f"hand-entered row was collateral: {names}"

    async def test_another_patients_identical_import_survives(self, client: AsyncClient):
        """The clause that matters most.

        Two patients import the SAME document, so the rows carry the same names,
        the same dates and the same values. Only the ids differ. A discard that
        matched on anything but the recorded row id would take both.
        """
        mine = await _token(client, "disc4@example.com")
        theirs = await _token(client, "disc5@example.com")
        content = wrapped_range_pdf()

        my_import = await _import_a_document(client, mine, content)
        await _import_a_document(client, theirs, content)

        their_before = (await client.get("/api/v1/labs/", headers=_auth(theirs))).json()
        assert their_before

        await client.post(f"/api/v1/pdf/imports/{my_import}/discard", headers=_auth(mine))

        their_after = (await client.get("/api/v1/labs/", headers=_auth(theirs))).json()
        assert len(their_after) == len(their_before), "another patient lost rows"
        assert (await client.get("/api/v1/labs/", headers=_auth(mine))).json() == []

    async def test_one_patient_cannot_discard_another_import(self, client: AsyncClient):
        mine = await _token(client, "disc6@example.com")
        theirs = await _token(client, "disc7@example.com")
        import_id = await _import_a_document(client, mine, wrapped_range_pdf())

        r = await client.post(f"/api/v1/pdf/imports/{import_id}/discard",
                              headers=_auth(theirs))
        assert r.status_code == 404, "an import must not be reachable by another account"
        assert (await client.get("/api/v1/labs/", headers=_auth(mine))).json()


@pytest.mark.asyncio
class TestDiscardEnablesReimport:
    async def test_the_same_file_can_be_uploaded_again(self, client: AsyncClient):
        """The whole point. `find_existing_import` skips discarded imports, or
        the patient is handed back the import they just deleted and the
        re-import can never happen."""
        token = await _token(client, "disc8@example.com")
        content = wrapped_range_pdf()
        import_id = await _import_a_document(client, token, content)
        await client.post(f"/api/v1/pdf/imports/{import_id}/discard", headers=_auth(token))

        again = await client.post("/api/v1/pdf/parse-document",
                                  files=_upload(content), headers=_auth(token))
        body = again.json()
        assert body["already_imported"] is False, "the discarded import was handed back"
        assert body["import_id"] != import_id, "a discarded import was reused"
        assert body["items"], "the document did not parse on re-upload"

    async def test_reimporting_after_a_discard_does_not_duplicate(self, client: AsyncClient):
        """Delete first, then re-import — and end with ONE copy, not two."""
        token = await _token(client, "disc9@example.com")
        content = wrapped_range_pdf()
        first = await _import_a_document(client, token, content)
        count = len((await client.get("/api/v1/labs/", headers=_auth(token))).json())

        await client.post(f"/api/v1/pdf/imports/{first}/discard", headers=_auth(token))
        second = await _import_a_document(client, token, content)
        assert second != first

        after = (await client.get("/api/v1/labs/", headers=_auth(token))).json()
        assert len(after) == count, f"re-import duplicated rows: {count} -> {len(after)}"


@pytest.mark.asyncio
class TestDiscardRefusesWhatItCannotDo:
    async def test_discarding_an_unconfirmed_import_is_refused(self, client: AsyncClient):
        """Nothing was written, so "removed 0 rows" would read as success."""
        token = await _token(client, "disc10@example.com")
        parsed = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(wrapped_range_pdf()), headers=_auth(token))
        import_id = parsed.json()["import_id"]

        r = await client.post(f"/api/v1/pdf/imports/{import_id}/discard",
                              headers=_auth(token))
        assert r.status_code == 409
        assert "nothing to remove" in r.json()["detail"].lower()

    async def test_discarding_twice_is_safe(self, client: AsyncClient):
        """A retry, or two taps on a phone. The second must not error or delete."""
        token = await _token(client, "disc11@example.com")
        import_id = await _import_a_document(client, token, wrapped_range_pdf())

        first = await client.post(f"/api/v1/pdf/imports/{import_id}/discard",
                                  headers=_auth(token))
        assert first.status_code == 200 and first.json()["total_removed"] > 0

        second = await client.post(f"/api/v1/pdf/imports/{import_id}/discard",
                                   headers=_auth(token))
        # Already discarded is no longer CONFIRMED, so it is refused by status
        # rather than silently deleting nothing.
        assert second.status_code == 409
