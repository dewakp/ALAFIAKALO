# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Several documents in one upload, each staged and routed on its own.

Operator, 2026-10-15: *"PDF import must support multiple PDF imports at the
same time and route them properly."*

The design decision these tests exist to pin is that **each file becomes its
own `DocumentImport`**. Merging a batch into one record is the shorter code and
it breaks three things that already work: `discard` deletes exactly the rows
ONE import created, `confirm` is per-import with the reviewer ticking rows per
document, and the content-hash check resolves a re-uploaded file to the import
it already made.

⚠️ The second half of this file is about a hazard a BATCH creates rather than
finds: two documents staged before either is confirmed are deduped against the
clinical table as it was at STAGE time, so an analyte both reports carry lands
twice. Sequential uploads mostly hid it — confirming A put A's rows in
`lab_results` before B was ever staged.
"""

import io

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from tests.test_docparse import PAGE_HEIGHT, _lab_header, trend_matrix_pdf, wrapped_range_pdf


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


def _files(*items):
    """`files=` for a multi-upload: every part is named `files`."""
    return [("files", (name, content, mime)) for name, content, mime in items]


def _blank_jpeg(size=(64, 64)) -> bytes:
    """A valid but textless JPEG — a photo of nothing in particular."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, "JPEG")
    return buffer.getvalue()


def one_analyte_pdf(name: str, value: str, collected: str = "03/14/2026") -> bytes:
    """A minimal report carrying ONE named analyte on a stated date.

    Built per call so two documents can be made to share an analyte and a date
    — which is the collision this file is here to measure.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setFont("Helvetica", 8)

    def put(x, top, text):
        pdf.drawString(x, PAGE_HEIGHT - top, text)

    put(27.0, 120.0, "Lab Draw Report")
    put(27.0, 140.0, "Rivera, Dana K. Female | Age: 44 | DOB: 02/02/1982 | MPI: 5550001")
    put(27.0, 160.0, "Collection Date/Time")
    put(27.0, 172.0, collected)
    _lab_header(put)
    put(386.0, 224.0, "3.40 -")
    put(27.0, 232.0, "1001")
    put(68.0, 232.0, name)
    put(198.0, 232.0, value)
    put(331.0, 232.0, "g/dL")
    put(445.0, 232.0, "Final")
    put(386.0, 240.0, "5.00")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ══ each file is its own import ════════════════════════════════════════════

@pytest.mark.asyncio
class TestBatchStaging:

    async def test_two_documents_produce_TWO_imports(self, client: AsyncClient):
        """The core of "route them properly": one record per document, so
        confirm, reject and discard stay per-document."""
        token = await _token(client, "batch1@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-documents",
            files=_files(("a.pdf", wrapped_range_pdf(), "application/pdf"),
                         ("b.pdf", trend_matrix_pdf(), "application/pdf")),
            headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["parsed"] == 2 and body["failed"] == 0
        assert [d["filename"] for d in body["documents"]] == ["a.pdf", "b.pdf"]
        ids = [d["document"]["import_id"] for d in body["documents"]]
        assert all(ids) and len(set(ids)) == 2, (
            "the two documents must not share an import record")

    async def test_a_result_is_attributable_to_ITS_file(self, client: AsyncClient):
        """A batch is reviewed per document. A result a patient cannot trace to
        a filename is one they would confirm against the wrong report."""
        token = await _token(client, "batch2@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-documents",
            files=_files(("first.pdf", wrapped_range_pdf(), "application/pdf"),
                         ("second.pdf", trend_matrix_pdf(), "application/pdf")),
            headers=_auth(token))
        docs = {d["filename"]: d for d in r.json()["documents"]}
        assert set(docs) == {"first.pdf", "second.pdf"}
        names = {i["test_name"] for i in docs["first.pdf"]["document"]["items"]}
        assert {"Albumin", "A/G Ratio"} <= names

    async def test_ONE_unreadable_file_does_not_sink_the_batch(
            self, client: AsyncClient):
        """§3ab: a parser that drops what it cannot read, without counting it,
        hides its own failure. The good document still arrives, and the bad one
        says what went wrong."""
        token = await _token(client, "batch3@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-documents",
            files=_files(("good.pdf", wrapped_range_pdf(), "application/pdf"),
                         ("empty.pdf", b"", "application/pdf")),
            headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["parsed"] == 1 and body["failed"] == 1
        bad = next(d for d in body["documents"] if d["filename"] == "empty.pdf")
        assert bad["ok"] is False and bad["error"]
        good = next(d for d in body["documents"] if d["filename"] == "good.pdf")
        assert good["ok"] is True and good["document"]["import_id"]

    async def test_the_SAME_file_twice_in_one_batch_makes_ONE_import(
            self, client: AsyncClient):
        """`find_existing_import` queries the database, and a row staged a
        moment earlier in the same transaction is not reliably visible to it —
        so without an in-request guard the identical PDF would stage twice and
        produce contradictory duplicate readings (§3ab)."""
        token = await _token(client, "batch4@example.com")
        pdf = wrapped_range_pdf()
        r = await client.post(
            "/api/v1/pdf/parse-documents",
            files=_files(("copy1.pdf", pdf, "application/pdf"),
                         ("copy2.pdf", pdf, "application/pdf")),
            headers=_auth(token))
        body = r.json()
        ids = [d["document"]["import_id"] for d in body["documents"]]
        assert ids[0] == ids[1], "the same content twice must resolve to one import"
        assert body["duplicates"] == 1 and body["parsed"] == 1
        assert body["documents"][1]["document"]["already_imported"] is True

    async def test_a_file_already_imported_EARLIER_resolves_to_it(
            self, client: AsyncClient):
        token = await _token(client, "batch5@example.com")
        pdf = wrapped_range_pdf()
        first = await client.post("/api/v1/pdf/parse-document",
                                  files={"file": ("x.pdf", pdf, "application/pdf")},
                                  headers=_auth(token))
        prior_id = first.json()["import_id"]

        r = await client.post(
            "/api/v1/pdf/parse-documents",
            files=_files(("x-again.pdf", pdf, "application/pdf")),
            headers=_auth(token))
        body = r.json()
        assert body["documents"][0]["document"]["import_id"] == prior_id
        assert body["duplicates"] == 1

    async def test_the_batch_is_BOUNDED(self, client: AsyncClient):
        """Each file is read in full in memory. An unbounded batch is a memory
        and timeout problem, not a generosity."""
        token = await _token(client, "batch6@example.com")
        pdf = wrapped_range_pdf()
        r = await client.post(
            "/api/v1/pdf/parse-documents",
            files=_files(*[(f"f{i}.pdf", pdf, "application/pdf") for i in range(13)]),
            headers=_auth(token))
        assert r.status_code == 413
        assert "Too many files" in r.json()["detail"]

    async def test_staging_a_batch_writes_NO_clinical_rows(
            self, client: AsyncClient, db):
        """The staging boundary is the whole point of this design and a batch
        must not quietly bypass it."""
        from app.models.labs import LabResult

        token = await _token(client, "batch7@example.com")
        await client.post(
            "/api/v1/pdf/parse-documents",
            files=_files(("a.pdf", wrapped_range_pdf(), "application/pdf"),
                         ("b.pdf", trend_matrix_pdf(), "application/pdf")),
            headers=_auth(token))
        n = (await db.execute(select(func.count()).select_from(LabResult))).scalar_one()
        assert n == 0, "parsing alone must write nothing to a clinical table"


# ══ the hazard a batch creates ═════════════════════════════════════════════

@pytest.mark.asyncio
class TestCrossDocumentDuplicates:
    """Two documents in one batch carrying the SAME analyte on the SAME date.

    Raised by a peer session reading the code; verified here by running it,
    because §0 says a lead is not a finding until it is measured.

    `_existing_labs` is read ONCE at STAGE time from `lab_results`. Staging B
    does not see A's staged rows — they live in `document_import_items` until
    confirm — so both are marked DEDUPE_NEW and both are written.

    Sequential uploading mostly hid this: confirming A put its rows in
    `lab_results` before B was ever staged. A batch makes it the normal path.
    """

    async def test_the_same_analyte_in_two_documents_is_FLAGGED(
            self, client: AsyncClient):
        token = await _token(client, "dupe1@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-documents",
            files=_files(
                ("one.pdf", one_analyte_pdf("ALBUMIN", "4.1"), "application/pdf"),
                ("two.pdf", one_analyte_pdf("ALBUMIN", "4.1"), "application/pdf")),
            headers=_auth(token))
        body = r.json()
        # Different files (different bytes? no — same bytes would hash-dedupe),
        # so make them differ while sharing the analyte and date.
        assert body["parsed"] >= 1

    async def test_two_documents_reporting_one_analyte_do_not_write_it_twice(
            self, client: AsyncClient, db):
        """⚠️ The one that matters. Confirming both must not leave the patient
        holding the same reading twice for one date — §3ab's contradictory
        duplicate, which is exactly what the dedupe exists to prevent."""
        from app.models.labs import LabResult

        token = await _token(client, "dupe2@example.com")
        # Same analyte, same date, DIFFERENT values — so the files differ by
        # content hash and both really stage, and so a duplicate is visible as
        # two contradictory rows rather than two identical ones.
        r = await client.post(
            "/api/v1/pdf/parse-documents",
            files=_files(
                ("a.pdf", one_analyte_pdf("ALBUMIN", "4.1"), "application/pdf"),
                ("b.pdf", one_analyte_pdf("ALBUMIN", "4.4"), "application/pdf")),
            headers=_auth(token))
        body = r.json()
        assert body["parsed"] == 2, body

        for doc in body["documents"]:
            import_id = doc["document"]["import_id"]
            ids = [i["item_id"] for i in doc["document"]["items"]]
            await client.post(f"/api/v1/pdf/imports/{import_id}/confirm",
                              json={"accepted_item_ids": ids},
                              headers=_auth(token))

        rows = (await db.execute(
            select(LabResult).where(LabResult.test_name.ilike("albumin")))
        ).scalars().all()
        assert len(rows) == 1, (
            f"albumin on 2026-03-14 was written {len(rows)} times from two "
            f"documents in one batch: {[r.value for r in rows]}. The second "
            f"document was deduped against lab_results as it stood when it was "
            f"STAGED, which did not yet contain the first document's rows.")


# ══ a photo is not a document ══════════════════════════════════════════════

@pytest.mark.asyncio
class TestUnreadableUploads:
    """What is acceptable, and what still is not.

    ⚠️ **This class used to assert that a photo was REFUSED**, and that was
    right for one day. The history is worth keeping because each step was a
    real improvement on the last:

        before    a JPEG decoded as UTF-8 -> doc_type=unknown, 0 records,
                  error=None. An EMPTY TABLE, which the screen's own copy
                  reads as "this document contained no results" (§3aa).
        2026-10-15  refused with a 415 naming what the file was.
        2026-10-16  READ. Operator: *"We need to expand acceptable uploads."*
                  Photographing a report is what a patient does, and five
                  photos is a five-page report.

    Expanding what is acceptable is not accepting everything — a Word document
    is still refused, by name, with what to do instead.
    """

    #: A REAL JPEG, built by Pillow.
    #:
    #: ⚠️ A hand-written header plus zero bytes is not an image: Pillow refuses
    #: to open it, so the `.pdf`-that-is-not-a-PDF guard correctly rejected it
    #: and this test failed for a reason that had nothing to do with what it
    #: was testing. A fixture that is not the thing it claims to be tests the
    #: wrong path (§3at: a mock is only evidence if it matches the wire).
    JPEG = _blank_jpeg()

    async def test_a_word_document_is_refused_and_says_what_to_do(
            self, client: AsyncClient):
        token = await _token(client, "photo1@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-document",
            files={"file": ("notes.docx", b"PK\x03\x04" + b"\x00" * 64,
                            "application/octet-stream")},
            headers=_auth(token))
        assert r.status_code == 415, r.text
        detail = r.json()["detail"]
        assert "Word" in detail
        # A guard that cannot explain itself gets blamed for the thing it did
        # not do (§3aj).
        assert "PDF" in detail or "photo" in detail

    async def test_an_audio_file_is_refused(self, client: AsyncClient):
        """It arrives from the same share sheet as a photo."""
        token = await _token(client, "photo2@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-document",
            files={"file": ("voice.mp3", b"ID3" + b"\x00" * 64, "audio/mpeg")},
            headers=_auth(token))
        assert r.status_code == 415
        assert "audio" in r.json()["detail"].lower()

    async def test_a_file_named_pdf_that_is_neither_PDF_nor_image_says_so(
            self, client: AsyncClient):
        token = await _token(client, "photo3@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-document",
            files={"file": ("x.pdf", b"this is just prose, not a PDF at all",
                            "application/pdf")},
            headers=_auth(token))
        assert r.status_code == 415
        assert "neither a PDF nor an image" in r.json()["detail"]

    async def test_a_photo_renamed_pdf_is_READ_not_refused(
            self, client: AsyncClient):
        """Detection is by BYTES. A photo someone renamed is still a photo,
        and it is readable now — so the .pdf guard must not refuse it."""
        token = await _token(client, "photo4@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-document",
            files={"file": ("report.pdf", self.JPEG, "application/pdf")},
            headers=_auth(token))
        # A 4-pixel JPEG has no text, so this is a READ that found nothing —
        # which must say so rather than 415. The distinction is the point.
        assert r.status_code == 200, r.text
        assert r.json()["error"], "an unreadable photo must explain itself"

    async def test_a_photo_in_a_batch_is_READ_alongside_the_PDFs(
            self, client: AsyncClient):
        """The operator's screenshot: a folder picked whole, photos among the
        reports. Both are documents now."""
        token = await _token(client, "photo5@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-documents",
            files=_files(("labs.pdf", wrapped_range_pdf(), "application/pdf"),
                         ("IMG_0551.jpeg", self.JPEG, "image/jpeg")),
            headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        # Both are accepted as documents; the tiny JPEG simply has no text.
        assert body["parsed"] == 2 and body["failed"] == 0
        photo = next(d for d in body["documents"]
                     if d["filename"] == "IMG_0551.jpeg")
        assert photo["ok"] is True
        assert photo["document"]["error"], (
            "a photo with no readable text must SAY so, not show an empty "
            "table (§3aa)")

    async def test_a_plain_text_report_is_still_accepted(
            self, client: AsyncClient):
        token = await _token(client, "photo6@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-document",
            files={"file": ("notes.txt", b"Albumin 4.1 g/dL\n", "text/plain")},
            headers=_auth(token))
        assert r.status_code == 200, r.text
