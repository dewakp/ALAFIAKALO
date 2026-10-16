# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""OCR readiness has to reach an OPERATOR, not only the patient.

`ocr.available()` shipped with two callers, both on the parse path, so an
unreadable capability told the one person who cannot fix it — *"text
recognition is not available on the server"* — and nothing told anyone who
could. OPEN_ITEMS 50.

These pin the half that was missing. Run against the pre-fix tree, the four
`document_ocr` tests fail at `no document_ocr check in …` (the probe did not
exist) and the `status()` tests fail at import (the function did not exist), so
all of them are regression guards rather than coverage — unlike §3al's PII test
that passed against the broken implementation.
"""

import pytest

from app.core.admin_auth import require_admin
from app.main import app
from app.services.docparse import ocr

HEALTH = "/api/v1/admin/health"


def _check(payload: dict, name: str) -> dict:
    for c in payload.get("checks", []):
        if c["name"] == name:
            return c
    raise AssertionError(
        f"no {name} check in {[c['name'] for c in payload.get('checks', [])]}")


class _Admin:
    id = 1
    email = "dew@6igma.com"
    is_active = True
    is_superuser = True


@pytest.fixture
def as_admin():
    app.dependency_overrides[require_admin] = lambda: _Admin()
    yield
    app.dependency_overrides.pop(require_admin, None)


# ── status() reports what is actually installed ────────────────────────────

def test_status_reports_the_real_toolchain_in_this_container():
    """Not a mock. This is the measurement the deploy had to do by hand."""
    s = ocr.status()
    assert s["available"] is True, s["reason"]
    assert s["version"] and not str(s["version"]).startswith("unreadable")
    assert isinstance(s["languages"], list) and "eng" in s["languages"]
    assert s["poppler"], "pdftoppm is not on PATH"
    assert s["min_dpi"] == ocr.MIN_DPI


def test_osd_is_reported_because_rotation_depends_on_it():
    """`_upright()` needs `osd`, and without it a sideways page reads as
    NOTHING with no error — §48 measured 0 records at 90/180/270."""
    s = ocr.status()
    assert s["osd_present"] is True, (
        f"the orientation pack is missing; languages={s['languages']}")


def test_status_never_raises_when_the_engine_is_absent(monkeypatch):
    """A readiness reporter that throws cannot report."""
    monkeypatch.setattr(ocr, "available", lambda: (False, "no binary"))
    s = ocr.status()
    assert s["available"] is False
    assert s["reason"] == "no binary"
    assert s["languages"] == []


def test_unreadable_languages_do_not_look_like_none_installed(monkeypatch):
    """§3aa: "we could not ask" and "none are installed" are opposite facts,
    and the second would make a working install look broken."""
    import pytesseract

    def _boom(config=""):
        raise RuntimeError("tessdata unreadable")

    monkeypatch.setattr(pytesseract, "get_languages", _boom)
    s = ocr.status()
    assert s["languages"] != []
    assert "unreadable" in str(s["languages"])
    assert s["osd_present"] is False


# ── the probe makes it visible, and degrades ──────────────────────────────

@pytest.mark.asyncio
async def test_health_reports_document_ocr_when_everything_is_present(client, as_admin):
    resp = await client.get(HEALTH)
    assert resp.status_code == 200
    check = _check(resp.json(), "document_ocr")
    assert check["status"] == "ok", check["detail"]
    assert "tesseract" in check["detail"] and "langs" in check["detail"]


@pytest.mark.asyncio
async def test_an_unavailable_engine_is_DEGRADED_not_quiet(client, as_admin, monkeypatch):
    """§3ah's PayPal rail: a declared input nobody can read must not be silent.
    The upload surface accepts photographs on all three clients."""
    monkeypatch.setattr(ocr, "status", lambda: {
        "available": False, "reason": "the tesseract binary is not available",
        "version": None, "languages": [], "osd_present": False,
        "poppler": "/usr/bin/pdftoppm", "min_dpi": 400,
    })
    body = (await client.get(HEALTH)).json()
    check = _check(body, "document_ocr")
    assert check["status"] == "error"
    assert "refused" in check["detail"]
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_a_missing_osd_pack_is_degraded(client, as_admin, monkeypatch):
    """The words would still be read, so this is the case most likely to be
    waved through — and it is a SILENT total loss on a sideways page."""
    monkeypatch.setattr(ocr, "status", lambda: {
        "available": True, "reason": None, "version": "5.5.0",
        "languages": ["eng"], "osd_present": False,
        "poppler": "/usr/bin/pdftoppm", "min_dpi": 400,
    })
    body = (await client.get(HEALTH)).json()
    check = _check(body, "document_ocr")
    assert check["status"] == "error"
    assert "orientation" in check["detail"]
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_missing_poppler_says_photographs_still_import(client, as_admin, monkeypatch):
    """Two inputs fail independently; collapsing them would overstate the
    outage and send someone hunting the wrong capability (§3ae's 503 vs 502)."""
    monkeypatch.setattr(ocr, "status", lambda: {
        "available": True, "reason": None, "version": "5.5.0",
        "languages": ["eng", "osd"], "osd_present": True,
        "poppler": None, "min_dpi": 400,
    })
    check = _check((await client.get(HEALTH)).json(), "document_ocr")
    assert check["status"] == "error"
    assert "SCANNED PDF" in check["detail"]
    assert "photographs still" in check["detail"]
