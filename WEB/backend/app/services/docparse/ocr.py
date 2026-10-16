# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Words and geometry from a document that has no text layer.

Operator, 2026-10-16, on the upload screen refusing five photos of a report:
*"We need to expand acceptable uploads."* Refusing was better than the empty
table it replaced, and it is still the wrong answer — photographing a report is
what a patient actually does, and five photos is a five-page report.

Two inputs arrive here, and they were the same problem all along:

  * a PHOTO — JPEG, PNG, HEIC
  * a SCANNED PDF — `extract.py` has detected these as `needs_ocr` since it was
    written, and nothing could act on it, so they failed exactly like a photo

**Everything runs in this container.** That is the decisive property, not a
convenience: §3al records that a lab-report photo carries the patient's name,
address and record number in its header, that `scrub_payload` redacts a message
only when its content is a string so image bytes could never be redacted, and
that *"whether a photo or a recording may reach a third party at all is a
product decision"*. Tesseract makes that decision unnecessary — nothing leaves.

It is also DETERMINISTIC. A vision model asked to read a potassium value can
invent a plausible one, and §3ab exists because a wrong value in `lab_results`
is indistinguishable from a real one forever after.

⚠️ **OCR IS NOT TRUSTED, AND THE CALLER MUST NOT TREAT IT AS READ TEXT.**
Measured on the test fixture at tesseract's handling of a 300-dpi render: the
A/G ratio **`1.8` came back as `18`** — a decimal point lost, **at confidence
85**. No confidence threshold catches that, because the engine is confident and
wrong. Raising the render to 400 dpi recovered it under every page segmentation
mode tried, which is why `MIN_DPI` is 400 and not a rounder number — but a
phone photo is not a clean render, so the resolution fixes the measured case
and promises nothing about the next one.

The protection is therefore not a threshold. It is that **every row from an
OCR'd document is staged UNTICKED**, with the reason on it, so a person reads
the value against the paper before it becomes a clinical record. That is §3ab's
own pattern for a row that might be wrong — *"nothing is deleted: an
implausible row arrives unticked with its reason"* — applied to a whole
document rather than a row.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Measured, not chosen. See the module docstring: at 300 dpi the fixture's
#: `1.8` was read as `18` at confidence 85; at 400 it reads correctly under
#: every `--psm` tried.
MIN_DPI = 400

#: A page rendered much larger than this gains nothing and costs memory. A
#: letter page at 400 dpi is 3400x4400, so this leaves generous headroom for a
#: phone photo without letting a 100-megapixel image through unscaled.
MAX_PIXELS = 40_000_000

#: Below this, tesseract's own score says it is guessing. Kept as a SIGNAL on
#: the word, never as a gate — the `1.8` → `18` corruption scored 85.
LOW_CONFIDENCE = 60

#: What this module can open. Checked against the BYTES by the caller; these
#: are for reporting, not detection.
IMAGE_KINDS = ("JPEG", "PNG", "HEIC", "HEIF", "TIFF", "BMP", "WEBP")


def available() -> tuple[bool, str | None]:
    """Is OCR usable in this process? Reports WHY not, rather than failing late.

    §3ae's rule about a transport gated on its own credential, applied to a
    binary: an unconfigured capability that silently does nothing is how the
    PayPal rail was advertised and unbuyable for weeks.
    """
    try:
        import pytesseract
    except ImportError:
        return False, "pytesseract is not installed in this image"
    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:  # noqa: BLE001 — any failure here means unusable
        return False, f"the tesseract binary is not available ({type(exc).__name__})"
    return True, None


#: Below this, tesseract's orientation guess is not evidence. Measured: a clean
#: rendered page scores 4.6-7.1 whichever way it is turned, while a 1024-px
#: thumbnail of a REAL sideways photo scored **0.43 and said "rotate 0"** — it
#: could not tell, and acting on that would have turned an upright page.
MIN_ORIENTATION_CONF = 2.0

#: The language pack `image_to_osd` needs. It is NOT the same thing as a
#: recognition language: `eng` reads the words, `osd` decides which way up the
#: page is. See `status()` for why its absence has to be reported.
OSD_TRAINEDDATA = "osd"


def status() -> dict:
    """What an OPERATOR needs to know about OCR, in one call.

    `available()` reports usability to the PARSE PATH, which turns it into a
    sentence for the patient — *"text recognition is not available on the
    server"*. That is the right message and the wrong audience: it told the one
    person who cannot fix it, and nothing told anyone who could. OPEN_ITEMS 50,
    and this function is the fix — the shape of `push.status()`, for the same
    reason §3ah's PayPal rail needed one.

    Three capabilities fail INDEPENDENTLY, so they are reported separately
    rather than collapsed into one boolean (§3aa):

    * **the engine** — no tesseract, and every photograph and scan is refused;
    * **`osd`** — the recognition languages are present, the page-orientation
      pack is not, so `_upright()` silently gives up and a sideways page reads
      as NOTHING. Measured in §48: 4 records upright, **0** at 90/180/270. The
      failure is invisible — the `except` in `_upright` logs at DEBUG and
      returns the page unturned;
    * **poppler** — tesseract is fine and `pdf2image` cannot rasterise, so
      PHOTOGRAPHS still import and SCANNED PDFs do not.

    Nothing here raises. The caller decides what is degraded, because that
    judgement depends on what the upload surface currently accepts.
    """
    import shutil

    ok, why = available()
    out: dict = {
        "available": ok,
        "reason": why,
        "version": None,
        "languages": [],
        "osd_present": False,
        "poppler": shutil.which("pdftoppm"),
        "min_dpi": MIN_DPI,
    }
    if not ok:
        return out

    import pytesseract

    try:
        out["version"] = str(pytesseract.get_tesseract_version())
    except Exception as exc:  # noqa: BLE001 — a version we cannot read is not fatal
        out["version"] = f"unreadable ({type(exc).__name__})"
    try:
        langs = sorted(pytesseract.get_languages(config=""))
    except Exception as exc:  # noqa: BLE001
        # Do NOT report an empty list here: "no languages installed" and "we
        # could not ask" are opposite facts (§3aa), and the first would make a
        # working install look broken.
        out["languages"] = f"unreadable ({type(exc).__name__})"
        return out
    out["languages"] = langs
    out["osd_present"] = OSD_TRAINEDDATA in langs
    return out


def _upright(image):
    """Turn a sideways page the right way up, or leave it exactly as it is.

    ⚠️ **Rotation is total, not partial.** Measured on the test fixture, same
    page, four orientations:

        0deg    records=4
        90deg   records=0
        180deg  records=0
        270deg  records=0

    `--psm 6` assumes horizontal lines, so a page photographed sideways — which
    is what happens when someone lays a report on a desk and turns to it —
    reads as nothing at all. Tesseract's own orientation detection gets the
    angle right every time on a legible image (90 -> 90, 180 -> 180,
    270 -> 270), so the fix is to ask it.

    It is asked, never assumed: a low-confidence guess is IGNORED rather than
    acted on, because rotating a page that was already upright would turn a
    working import into a blank one.
    """
    try:
        import pytesseract

        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        angle = int(osd.get("rotate", 0) or 0)
        confidence = float(osd.get("orientation_conf", 0) or 0)
    except Exception as exc:  # noqa: BLE001 — OSD is an aid, never a gate
        logger.debug("orientation detection unavailable: %s", exc)
        return image, 0

    if angle % 360 == 0 or confidence < MIN_ORIENTATION_CONF:
        return image, 0
    # `rotate` is how far to turn the image to make it upright, clockwise;
    # PIL rotates counter-clockwise, hence the negation.
    return image.rotate(-angle, expand=True), angle


def _prepare(image):
    """Upscale so small text is legible, and flatten to greyscale.

    A phone photo of a letter page is often around 300 dpi equivalent once
    cropped — which is exactly the resolution that lost a decimal point. Short
    of knowing the physical page size, the honest proxy is the pixel height: a
    letter page at `MIN_DPI` is 11 x 400 = 4400 px tall, so anything shorter is
    scaled up to it.
    """
    from PIL import Image

    target_height = int(11 * MIN_DPI)
    width, height = image.size
    if height < target_height:
        scale = target_height / float(height)
        if width * height * scale * scale <= MAX_PIXELS:
            image = image.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.LANCZOS,
            )
    # Greyscale helps the engine and costs nothing; it is not thresholding,
    # which would destroy faint print on a phone photo.
    return image.convert("L")


#: "Assume a single uniform block of text", and it is load-bearing.
#:
#: ⚠️ Tesseract's DEFAULT segmentation reads a lab table COLUMN-MAJOR — it
#: finds each column as its own block, so the word order runs
#: `CODE LAB TEST NAME … RESULT 18 4.6 637H …`. The layout parser then grouped
#: only the LAST word of each test name, and the result was a clinical
#: misidentification: `ALK PHOS` became `PHOS`, which the analyte dictionary
#: resolved to **Phosphorus** — a mineral a dialysis patient is managed on,
#: carrying 637 U/L, a figure impossible for phosphorus and ordinary for
#: alkaline phosphatase.
#:
#: Measured on the test fixture, same photo, three modes:
#:
#:     default   3 records   'PHOS'     -> Phosphorus            637.0
#:     --psm 4   3 records   'PHOS'     -> Phosphorus            637.0
#:     --psm 6   4 records   'ALK PHOS' -> Alkaline Phosphatase  637.0
#:
#: psm 6 matches the PDF path exactly, analyte for analyte. The mode is not a
#: tuning preference; changing it changes which analyte a row claims to be.
_PSM = "--psm 6"


def words_from_image(image) -> list[dict]:
    """One dict per recognised word: text, box, confidence.

    The box is in PIXELS of the prepared image. The caller scales it into the
    coordinate space the layout parser expects — the parser only ever compares
    positions to each other, so the unit does not matter as long as it is
    consistent within a page.
    """
    import pytesseract
    from pytesseract import Output

    upright, turned = _upright(image)
    if turned:
        logger.info("rotated a sideways page %s degrees before reading it", turned)
    prepared = _prepare(upright)
    data = pytesseract.image_to_data(prepared, output_type=Output.DICT,
                                     config=_PSM)

    out: list[dict] = []
    for index, text in enumerate(data.get("text", [])):
        token = (text or "").strip()
        if not token:
            continue
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            confidence = -1.0
        left = float(data["left"][index])
        top = float(data["top"][index])
        out.append({
            "text": token,
            "x0": left,
            "x1": left + float(data["width"][index]),
            "top": top,
            "bottom": top + float(data["height"][index]),
            "confidence": confidence,
        })
    return out, prepared.size


def open_image(content: bytes):
    """Decode an image, including HEIC. Returns None if it is not one."""
    import io

    from PIL import Image

    try:
        # Registers HEIC/HEIF with Pillow. iPhones shoot HEIC by default, so
        # without this the most likely file a patient sends is unreadable.
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        logger.debug("pillow-heif not installed; HEIC photos cannot be read")

    try:
        image = Image.open(io.BytesIO(content))
        image.load()
        return image
    except Exception:  # noqa: BLE001 — not an image is an ordinary answer
        return None
