# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""What an elimination row says in words, when its columns say nothing.

`bowel_movements.blood_present` is a boolean and **five different writers fill
this table**. Two of them — `scripts/import_firestore.py:346` and
`scripts/migrate_all_firebase.py:508` — insert
`(user_id, log_date, log_time, notes, created_at)` and name no structured
column at all, so everything they migrate arrives as prose. The other three
(`import_real_data.py`, `import_food_bowel.py`, `services/firebase_sync.py`)
write the flag correctly.

Measured on the reference record 2026-10-04:

    bowel_movements        648 rows   written 2026-06-04 -> 2026-10-02
      blood_present true     0
      notes matching blood 134        "Bloody" 109, "Very bloody" 5,
                                      "bloody" 5, "Regular, traces of blood." 2,
                                      "Regular flow. Bloody, Mucus" 1, "Blooy" 1

One in five of this patient's bowel movements is recorded as bloody, and every
reader that consults the boolean sees none of them. §3aa in an import path: the
column is empty, the fact is not.

**This is not a fact about one record.** Any patient migrated through either
Firestore path has the same shape, so a reader that trusts the boolean alone
will under-report blood for all of them. The rule therefore belongs in a
service that every consumer shares — the photo-caption path in `api/image_ai`,
the wellness score, and any backfill — rather than being re-typed per caller.
Two copies is how a fix lands on one path and misses the other.

**On matching a misspelling.** `"blood" in text` catches 134 of the 135 blood
mentions here and misses `"Blooy"`. Adding `"blooy"` to a literal list would
fix exactly this record and nothing else, which is the hardcoding this codebase
keeps paying for (§3ad, §3c). Patients hand-type these notes, so the variants
are unbounded. Instead a token that *starts* like the word is compared by edit
distance, which covers `blooy`, `bloddy`, `bloody` and `blod` without naming
any of them — and `_matched` records which token fired, so a reader can audit
what the rule actually did rather than trusting it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Words whose presence is the finding. Compared by edit distance against any
#: token sharing their first three letters, so ordinary misspellings resolve
#: without a list of misspellings.
_BLOOD_WORDS = ("blood", "bloody")

#: A negation anywhere in the sentence withdraws the claim. Deliberately
#: explicit: "no blood" must never read as blood.
_NEGATIONS = ("no blood", "no visible blood", "without blood", "none seen",
              "no fresh blood", "not bloody")

#: Edit distance a token may sit from a target and still count. 1 covers the
#: single-character slips that dominate hand-typed notes ("Blooy", "blod");
#: 2 begins to admit genuinely different words, so it is the ceiling.
_MAX_EDITS = 1

_TOKEN = re.compile(r"[a-z]+")


def _levenshtein(a: str, b: str) -> int:
    """Edit distance. Small inputs — single words — so the simple form is fine."""
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@dataclass
class TextFindings:
    """What the words say, and which word said it.

    `matched` exists so a finding is never unexplainable: a score that drops
    because of this must be able to name the token it read.
    """

    blood: bool = False
    mucus: bool = False
    watery: bool = False
    matched: list[str] = field(default_factory=list)


def _mentions(text_low: str, targets: tuple[str, ...]) -> str | None:
    """The token that matched one of `targets`, by exact word or near spelling."""
    for token in _TOKEN.findall(text_low):
        for target in targets:
            if token == target:
                return token
            # FOUR characters, not three — and that is not a tuning knob.
            #
            # "blond" is ONE edit from "blood" (b-l-o-n-d → b-l-o-o-d), exactly
            # like the real typo "blooy". Distance cannot separate them, so a
            # three-letter prefix admitted an ordinary English word as a
            # clinical finding. The prefix is what discriminates: "bloo"
            # accepts blooy/blood/bloody and refuses blond, blot, blow.
            #
            # Found by the test asserting "blond" was two edits away — written
            # from arithmetic done in someone's head, which §3av already
            # records as the way to get this wrong. The scan said one.
            if (len(token) >= 4 and token[:4] == target[:4]
                    and _levenshtein(token, target) <= _MAX_EDITS):
                return token
    return None


def read_notes(text: str | None) -> TextFindings:
    """Findings stated in free text, for a row whose columns were never filled.

    Returns everything false for empty text — absence of words is not a
    negative finding, it is no finding, and the caller must keep that
    distinction rather than recording "no blood".
    """
    out = TextFindings()
    if not text:
        return out
    low = str(text).lower()

    if not any(neg in low for neg in _NEGATIONS):
        hit = _mentions(low, _BLOOD_WORDS)
        if hit:
            out.blood = True
            out.matched.append(hit)

    if "mucus" in low and "no mucus" not in low:
        out.mucus = True
        out.matched.append("mucus")

    if "watery" in low or "liquid" in low:
        out.watery = True
        out.matched.append("watery")

    return out


def blood_in_row(*, flag: bool | None, notes: str | None) -> bool:
    """Whether this row records blood, by column OR by what it says.

    The column wins when it is set to anything — True or False — because a
    writer that filled it made a statement. Only a NULL column falls through to
    the text, which is exactly the population the two Firestore importers left
    behind.
    """
    if flag is not None:
        return bool(flag)
    return read_notes(notes).blood
