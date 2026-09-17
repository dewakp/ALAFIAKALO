"""Canonical clinical vocabulary for document parsing.

Seeded from the curated map in `scripts/import_pdf_labs.py`, which was built by
hand against a real DaVita corpus. It lives here so the API and the batch script
share one vocabulary instead of drifting apart.

An analyte missing from this table is not an error — `normalize` keeps the name
the document used and marks the record low-confidence, and the local model may
be asked to propose a canonical form. Nothing is silently discarded.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

#: Report abbreviation (upper-cased, whitespace-collapsed) → canonical name.
ANALYTE_NAMES: dict[str, str] = {
    "A/G": "A/G Ratio",
    "A/G RATIO": "A/G Ratio",
    "ALB": "Albumin",
    "ALBUMIN": "Albumin",
    # Alkaline phosphatase, printed three ways. One patient's history was stored
    # as "ALP" until July 2025 and "Alk Phos" after, when the report format
    # changed — one analyte that every reader treated as two tests.
    "ALP": "Alkaline Phosphatase",
    "ALK PHOS": "Alkaline Phosphatase",
    "ALKALINE PHOSPHATASE": "Alkaline Phosphatase",
    "ALT/SGPT": "ALT/SGPT",
    "AST/SGOT": "AST/SGOT",
    "BASO": "Basophils %",
    "BASOPHILS": "Basophils %",
    "BASOS-ABS": "Basophils Abs",
    "B12": "Vitamin B12",
    "BUN": "BUN",
    "BUN - POST": "BUN Post",
    "BUN-P": "BUN Post",
    "CA": "Calcium",
    "CA CORR": "Calcium Corrected",
    "CA CORRECTED": "Calcium Corrected",
    "CA*PO4 CORRCTD": "Ca*PO4 Product Corrected",
    "CA*POCOR": "Ca*PO4 Product Corrected",
    "CA/P": "Ca*PO4 Product",
    "CA/PHOS PRODUCT": "Ca*PO4 Product",
    "CA-POST": "Calcium Post",
    "CALCIUM": "Calcium",
    "CHLORIDE": "Chloride",
    "CHOL": "Cholesterol",
    "CHOL/HDL": "Cholesterol/HDL Ratio",
    "CHOL/HDL RATIO": "Cholesterol/HDL Ratio",
    "CHOLESTEROL": "Cholesterol",
    "CO2": "CO2",
    "CRE": "Creatinine",
    "CREATININE": "Creatinine",
    "CREATININE - POST": "Creatinine Post",
    "EOS": "Eosinophils %",
    "EOSINOPHILS": "Eosinophils %",
    "EOS-ABS": "Eosinophils Abs",
    "EOSINS-ABS": "Eosinophils Abs",
    "FE": "Iron",
    "FERR": "Ferritin",
    "FERRITIN": "Ferritin",
    "FOLATE": "Folate",
    "GLU": "Glucose",
    "GLUCOSE": "Glucose",
    "GLOBULIN": "Globulin",
    "HCT": "Hematocrit",
    "HCT%": "Hematocrit",
    "HEMATOCRIT": "Hematocrit",
    "HGB": "Hemoglobin",
    "HEMOGLOBIN": "Hemoglobin",
    "HEMOGLOBIN-POST": "Hemoglobin Post",
    "HEMOGLOBIN MID": "Hemoglobin Mid",
    "HDL": "HDL Cholesterol",
    "HDL CHOLESTEROL": "HDL Cholesterol",
    "IRON": "Iron",
    "IRON SATURATION": "Iron Saturation",
    "IRON SAT": "Iron Saturation",
    "K+": "Potassium",
    "LDH": "LDH",
    "LDL": "LDL Cholesterol",
    "LDL CALCULATED": "LDL Cholesterol",
    "LYMPH": "Lymphocytes %",
    "LYMPHOCYTES": "Lymphocytes %",
    "LYMPHS-ABS": "Lymphocytes Abs",
    "MCH": "MCH",
    "MCHC": "MCHC",
    "MCV": "MCV",
    "MG": "Magnesium",
    "MONO": "Monocytes %",
    "MONOCYTES": "Monocytes %",
    "MONOS-ABS": "Monocytes Abs",
    "NA": "Sodium",
    "NEUT": "Neutrophils %",
    "NEUTROPHILS": "Neutrophils %",
    "NEUTS-ABS": "Neutrophils Abs",
    "NPCR": "NPCR",
    "PHOS": "Phosphorus",
    "PHOSPHORUS": "Phosphorus",
    "PLATELET": "Platelet Count",
    "PLATELET COUNT": "Platelet Count",
    "PLT": "Platelet Count",
    "POTASSIUM": "Potassium",
    "POTASSIUM - POST": "Potassium Post",
    "PTH-INTACT": "PTH (Intact)",
    "PTH INTACT": "PTH (Intact)",
    "PTH-I": "PTH (Intact)",
    "PTH": "PTH (Intact)",
    "RBC": "RBC",
    "RDW": "RDW",
    "SODIUM": "Sodium",
    "SPKT/V": "spKt/V",
    "STDKT/V (DIAL)": "stdKt/V Dialysis",
    "STDKT/V TOTAL": "stdKt/V Total",
    "TIBC": "TIBC",
    "TOTAL PROTEIN": "Total Protein",
    "TRANSFERRIN": "Transferrin",
    "TRIGLYCERIDE": "Triglycerides",
    "TRIGLYCERIDES": "Triglycerides",
    "URR%": "URR%",
    "VLDL": "VLDL",
    "VITAMIN D (25-OH)": "Vitamin D 25-OH",
    "VITAMIN D": "Vitamin D 25-OH",
    "WBC": "WBC",
    "ABSL. RETIC CT.": "Absolute Reticulocyte Count",
    "ABSOLUTE RETIC": "Absolute Reticulocyte Count",
    "ABSOLUTE RETIC COUNT": "Absolute Reticulocyte Count",
    "RETIC COUNT": "Reticulocyte Count",
    "ALUMINUM - BLOOD": "Aluminum Blood",
    "A1C": "HbA1c",
    "HEMOGLOBIN A1C": "HbA1c",
    "HBA1C": "HbA1c",
    "GFR": "GFR",
    "EGFR": "eGFR",
    "EKT/V": "eKt/V",
    "PSA": "PSA",
    "TSH": "TSH",
    "FREE T4": "Free T4",
    "T4 FREE": "Free T4",
    "URIC ACID": "Uric Acid",
    "HEPATITIS B SURFACE AB": "Hepatitis B Surface Ab",
    "HEPATITIS B SURFACE AG": "Hepatitis B Surface Ag",
    "HEPATITIS C AB": "Hepatitis C Ab",
    "HIV": "HIV",
}

#: (category, substrings). First match wins, so order matters.
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Hematology", (
        "HEMOGLOBIN", "HEMATOCRIT", "HGB", "HCT", "RBC", "WBC", "PLATELET", "MCV",
        "MCH", "MCHC", "RDW", "NEUT", "LYMPH", "MONO", "EOS", "BASO", "RETIC",
        "IRON", "FERRITIN", "TIBC", "TRANSFERRIN",
    )),
    ("Kidney Function", (
        "BUN", "CREATININE", "GFR", "EGFR", "URR", "KT/V", "STDKT", "SPKT", "NPCR",
    )),
    ("Lipid Panel", ("CHOLESTEROL", "HDL", "LDL", "TRIGLYCERIDE", "VLDL", "CHOL")),
    # Liver is tested before Mineral on purpose: "ALK PHOS" contains "PHOS", and
    # with the other order alkaline phosphatase — a liver enzyme — was filed
    # under bone chemistry.
    ("Liver & Protein", (
        "ALT", "AST", "ALP", "ALK PHOS", "ALKALINE PHOSPHATASE", "BILIRUBIN",
        "TOTAL PROTEIN", "ALBUMIN",
        "A/G", "LDH", "GLOBULIN",
    )),
    ("Mineral & Bone", (
        "CALCIUM", "PHOSPHORUS", "PTH", "VITAMIN D", "CA*PO4", "CA CORRECTED",
        "CA/PHOS", "MAGNESIUM",
    )),
    ("Electrolytes", ("SODIUM", "POTASSIUM", "CHLORIDE", "CO2", "GLUCOSE")),
    ("Infectious Disease", ("HEPATITIS", "HIV")),
    ("Thyroid", ("TSH", "T4", "T3")),
    ("Vitamins", ("B12", "FOLATE")),
    ("Toxicology", ("ALUMINUM",)),
    ("Diabetes", ("A1C",)),
]

_WHITESPACE = re.compile(r"\s+")


def lookup_key(raw_name: str) -> str:
    return _WHITESPACE.sub(" ", raw_name.strip().upper())


def canonical_name(raw_name: str) -> tuple[str, bool]:
    """Return (canonical name, was_recognised).

    An unrecognised analyte keeps the document's own wording — losing the name
    would be worse than not standardising it.
    """
    key = lookup_key(raw_name)
    if key in ANALYTE_NAMES:
        return ANALYTE_NAMES[key], True

    # Retry without a trailing qualifier: a trend grid prints
    # "CA*PO4 CORRCTD (Calc)" where a column report prints "CA*PO4 CORRCTD".
    stripped = _WHITESPACE.sub(" ", re.sub(r"\s*\([^()]*\)\s*$", "", key)).strip()
    if stripped and stripped in ANALYTE_NAMES:
        return ANALYTE_NAMES[stripped], True

    return raw_name.strip(), False


def display_name(raw_name: str) -> str:
    """What to call a stored result: its analyte's canonical name where known.

    An unrecognised name keeps its own wording, exactly as `canonical_name` does.
    """
    return canonical_name(raw_name or "")[0]


def analyte_key(raw_name: str) -> str:
    """One identity per analyte, whatever the report printed.

    A stored `test_name` is the document's wording and stays that way. Anything
    that groups, charts or de-duplicates results compares this instead: on the
    dev copy of production 219 stored names are 155 analytes, and 50 of those are
    split across two or three spellings ("ALP" / "Alk Phos", "K+" / "Potassium").
    Compared raw, each spelling read as a separate test holding part of the
    history.
    """
    return display_name(raw_name).casefold()


def preferred_name(raw_names: Iterable[str], fallback: str | None = None) -> str:
    """The name for results already known to be one analyte, oldest first.

    The vocabulary's name when any spelling is recognised; otherwise `fallback`,
    or the newest wording. The newest wording alone labelled a merged magnesium
    series "MAGNESIUM" — the one spelling of three the vocabulary has no entry for.
    """
    names = [n for n in raw_names if n]
    for raw in reversed(names):
        canonical, recognised = canonical_name(raw)
        if recognised:
            return canonical
    if fallback:
        return fallback
    return names[-1].strip() if names else ""


def category_for(test_name: str) -> str:
    upper = test_name.upper()
    for category, needles in CATEGORY_RULES:
        if any(needle in upper for needle in needles):
            return category
    return "Other"
