# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A finding written in words is still a finding.

`bowel_movements` has five writers and two of them — `import_firestore.py:346`
and `migrate_all_firebase.py:508` — insert only
`(user_id, log_date, log_time, notes, created_at)`, naming no structured
column. Everything they migrate therefore arrives as prose. Measured on the
reference record 2026-10-04:

    648 rows   blood_present true on 0
               notes matching blood on 134  ("Bloody" 109, "Very bloody" 5,
               "bloody" 5, "Regular, traces of blood." 2, "Blooy" 1)

One bowel movement in five is recorded as bloody and every reader that consults
the boolean alone sees none of them. These pin the reader that fixes it.
"""

import pytest

from app.services import elimination_text as et


# ── What the patient actually typed ───────────────────────────────────────

@pytest.mark.parametrize("note", [
    "Bloody",
    "bloody",
    "Very bloody",
    "Regular, traces of blood.",
    "Regular flow. Bloody, Mucus",
    "Lots of fresh blood after first poop.",
    "Less blood but blood streaked poop.",
])
def test_blood_is_read_from_the_words(note):
    assert et.read_notes(note).blood is True, note


def test_a_misspelling_is_caught_without_being_listed():
    """`"Blooy"` appears once in this record and `"blood" in text` misses it.

    Adding `"blooy"` to a literal list would fix this record and nothing else —
    the hardcoding §3ad and §3c keep paying for. Patients hand-type these notes,
    so the variants are unbounded; a token that OPENS like the word is compared
    by edit distance instead, and the matched token is recorded so the rule can
    be audited rather than trusted.
    """
    found = et.read_notes("Blooy")
    assert found.blood is True
    assert found.matched == ["blooy"], "the rule must say which token fired"


# ── …and what must NOT be read as blood ───────────────────────────────────

@pytest.mark.parametrize("note", [
    "Regular",
    "Regular flow",
    "Watery",
    "",
    None,
])
def test_an_ordinary_note_reports_nothing(note):
    assert et.read_notes(note).blood is False


@pytest.mark.parametrize("note", [
    "no blood",
    "No blood seen",
    "Formed brown stool, no visible blood",
    "not bloody",
])
def test_a_negation_withdraws_the_claim(note):
    """"no blood" must never read as blood — the one direction that is worse."""
    assert et.read_notes(note).blood is False, note


@pytest.mark.parametrize("word", ["blond hair", "a blot on the page", "blow"])
def test_a_word_that_merely_starts_like_blood_is_not_blood(word):
    """Edit distance is a REFUSAL instrument here, not a matcher.

    §3aj settled that string similarity picks confidently wrong answers — it
    scored "calcium calcitriol" nearest to "calcium citrate". The budget is one
    edit against a token already sharing the first three letters, which admits
    "blooy" and "blod" and rejects "blond" (2 edits) and "blot" (2).
    """
    assert et.read_notes(word).blood is False, word


# ── The column is a statement; only its absence defers to prose ───────────

def test_a_writer_that_filled_the_column_is_believed():
    """False means a writer looked and said no. It is not missing data."""
    assert et.blood_in_row(flag=False, notes="Bloody") is False
    assert et.blood_in_row(flag=True, notes="Regular") is True


def test_a_null_column_falls_through_to_the_words():
    """The 134 rows this exists for: NULL flag, "Bloody" in notes."""
    assert et.blood_in_row(flag=None, notes="Bloody") is True
    assert et.blood_in_row(flag=None, notes="Regular") is False
    assert et.blood_in_row(flag=None, notes=None) is False


# ── Other findings the same prose carries ─────────────────────────────────

def test_mucus_and_watery_are_read_too():
    found = et.read_notes("Regular flow. Bloody, Mucus")
    assert found.mucus is True
    assert et.read_notes("Watery").watery is True
    assert et.read_notes("no mucus").mucus is False


def test_absence_of_words_is_not_a_negative_finding():
    """Empty text means NO finding, never "no blood" — §3aa in a parser.

    A row with nothing written on it must not be recorded as having been
    checked and found clear.
    """
    found = et.read_notes(None)
    assert (found.blood, found.mucus, found.watery) == (False, False, False)
    assert found.matched == []
