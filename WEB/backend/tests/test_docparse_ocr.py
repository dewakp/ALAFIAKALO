# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Reading a document that has no text layer — a photo, or a scan.

Operator, 2026-10-16, on the upload screen refusing five photos of a report:
*"We need to expand acceptable uploads."*

⚠️ **Two of these tests exist because the first implementation was clinically
WRONG, not merely inaccurate.** Both faults produced a confident, plausible,
incorrect analyte — the thing §3ab exists to keep out of `lab_results`, where
a wrong value is indistinguishable from a real one forever after.
"""

import io

import pytest

from tests.test_docparse import wrapped_range_pdf

pytest.importorskip("pytesseract", reason="OCR bindings not installed here")
pytest.importorskip("pdf2image", reason="pdf2image not installed here")


def _photo_of(pdf: bytes, dpi: int = 200, quality: int = 88) -> bytes:
    """A photograph of the document, as a patient would send it.

    Rendered at a deliberately LOW dpi and saved as lossy JPEG: a clean
    high-resolution render would not exercise the path a phone camera does.
    """
    from pdf2image import convert_from_bytes

    image = convert_from_bytes(pdf, dpi=dpi)[0]
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def _records(parsed):
    return [(r.test_name, r.value, r.unit) for r in parsed.records]


@pytest.mark.asyncio
class TestAPhotoReadsLikeTheDocument:

    async def test_a_photo_of_a_report_parses_AS_the_report(self):
        """The whole point: the same document, photographed, yields the same
        analytes and the same values."""
        from app.services.docparse import pipeline

        pdf = wrapped_range_pdf()
        from_pdf = await pipeline.parse(pdf, "labs.pdf", "application/pdf")
        from_photo = await pipeline.parse(_photo_of(pdf), "IMG_0553.jpeg",
                                          "image/jpeg")

        assert from_photo.extraction_method == "ocr"
        assert from_photo.doc_type == from_pdf.doc_type == "lab_report"
        assert _records(from_photo) == _records(from_pdf), (
            "a photograph of a document must not report different analytes "
            "from the document")

    async def test_ALK_PHOS_is_not_read_as_PHOSPHORUS(self):
        """⚠️ The clinical misidentification, pinned by name.

        Tesseract's DEFAULT segmentation reads a lab table COLUMN-MAJOR, so the
        layout parser grouped only the last word of each test name: `ALK PHOS`
        became `PHOS`, which the analyte dictionary resolved to **Phosphorus**.

        Alkaline phosphatase is a liver enzyme reported in U/L with a reference
        around 46-116. Phosphorus is a mineral a dialysis patient is managed
        on, in mg/dL. 637 is ordinary for the first and impossible for the
        second — and it would have landed in the record as a phosphorus result.

        `--psm 6` is what separates these, which is why it is not a tuning
        preference.
        """
        from app.services.docparse import pipeline

        parsed = await pipeline.parse(_photo_of(wrapped_range_pdf()),
                                      "p.jpeg", "image/jpeg")
        names = {r.test_name for r in parsed.records}
        assert "Alkaline Phosphatase" in names
        assert "Phosphorus" not in names, (
            "a liver enzyme was recorded as the mineral a dialysis patient is "
            "managed on")

    async def test_a_decimal_point_survives(self):
        """⚠️ At a 300-dpi render this fixture's A/G ratio `1.8` came back as
        `18` — AT CONFIDENCE 85, which no threshold would have caught. The
        upscale in `_prepare` is what fixes it, so this fails if anyone lowers
        `MIN_DPI` for speed."""
        from app.services.docparse import pipeline

        parsed = await pipeline.parse(_photo_of(wrapped_range_pdf()),
                                      "p.jpeg", "image/jpeg")
        ratio = next(r for r in parsed.records if "Ratio" in (r.test_name or ""))
        assert ratio.value == pytest.approx(1.8), (
            f"read {ratio.value} — a lost decimal point turns 1.8 into 18")

    async def test_the_boxes_are_in_PDF_POINTS_not_pixels(self):
        """⚠️ The first version left OCR boxes in pixels, reasoning that the
        parser only compares positions to each other. It does not: §3ab records
        the name/value boundary at `x_mid 162.0` and separates "a gap inside a
        name (2.0 pt)" from "the gap to the real value (29.0 pt)". At 400 dpi
        one point is ~5.5 pixels, so every one of those figures was
        meaningless."""
        from app.services.docparse import extract

        doc = extract.extract(_photo_of(wrapped_range_pdf()), "p.jpeg",
                              "image/jpeg")
        page = doc.pages[0]
        assert page.width == pytest.approx(612.0), "not a letter page in points"
        # And a word sits where it does on the PDF, not 5x further right.
        albumin = next(w for w in page.words if w.text.upper() == "ALBUMIN")
        assert 60 < albumin.x0 < 80, albumin.x0


@pytest.mark.asyncio
class TestNothingFromAnImageIsPreTicked:

    async def test_every_OCR_row_is_staged_UNTICKED(self, db):
        """The protection is the review step, not a confidence threshold —
        because the `1.8` → `18` corruption scored 85.

        §3ab's own pattern for a row that might be wrong: *"an implausible row
        arrives unticked with its reason"*, applied to a whole document.
        """
        from app.models.user import User
        from app.services import document_import_service as importer
        from app.services.docparse import pipeline

        user = User(email="ocr-stage@example.test",
                    hashed_password="x", full_name="Ada Demo")
        db.add(user)
        await db.flush()

        parsed = await pipeline.parse(_photo_of(wrapped_range_pdf()),
                                      "p.jpeg", "image/jpeg")
        record = await importer.stage(db, user.id, parsed)
        await db.flush()
        await db.refresh(record, ["items"])

        assert record.items, "the photo staged nothing at all"
        assert all(not i.accepted for i in record.items), (
            "a row recognised from an image was pre-ticked for import")
        assert all("Recognised from an image" in (i.error or "")
                   for i in record.items), "the reason must travel with the row"

    async def test_a_PDF_is_still_pre_ticked_normally(self, db):
        """The quarantine must not leak onto documents that have real text —
        it would make every ordinary import a manual re-entry job."""
        from app.models.user import User
        from app.services import document_import_service as importer
        from app.services.docparse import pipeline

        user = User(email="pdf-stage@example.test",
                    hashed_password="x", full_name="Ada Demo")
        db.add(user)
        await db.flush()

        parsed = await pipeline.parse(wrapped_range_pdf(), "labs.pdf",
                                      "application/pdf")
        record = await importer.stage(db, user.id, parsed)
        await db.flush()
        await db.refresh(record, ["items"])
        assert any(i.accepted for i in record.items)


@pytest.mark.asyncio
class TestTheUploadBoundary:

    async def test_a_photo_is_ACCEPTED_now(self, client):
        """It was a 415 until today. Refusing was better than the empty table
        it replaced, and still wrong."""
        token = await _token(client, "ocr-upload@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-document",
            files={"file": ("IMG_0553.jpeg", _photo_of(wrapped_range_pdf()),
                            "image/jpeg")},
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["import_id"] is not None
        assert {i["test_name"] for i in body["items"]} >= {"Albumin"}
        # Nothing pre-ticked.
        assert not any(i["accepted"] for i in body["items"])

    async def test_a_WORD_document_is_still_refused_and_says_so(self, client):
        """Expanding what is acceptable is not accepting everything."""
        token = await _token(client, "ocr-docx@example.com")
        r = await client.post(
            "/api/v1/pdf/parse-document",
            files={"file": ("notes.docx", b"PK\x03\x04" + b"\x00" * 64,
                            "application/vnd.openxmlformats-officedocument"
                            ".wordprocessingml.document")},
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 415
        assert "Word" in r.json()["detail"]


async def _token(client, email: str) -> str:
    await client.post("/api/v1/auth/register",
                      json={"email": email, "password": "SecureP@ss123",
                            "full_name": "Test User",
                            "date_of_birth": "1990-01-01"})
    r = await client.post("/api/v1/auth/login",
                          data={"username": email, "password": "SecureP@ss123"})
    return r.json()["access_token"]


@pytest.mark.asyncio
class TestASidewaysPageIsTurnedUpright:
    """Found on the operator's REAL photographs, 2026-10-16.

    A five-page report laid on a desk and photographed: several pages are
    sideways, because that is how paper ends up when you turn to it.

    ⚠️ **Rotation is not degradation, it is total loss.** Measured on the test
    fixture, same page, four orientations, before the fix:

        0deg    records=4
        90deg   records=0
        180deg  records=0
        270deg  records=0

    `--psm 6` assumes horizontal lines, so a sideways page reads as nothing.
    """

    @pytest.mark.parametrize("angle", [0, 90, 180, 270])
    async def test_a_page_reads_the_same_whichever_way_it_was_photographed(
            self, angle):
        from pdf2image import convert_from_bytes

        from app.services.docparse import pipeline

        page = convert_from_bytes(wrapped_range_pdf(), dpi=200)[0]
        turned = page.rotate(angle, expand=True)
        buffer = io.BytesIO()
        turned.convert("RGB").save(buffer, "JPEG", quality=88)

        parsed = await pipeline.parse(buffer.getvalue(), "p.jpeg", "image/jpeg")
        names = [r.test_name for r in parsed.records]
        assert names == ["A/G Ratio", "Albumin", "Alkaline Phosphatase",
                         "ACTUAL DAYS/WEEK TREATED"], (
            f"a page photographed at {angle} degrees read as {names}")

    async def test_an_upright_page_is_NOT_turned(self):
        """⚠️ The dangerous direction. Tesseract's orientation guess carries a
        confidence, and on a degraded image it is noise: a 1024-px thumbnail of
        a genuinely sideways page scored **0.43 and said "rotate 0"**. Acting
        on a guess that weak would turn upright pages over and lose documents
        that currently work, so a low-confidence answer is ignored."""
        from PIL import Image

        from app.services.docparse import ocr

        # A blank page gives the detector nothing to go on.
        blank = Image.new("L", (1700, 2200), "white")
        _image, turned = ocr._upright(blank)
        assert turned == 0, "an unreadable page must not be rotated on a guess"


@pytest.mark.asyncio
class TestAnUnreadablePhotoSaysSo:

    async def test_a_photo_too_poor_to_read_reports_it(self):
        """⚠️ Measured on the operator's real photographs: at 1024 px on the
        long edge, every page produced **0 records**. The text came back as
        fragments — "tment", "Detal", "eport" from "Treatment Details Report" —
        because upscaling a thumbnail cannot invent detail that was never
        captured.

        The result that matters is that it FAILED HONESTLY: `ok=False`, zero
        records, and a stated reason. Nothing garbage reached staging, and the
        screen does not show an empty table that reads as "this document
        contained no results" (§3aa).
        """
        from PIL import Image

        from app.services.docparse import pipeline

        # Noise, not a document.
        import random
        random.seed(7)
        noise = Image.new("L", (900, 1200))
        noise.putdata([random.randint(0, 255) for _ in range(900 * 1200)])
        buffer = io.BytesIO()
        noise.convert("RGB").save(buffer, "JPEG", quality=60)

        parsed = await pipeline.parse(buffer.getvalue(), "blurry.jpeg",
                                      "image/jpeg")
        assert not parsed.records
        assert parsed.ok is False
        assert parsed.error_detail, "an unreadable photo must explain itself"
