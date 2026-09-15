"""The language a patient is answered in. One place, like prompt_identity.

A patient writes in the language they think in, and the assistant answered in
English regardless: `preferred_language` was saved by the Profile screens and
read by nothing that talks to a patient. Worse, the column holds two dialects —
web saves codes ("en"), iOS saves names ("English") — so any consumer that
compared it to one form silently ignored the other.

Order, most specific first:
  1. the app's CURRENT UI language — every client sends it on every request
     (`X-Client-Language`), the way it sends `X-Client-Timezone`;
  2. the patient's saved preference;
  3. English.
An unrecognised value is discarded, not repaired: guessing that "Engish" meant
English is inventing a fact about the patient (the same rule as timezones,
`app/core/patient_time.py`).

What is and is NOT translated is a safety decision, not a style one. Prose the
patient reads follows their language. Anything a guard or a lookup reads stays
exactly as the schema says — the meal planner's allergy sanitiser matches
English forbidden-food names against meal names, and a translated "cacahuète"
walks straight past a peanut allergy.
"""

from __future__ import annotations

from typing import Any, Iterable

LANGUAGE_HEADER = "X-Client-Language"

# The product's language set — the eleven the web switcher offers. Code ->
# (English name, native name). Clients carry the same codes.
LANGUAGES: dict[str, tuple[str, str]] = {
    "en": ("English", "English"),
    "es": ("Spanish", "Español"),
    "fr": ("French", "Français"),
    "de": ("German", "Deutsch"),
    "pt": ("Portuguese", "Português"),
    "ar": ("Arabic", "العربية"),
    "zh": ("Chinese", "中文"),
    "yo": ("Yoruba", "Yorùbá"),
    "ig": ("Igbo", "Igbo"),
    "ha": ("Hausa", "Hausa"),
    "sw": ("Swahili", "Kiswahili"),
}
DEFAULT_LANGUAGE = "en"


def normalise_language(value: str | None) -> str | None:
    """A product language code for any form the apps store or send, else None.

    Accepts a code ("fr"), a locale ("fr-FR", "fr_CA"), an English name
    ("French") or a native name ("Français"), case-insensitively.
    """
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    code = text.replace("_", "-").split("-")[0].lower()
    if code in LANGUAGES:
        return code
    folded = text.casefold()
    for candidate, (english, native) in LANGUAGES.items():
        if folded in (english.casefold(), native.casefold()):
            return candidate
    return None


def patient_language(user: Any, client_language: str | None = None) -> str:
    """The code to answer this patient in."""
    return (
        normalise_language(client_language)
        or normalise_language(getattr(user, "preferred_language", None))
        or DEFAULT_LANGUAGE
    )


def language_name(code: str) -> str:
    english, native = LANGUAGES.get(code, LANGUAGES[DEFAULT_LANGUAGE])
    return english if english == native else f"{english} ({native})"


def conversation_instruction(code: str) -> str:
    """For prose replies: detect the patient's language, answer in it."""
    return (
        "LANGUAGE: Reply in the language the patient writes in. When their message "
        f"does not show one — a single word, a number, a food — reply in {language_name(code)}, "
        "the language their app is set to. Keep drug names, lab test names, units and "
        "every number exactly as recorded; never translate or convert them."
    )


def structured_instruction(code: str, prose_fields: Iterable[str]) -> str:
    """For JSON replies: only the named prose fields follow the patient's language."""
    fields = ", ".join(f'"{f}"' for f in prose_fields)
    if code == DEFAULT_LANGUAGE:
        return ""
    return (
        f"LANGUAGE: Write the values of {fields} in {language_name(code)}. Every other value "
        "and every key stays exactly as the schema specifies, in English — other parts of "
        "ALAFIA read them."
    )
