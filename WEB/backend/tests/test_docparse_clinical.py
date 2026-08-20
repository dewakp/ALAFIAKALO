"""Medication lists and problem lists read through the same geometry.

These share the layout engine with lab reports — a subject column plus
attributes — so the risk is not the columns but the *meaning* put on them:
a dose that is really a frequency, a condition filed under the wrong enum, or a
default silently presented as a finding.

`ChronicCondition.category` and `.severity` are NOT NULL enums, so every
imported condition must resolve to something. Where that something is a
fallback, the record has to say so — otherwise a guess enters the chart as fact.
"""

import pytest

from app.services.docparse.extract import extract
from app.services.docparse.layout import parse_document
from app.services.docparse.records_clinical import (
    condition_category,
    condition_severity,
    looks_like_frequency,
    looks_like_route,
    records_from_condition_table,
    records_from_medication_table,
    split_dose,
)
from tests.test_docparse import _pdf


def medication_list_pdf() -> bytes:
    def draw(put):
        put(27.0, 120.0, "Current Medications")
        put(27.0, 160.0, "MEDICATION")
        put(200.0, 160.0, "DOSE")
        put(300.0, 160.0, "FREQUENCY")
        put(430.0, 160.0, "ROUTE")
        put(500.0, 160.0, "STATUS")

        put(27.0, 180.0, "Calcitriol")
        put(200.0, 180.0, "0.25 mcg")
        put(300.0, 180.0, "once daily")
        put(430.0, 180.0, "oral")
        put(500.0, 180.0, "active")

        put(27.0, 196.0, "Calcium Carbonate")
        put(200.0, 196.0, "500 mg")
        put(300.0, 196.0, "three times daily")
        put(430.0, 196.0, "oral")
        put(500.0, 196.0, "active")

        put(27.0, 212.0, "Lisinopril")
        put(200.0, 212.0, "10 mg")
        put(300.0, 212.0, "once daily")
        put(430.0, 212.0, "oral")
        put(500.0, 212.0, "stopped")

    return _pdf(draw)


def problem_list_pdf() -> bytes:
    def draw(put):
        put(27.0, 120.0, "Discharge Summary — Problem List")
        put(27.0, 160.0, "CONDITION")
        put(260.0, 160.0, "CODE")
        put(340.0, 160.0, "DATE")
        put(440.0, 160.0, "STATUS")

        put(27.0, 180.0, "End-Stage Renal Disease")
        put(260.0, 180.0, "N18.6")
        put(340.0, 180.0, "05/13/2016")
        put(440.0, 180.0, "active severe")

        put(27.0, 196.0, "Type 2 Diabetes Mellitus")
        put(260.0, 196.0, "E11.9")
        put(340.0, 196.0, "03/02/2011")
        put(440.0, 196.0, "active")

        put(27.0, 212.0, "Seasonal Allergic Rhinitis")
        put(260.0, 212.0, "J30.2")
        put(340.0, 212.0, "01/01/2019")
        put(440.0, 212.0, "resolved")

    return _pdf(draw)


class TestDoseParsing:
    @pytest.mark.parametrize("text,expected", [
        ("0.25 mcg", ("0.25", "mcg")),
        ("500 mg", ("500", "mg")),
        ("1,000 IU", ("1000", "IU")),
        ("10mg", ("10", "mg")),
    ])
    def test_amount_and_unit_split(self, text, expected):
        assert split_dose(text) == expected

    def test_microgram_spellings_normalize_to_mcg(self):
        assert split_dose("250 µg")[1] == "mcg"
        assert split_dose("250 ug")[1] == "mcg"

    def test_no_dose_is_not_invented(self):
        assert split_dose("as directed") == (None, None)


class TestFreeTextHints:
    @pytest.mark.parametrize("text", ["once daily", "BID", "every 8 hours", "at bedtime", "PRN"])
    def test_frequency_is_recognised(self, text):
        assert looks_like_frequency(text)

    def test_a_dose_is_not_a_frequency(self):
        assert not looks_like_frequency("500 mg")

    @pytest.mark.parametrize("text", ["oral", "IV", "subcutaneous", "topical"])
    def test_route_is_recognised(self, text):
        assert looks_like_route(text)


class TestMedicationTable:
    @pytest.fixture(scope="class")
    def records(self):
        tables = parse_document(extract(medication_list_pdf(), "meds.pdf"))
        assert tables, "no medication table was reconstructed"
        return {r.name: r for r in records_from_medication_table(tables[0])}

    def test_every_medication_is_read(self, records):
        assert {"Calcitriol", "Calcium Carbonate", "Lisinopril"} <= set(records)

    def test_dose_is_split_into_amount_and_unit(self, records):
        assert (records["Calcitriol"].dosage, records["Calcitriol"].dosage_unit) == ("0.25", "mcg")
        assert (records["Calcium Carbonate"].dosage, records["Calcium Carbonate"].dosage_unit) == ("500", "mg")

    def test_frequency_and_route_are_kept(self, records):
        assert records["Calcitriol"].frequency == "once daily"
        assert records["Calcitriol"].route == "oral"

    def test_a_stopped_drug_is_not_marked_active(self, records):
        """A discontinued prescription imported as active is a clinical error."""
        assert records["Lisinopril"].is_active is False
        assert records["Calcitriol"].is_active is True


class TestConditionCategories:
    @pytest.mark.parametrize("name,expected", [
        ("End-Stage Renal Disease", "renal"),
        ("Chronic Kidney Disease Stage 5", "renal"),
        ("Type 2 Diabetes Mellitus", "diabetes"),
        ("Breast Carcinoma", "cancer"),
        ("Sickle Cell Anemia", "blood_disorder"),
        ("Congestive Heart Failure", "cardiovascular"),
        ("Asthma", "respiratory"),
        ("Systemic Lupus Erythematosus", "autoimmune"),
        ("Hypothyroidism", "endocrine"),
    ])
    def test_known_conditions_map_to_their_category(self, name, expected):
        category, recognised = condition_category(name)
        assert (category, recognised) == (expected, True)

    def test_an_unknown_condition_falls_back_and_admits_it(self):
        """The column is NOT NULL, so a value is required — but not a pretence."""
        category, recognised = condition_category("Idiopathic Widget Syndrome")
        assert category == "other"
        assert recognised is False

    def test_severity_is_read_when_stated(self):
        assert condition_severity("active severe") == ("severe", True)
        assert condition_severity("mild intermittent") == ("mild", True)

    def test_unstated_severity_defaults_and_admits_it(self):
        assert condition_severity("active") == ("moderate", False)


class TestConditionTable:
    @pytest.fixture(scope="class")
    def records(self):
        tables = parse_document(extract(problem_list_pdf(), "problems.pdf"))
        assert tables, "no problem list was reconstructed"
        return {r.condition_name: r for r in records_from_condition_table(tables[0])}

    def test_every_condition_is_read(self, records):
        assert len(records) == 3

    def test_icd10_codes_are_captured(self, records):
        assert records["End-Stage Renal Disease"].icd10_code == "N18.6"
        assert records["Type 2 Diabetes Mellitus"].icd10_code == "E11.9"

    def test_categories_and_severity_resolve(self, records):
        esrd = records["End-Stage Renal Disease"]
        assert esrd.category == "renal"
        assert esrd.severity == "severe"

    def test_a_resolved_problem_is_not_imported_as_active(self, records):
        assert records["Seasonal Allergic Rhinitis"].is_active is False
        assert records["End-Stage Renal Disease"].is_active is True

    def test_diagnosis_dates_are_parsed(self, records):
        assert str(records["End-Stage Renal Disease"].diagnosis_date) == "2016-05-13"

    def test_a_defaulted_severity_is_flagged_for_review(self, records):
        """The reviewer must be able to see which values were assumed."""
        diabetes = records["Type 2 Diabetes Mellitus"]
        assert diabetes.severity == "moderate"
        assert any("Severity was not stated" in note for note in diabetes.parse_notes)
