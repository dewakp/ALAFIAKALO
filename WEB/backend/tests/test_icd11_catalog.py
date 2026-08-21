"""Guards for the ICD-11 catalog.

The catalog is generated from WHO's published MMS linearization, so the codes
themselves need no defending. What needs defending is everything layered on top:

- **`ICD11_ALIASES` is hand-written.** A typo there puts a wrong-but-real code
  on a patient's condition, or a dangling code that resolves to nothing. Every
  alias target is checked against the generated file.
- **Spelling folding.** WHO writes "haemodialysis" and "tumour"; a US patient
  types "hemodialysis" and "tumor". That gap returned literally zero results
  before folding existed, and nothing else in the suite would notice it coming
  back.
- **Ranking.** The searches below are the ones this app's patients actually
  run — renal, blood disorders, the split-table domains of CLAUDE.md §3aa.
"""

from __future__ import annotations

import pytest

from app.services.icd11_catalog import (
    ICD11_ALIASES,
    ICD11_CODE_RE,
    catalog_version,
    get_icd11_by_code,
    is_valid_icd11_code,
    list_chapters,
    search_icd11,
)


def _codes(results):
    return [entry.code for entry in results]


# ── The generated file ────────────────────────────────────────────────


def test_catalog_loads_the_full_who_linearization():
    # Well under the real count (35,339 at 2025-01) but far above any
    # truncated or partially-written file.
    assert len(search_icd11("a", limit=5)) > 0
    assert "ICD-11 MMS" in catalog_version()
    assert len(list_chapters()) == 28


def test_known_codes_resolve_to_their_who_titles():
    # Spot checks across the domains this app is built around. These titles
    # are WHO's, not paraphrases.
    assert get_icd11_by_code("GB61.5").title == "Chronic kidney disease, stage 5"
    assert get_icd11_by_code("3A51.1").title == "Sickle cell disease without crisis"
    assert get_icd11_by_code("5A11").title == "Type 2 diabetes mellitus"
    assert (
        get_icd11_by_code("3A10.00").title
        == "Haemolytic anaemia due to glucose-6-phosphate dehydrogenase deficiency"
    )


def test_code_lookup_is_case_insensitive_and_rejects_unknowns():
    assert get_icd11_by_code("gb61.5") is not None
    assert get_icd11_by_code("  GB61.5  ") is not None
    assert get_icd11_by_code("") is None
    # Code-SHAPED but not a real code — the distinction that matters, because
    # a regex alone would happily accept this onto a clinical record.
    assert ICD11_CODE_RE.match("ZZ99.9")
    assert not is_valid_icd11_code("ZZ99.9")
    assert is_valid_icd11_code("GB61.5")


# ── The hand-written alias layer ──────────────────────────────────────


@pytest.mark.parametrize("term", sorted(ICD11_ALIASES))
def test_every_alias_points_at_a_real_code(term):
    for code in ICD11_ALIASES[term]:
        assert get_icd11_by_code(code) is not None, (
            f"alias {term!r} points at {code!r}, which is not in the WHO catalog"
        )


@pytest.mark.parametrize(
    "query,expected",
    [
        ("ESRD", "GB61.5"),
        ("end stage renal disease", "GB61.5"),
        ("G6PD", "3A10.00"),
        ("g6pd deficiency", "3A10.00"),
        ("sickle cell", "3A51.1"),
        ("type 2 diabetes", "5A11"),
        ("heart attack", "BA41"),
        ("crohn's", "DD70"),
        ("ulcerative colitis", "DD71"),
        ("kidney", "GB61"),
    ],
)
def test_lay_terms_and_abbreviations_lead_with_the_right_code(query, expected):
    # None of these strings appear in an ICD-11 title; without the alias layer
    # every one of them returns nothing useful.
    assert _codes(search_icd11(query, limit=5))[0] == expected


# ── Spelling ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "american,british",
    [
        ("hemodialysis", "haemodialysis"),
        ("anemia", "anaemia"),
        ("tumor", "tumour"),
        ("esophagus", "oesophagus"),
        ("diarrhea", "diarrhoea"),
        ("edema", "oedema"),
        ("celiac", "coeliac"),
        ("leukemia", "leukaemia"),
    ],
)
def test_us_and_who_spellings_find_the_same_codes(american, british):
    assert _codes(search_icd11(american, limit=8)) == _codes(
        search_icd11(british, limit=8)
    )
    assert search_icd11(american, limit=1), f"{american!r} found nothing"


def test_folded_title_still_matches_exactly():
    # "anemia" must be able to exact-match a title WHO spells "anaemia";
    # comparing the raw title against the folded query silently never did.
    assert _codes(search_icd11("iron deficiency anemia", limit=3))[0] == "3A00"


# ── Ranking ───────────────────────────────────────────────────────────


def test_word_order_does_not_matter():
    # ICD-11 titles it "Type 2 diabetes mellitus"; a substring match on the
    # natural phrasing finds nothing.
    assert _codes(search_icd11("diabetes mellitus type 2", limit=3))[0] == "5A11"


def test_exact_code_query_wins_even_when_residual():
    assert _codes(search_icd11("GB61.Z", limit=3))[0] == "GB61.Z"


def test_code_prefix_lists_the_subtree():
    codes = _codes(search_icd11("GB61", limit=8))
    assert codes[0] == "GB61"
    assert "GB61.5" in codes


def test_residual_codes_do_not_lead():
    # "Kidney failure, unspecified" starts with the query and would otherwise
    # bury chronic kidney disease.
    top = _codes(search_icd11("kidney", limit=3))
    assert "GB61" in top
    assert not get_icd11_by_code(top[0]).is_residual


def test_non_diagnostic_chapters_are_excluded_by_default():
    # Extension codes (X), the functioning supplement (V) and traditional
    # medicine (26) are not diagnoses. "Kidney" (XA6KU8) and "Kidney meridian
    # pattern (TM1)" used to outrank chronic kidney disease.
    for entry in search_icd11("kidney", limit=20):
        assert entry.chapter not in {"X", "V", "26"}

    # ...but stay reachable when the chapter is asked for by name.
    assert search_icd11("kidney", chapter="26", limit=5)


def test_health_status_codes_rank_below_real_diagnoses():
    codes = _codes(search_icd11("kidney", limit=10))
    assert codes.index("GB61") < codes.index("QB22")  # QB22 = "Kidney donor"


def test_partial_query_pulls_aliases_for_typeahead():
    assert _codes(search_icd11("kidn", limit=3))[0] == "GB61"


def test_blank_query_returns_nothing():
    assert search_icd11("") == []
    assert search_icd11("   ") == []


def test_chapter_filter_restricts_results():
    for entry in search_icd11("cancer", chapter="02", limit=10):
        assert entry.chapter == "02"
