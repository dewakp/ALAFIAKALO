"""Tests for the canonical 6IGMA SID (Prompt 1.2). Pure functions — run offline.

Includes a cross-app vector: a SID assembled exactly as FlowSheet's PostgreSQL
`fn_generate_system_id` does, to prove ONE verifier accepts SIDs from either app.
"""

import hashlib

from app.services import canonical_sid as csid
from app.services import sid_service


def test_generate_shape():
    sid = csid.generate_sid("Adewole", "Akpose", "1958-04-12", "male")
    assert len(sid) == 255
    parts = sid.split(".")
    assert len(parts) == 8
    assert parts[0] == "S1"
    assert len(parts[1]) == 3 and len(parts[2]) == 3      # FN3, LN3
    assert len(parts[3]) == 8 and len(parts[4]) == 1      # DOB8, GEN1
    assert len(parts[5]) == 10 and len(parts[6]) == 157   # EPO10, RND157
    assert len(parts[7]) == 64                            # SHA256 hex


def test_segments_decode():
    sid = csid.generate_sid("Adewole", "Akpose", "1958-04-12", "male")
    d = csid.decode_sid(sid)
    assert d["fn3"] == "ADE"
    assert d["ln3"] == "AKP"
    assert d["dob8"] == "19580412"
    assert d["gen1"] == "M"
    assert d["valid"] is True


def test_short_name_padded_and_nonalpha_stripped():
    sid = csid.generate_sid("Jo", "O'Brien-3", "2000-01-02", "female")
    d = csid.decode_sid(sid)
    assert d["fn3"] == "JOX"      # padded
    assert d["ln3"] == "OBR"      # apostrophe/dash/digit stripped
    assert d["gen1"] == "F"


def test_rnd_charset_and_uniqueness():
    a = csid.generate_sid("Ada", "Eze", "1990-05-05", "female")
    b = csid.generate_sid("Ada", "Eze", "1990-05-05", "female")
    assert a != b                                  # random segment differs
    rnd = a.split(".")[6]
    assert all(c in csid.ALPHABET for c in rnd) and len(rnd) == 157


def test_verify_roundtrip_and_tamper():
    sid = csid.generate_sid("Sam", "Lee", "1975-12-31", "male")
    assert csid.verify_sid(sid) is True
    # Flip one char in the random segment → hash no longer matches.
    parts = sid.split(".")
    bad_rnd = ("B" if parts[6][0] != "B" else "C") + parts[6][1:]
    tampered = ".".join(parts[:6] + [bad_rnd, parts[7]])
    assert csid.verify_sid(tampered) is False


def test_gender_codes():
    g = lambda s: csid.decode_sid(csid.generate_sid("A", "B", "2000-01-01", s))["gen1"]
    assert g("male") == "M"
    assert g("female") == "F"
    assert g("intersex") == "X"
    assert g("prefer_not_to_say") == "N"
    assert g(None) == "U"
    assert g("nonbinary") == "U"


def test_cross_app_flowsheet_vector():
    """A SID built like FlowSheet's SQL (payload → sha256 → append) must verify."""
    payload = "S1.ADE.AKP.19580412.M.1700000000." + ("A" * 157)
    flowsheet_sid = payload + "." + hashlib.sha256(payload.encode()).hexdigest()
    assert len(flowsheet_sid) == 255
    assert csid.verify_sid(flowsheet_sid) is True
    # A wrong checksum is rejected.
    assert csid.verify_sid(payload + "." + ("0" * 64)) is False


def test_dob_missing_defaults():
    sid = csid.generate_sid("No", "Dob", None, "male")
    assert csid.decode_sid(sid)["dob8"] == "00000000"


def test_sid_service_delegates():
    sid = sid_service.generate_sid("Adewole", "Akpose", "1958-04-12", "male")
    assert sid_service.verify_sid(sid) is True
    segs = sid_service.get_segments_for_log("Adewole", "Akpose", "1958-04-12", "male")
    assert segs["seg_fn3"] == "ADE" and segs["seg_gen1"] == "M" and segs["seg_version"] == "S1"
    assert sid_service.mask_sid(sid).startswith("S1.ADE.AKP.19580412.M.[RND")
