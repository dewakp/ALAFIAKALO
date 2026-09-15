"""The patient is answered in their language — and a guard's fields never are.

`preferred_language` was saved by the Profile screens and read by nothing that
talks to a patient, in two dialects at once: web stores "en", iOS "English".
"""

import pytest

from app.services.prompt_language import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    conversation_instruction,
    normalise_language,
    patient_language,
    structured_instruction,
)


class _User:
    def __init__(self, preferred_language=None):
        self.preferred_language = preferred_language


@pytest.mark.parametrize("stored,expected", [
    ("en", "en"),            # web
    ("English", "en"),       # iOS
    ("fr-FR", "fr"),
    ("pt_BR", "pt"),
    ("Français", "fr"),
    ("YORÙBÁ", "yo"),
    ("Kiswahili", "sw"),
    ("Engish", None),        # a typo is discarded, not guessed at
    ("xx", None),
    ("", None),
    (None, None),
])
def test_every_stored_and_sent_form_resolves_or_is_refused(stored, expected):
    assert normalise_language(stored) == expected


def test_the_app_language_outranks_the_saved_preference_which_outranks_english():
    assert patient_language(_User("English"), client_language="ha") == "ha"
    assert patient_language(_User("English"), client_language=None) == "en"
    assert patient_language(_User("Français"), client_language="nonsense") == "fr"
    assert patient_language(_User(None), client_language=None) == DEFAULT_LANGUAGE


def test_the_conversation_instruction_detects_and_names_the_fallback_language():
    text = conversation_instruction("yo")
    assert "language the patient writes in" in text
    assert "Yoruba (Yorùbá)" in text


def test_numbers_units_and_drug_names_are_never_translated():
    text = conversation_instruction("fr")
    for kept in ("drug names", "lab test names", "units", "every number"):
        assert kept in text


def test_only_named_prose_fields_follow_the_language_in_structured_output():
    text = structured_instruction("fr", ["description", "rationale"])
    assert '"description", "rationale"' in text and "French (Français)" in text
    assert "every key stays exactly as the schema specifies" in text
    assert structured_instruction("en", ["description"]) == ""


# That the backend offers the SAME eleven codes as web, iOS and Android is pinned
# in scripts/i18n/test_catalogs.py, which runs with the whole repo mounted — the
# backend test container sees only WEB/backend.
