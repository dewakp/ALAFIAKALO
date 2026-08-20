"""Upload → review → import, end to end.

The staging step is the point of this design. A parser is sometimes wrong, and
`lab_results` is the wrong place to find that out: once a bad reading is in
there it is indistinguishable from one a lab actually reported, and every
average, trend and clinician card built on it inherits the error.

So these tests assert the boundary as much as the happy path — that parsing
alone writes no clinical rows, that a duplicate is not silently written twice,
and that a document which could not be read says so instead of returning an
empty list that reads as "this patient has no results".
"""

import pytest
from httpx import AsyncClient

from tests.test_docparse import trend_matrix_pdf, wrapped_range_pdf


async def _token(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecureP@ss123",
              "full_name": "Test User", "date_of_birth": "1990-01-01"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "SecureP@ss123"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _upload(content: bytes, name: str = "labs.pdf"):
    return {"file": (name, content, "application/pdf")}


@pytest.mark.asyncio
class TestParseAndStage:
    async def test_upload_returns_the_readings_it_found(self, client: AsyncClient):
        token = await _token(client, "doc1@example.com")
        r = await client.post("/api/v1/pdf/parse-document",
                              files=_upload(wrapped_range_pdf()), headers=_auth(token))
        assert r.status_code == 200
        body = r.json()

        assert body["doc_type"] == "lab_report"
        assert body["import_id"] is not None
        assert body["error"] is None

        names = {i["test_name"] for i in body["items"]}
        assert {"Albumin", "Alk Phos", "A/G Ratio"} <= names

    async def test_fields_use_the_names_the_clients_decode(self, client: AsyncClient):
        """Web, iOS and Android all decode these exact keys.

        They were previously served as doctor_name / raw_text / items[].name,
        so a successful parse still rendered as a blank screen everywhere.
        """
        token = await _token(client, "doc2@example.com")
        r = await client.post("/api/v1/pdf/parse-document",
                              files=_upload(wrapped_range_pdf()), headers=_auth(token))
        body = r.json()

        for key in ("patient_name", "report_date", "lab_name",
                    "ordering_physician", "raw_text_preview", "items"):
            assert key in body, f"clients expect {key}"
        for key in ("test_name", "value", "unit", "reference_range", "is_abnormal"):
            assert key in body["items"][0], f"clients expect items[].{key}"

    async def test_the_wrapped_reference_range_survives_to_the_api(self, client: AsyncClient):
        token = await _token(client, "doc3@example.com")
        r = await client.post("/api/v1/pdf/parse-document",
                              files=_upload(wrapped_range_pdf()), headers=_auth(token))
        albumin = next(i for i in r.json()["items"] if i["test_name"] == "Albumin")
        assert albumin["reference_range"] == "3.4 – 4.8"
        assert albumin["is_abnormal"] is False

    async def test_an_abnormal_result_is_marked(self, client: AsyncClient):
        token = await _token(client, "doc4@example.com")
        r = await client.post("/api/v1/pdf/parse-document",
                              files=_upload(wrapped_range_pdf()), headers=_auth(token))
        alk = next(i for i in r.json()["items"] if i["test_name"] == "Alk Phos")
        assert alk["is_abnormal"] is True

    async def test_parsing_writes_no_clinical_rows(self, client: AsyncClient):
        """Nothing reaches lab_results until the patient confirms."""
        token = await _token(client, "doc5@example.com")
        await client.post("/api/v1/pdf/parse-document",
                          files=_upload(wrapped_range_pdf()), headers=_auth(token))

        labs = await client.get("/api/v1/labs/", headers=_auth(token))
        assert labs.json() == []

    async def test_reuploading_the_same_file_does_not_stage_it_twice(self, client: AsyncClient):
        token = await _token(client, "doc6@example.com")
        content = wrapped_range_pdf()

        first = await client.post("/api/v1/pdf/parse-document",
                                  files=_upload(content), headers=_auth(token))
        second = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(content, "again.pdf"), headers=_auth(token))

        assert first.json()["import_id"] == second.json()["import_id"]
        assert second.json()["already_imported"] is True

    async def test_a_trend_grid_is_read_as_a_flowsheet(self, client: AsyncClient):
        token = await _token(client, "doc7@example.com")
        r = await client.post("/api/v1/pdf/parse-document",
                              files=_upload(trend_matrix_pdf(), "worksheet.pdf"),
                              headers=_auth(token))
        body = r.json()
        assert body["items"], "the matrix layout produced no readings"
        assert any(i["test_name"] == "Hemoglobin" for i in body["items"])


@pytest.mark.asyncio
class TestUnreadableDocuments:
    async def test_a_scan_says_it_needs_ocr(self, client: AsyncClient):
        """An error must never arrive as an empty result list."""
        from tests.test_docparse import _pdf

        token = await _token(client, "doc8@example.com")
        r = await client.post("/api/v1/pdf/parse-document",
                              files=_upload(_pdf(lambda put: None), "scan.pdf"),
                              headers=_auth(token))
        body = r.json()
        assert body["items"] == []
        assert body["error"], "a failed parse must explain itself"
        assert "text recognition" in body["error"].lower()

    async def test_an_empty_upload_is_rejected(self, client: AsyncClient):
        token = await _token(client, "doc9@example.com")
        r = await client.post("/api/v1/pdf/parse-document",
                              files=_upload(b"", "empty.pdf"), headers=_auth(token))
        assert r.status_code == 400


@pytest.mark.asyncio
class TestConfirm:
    async def test_confirming_writes_the_readings(self, client: AsyncClient):
        token = await _token(client, "doc10@example.com")
        parsed = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(wrapped_range_pdf()), headers=_auth(token))
        import_id = parsed.json()["import_id"]

        confirmed = await client.post(
            f"/api/v1/pdf/imports/{import_id}/confirm", json={}, headers=_auth(token)
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["total_imported"] > 0

        labs = await client.get("/api/v1/labs/", headers=_auth(token))
        names = {row["test_name"] for row in labs.json()}
        assert "Albumin" in names

    async def test_imported_values_keep_their_range_and_flag(self, client: AsyncClient):
        token = await _token(client, "doc11@example.com")
        parsed = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(wrapped_range_pdf()), headers=_auth(token))
        await client.post(f"/api/v1/pdf/imports/{parsed.json()['import_id']}/confirm",
                          json={}, headers=_auth(token))

        labs = (await client.get("/api/v1/labs/", headers=_auth(token))).json()
        albumin = next(row for row in labs if row["test_name"] == "Albumin")
        assert albumin["value"] == 4.6
        assert albumin["reference_range_low"] == 3.4
        assert albumin["reference_range_high"] == 4.8
        assert albumin["is_abnormal"] is False

    async def test_only_the_selected_rows_are_written(self, client: AsyncClient):
        token = await _token(client, "doc12@example.com")
        parsed = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(wrapped_range_pdf()), headers=_auth(token))
        body = parsed.json()
        chosen = next(i for i in body["items"] if i["test_name"] == "Albumin")

        confirmed = await client.post(
            f"/api/v1/pdf/imports/{body['import_id']}/confirm",
            json={"accepted_item_ids": [chosen["item_id"]]}, headers=_auth(token),
        )
        assert confirmed.json()["total_imported"] == 1

        labs = (await client.get("/api/v1/labs/", headers=_auth(token))).json()
        assert {row["test_name"] for row in labs} == {"Albumin"}

    async def test_a_second_confirm_is_refused(self, client: AsyncClient):
        token = await _token(client, "doc13@example.com")
        parsed = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(wrapped_range_pdf()), headers=_auth(token))
        import_id = parsed.json()["import_id"]

        await client.post(f"/api/v1/pdf/imports/{import_id}/confirm", json={}, headers=_auth(token))
        again = await client.post(f"/api/v1/pdf/imports/{import_id}/confirm",
                                  json={}, headers=_auth(token))
        assert again.status_code == 409

    async def test_rejecting_writes_nothing(self, client: AsyncClient):
        token = await _token(client, "doc14@example.com")
        parsed = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(wrapped_range_pdf()), headers=_auth(token))
        await client.post(f"/api/v1/pdf/imports/{parsed.json()['import_id']}/reject",
                          headers=_auth(token))

        labs = await client.get("/api/v1/labs/", headers=_auth(token))
        assert labs.json() == []


@pytest.mark.asyncio
class TestIsolation:
    async def test_one_patient_cannot_read_another_import(self, client: AsyncClient):
        mine = await _token(client, "doc15@example.com")
        theirs = await _token(client, "doc16@example.com")

        parsed = await client.post("/api/v1/pdf/parse-document",
                                   files=_upload(wrapped_range_pdf()), headers=_auth(mine))
        import_id = parsed.json()["import_id"]

        assert (await client.get(f"/api/v1/pdf/imports/{import_id}",
                                 headers=_auth(theirs))).status_code == 404
        assert (await client.post(f"/api/v1/pdf/imports/{import_id}/confirm",
                                  json={}, headers=_auth(theirs))).status_code == 404


@pytest.mark.asyncio
class TestFlowsheetContract:
    async def test_it_accepts_what_the_clients_actually_send(self, client: AsyncClient):
        """`{session_type, days}` — the previous handler demanded session_id and 422'd."""
        token = await _token(client, "doc17@example.com")
        r = await client.post("/api/v1/pdf/generate-flowsheet",
                              json={"session_type": "hemodialysis", "days": 30},
                              headers=_auth(token))
        assert r.status_code == 200

        body = r.json()
        for key in ("title", "generated_at", "content", "session_count"):
            assert key in body, f"clients decode {key}"

    async def test_an_empty_window_is_explained_not_blank(self, client: AsyncClient):
        token = await _token(client, "doc18@example.com")
        r = await client.post("/api/v1/pdf/generate-flowsheet",
                              json={"session_type": "hemodialysis", "days": 7},
                              headers=_auth(token))
        body = r.json()
        assert body["session_count"] == 0
        assert "No sessions found" in body["content"]

    async def test_the_pdf_endpoint_returns_a_pdf(self, client: AsyncClient):
        token = await _token(client, "doc19@example.com")
        r = await client.get("/api/v1/pdf/reports/flowsheet.pdf",
                             params={"session_type": "hemodialysis", "days": 30},
                             headers=_auth(token))
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
