# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Structure the drugs a flowsheet records, when the flowsheet is saved.

`session_drugs` holds one row per flowsheet drug line; `therapy_sessions.
drugs_administered` holds the same administrations flattened into text. Both
readers in `clinical_sources` PREFER the structured rows and parse the text only
for a session that has none (§3aa, `_flowsheet_items`).

WHY THIS EXISTS
---------------
Until now the ONLY writer of `session_drugs` was `scripts/import_flowsheets.py`,
which reads Excel workbooks cell by cell. So the table could never be newer than
the last workbook somebody imported, and measured on production 2026-10-02 it
stopped at **2025-12-31** while dosing continued: 1,299 sessions spanning
2018-11-16 → 2026-09-25 carried drug text and no structured rows.

That is invisible on the clinical surfaces, because the text fallback covers
them. It is NOT invisible to anything reading the table directly — the ML
exposure series does, and it saw a patient who ceased IV iron ten months before
they actually did, during the window where ferritin fell from 1,033 to 24 and
transferrin saturation to 6%. A fitted iron model therefore learned from a
truncated series and could not see that the dose had changed from 100 mg to
200 mg, because every 2026 session was in the unparsed 1,299.

A workbook importer is also a one-patient artefact. Patients arriving with their
own data write the flowsheet form, not an Excel sheet, so the free text is the
general intake and parsing it on save is what makes the structured series
continuous for everyone.

THE TWO RULES THIS MUST NOT BREAK
---------------------------------
1. **Fill gaps; never overwrite a richer row.** The workbook carries a ROUTE on
   1,763 of 1,764 production rows and a TIME on 269 — neither of which
   `parse_drugs_administered` can reproduce, because the flattened text does not
   contain them. So a session that already has rows is left exactly alone. Only
   a session with ZERO rows is populated. Re-parsing to "refresh" would destroy
   the timing that `test_session_drug_timing.py` exists to protect, and §3at
   records why timing is not cosmetic: an IV iron runs over a period, and a drug
   given at 23:47 belongs to a different calendar day than the sheet's date.

2. **Store the name VERBATIM.** `parse_drugs_administered` canonicalises —
   `Epogene` becomes `Epoetin alfa` — but `SessionDrug.name` is documented as
   what the sheet said, because that is how a row is found on the paper again
   (§3ax), and production holds `Epogene` 673, `Venofer` 364, `Doxercalcif` 363.
   Writing the canonical form would split one drug into two spellings inside the
   very table that exists to stop that. Canonicalisation already happens at READ
   time (`administrations_on_day` calls `canonical_drug_name`), so verbatim
   storage loses nothing and keeps both sources agreeing.

Route and time are written as NULL, not guessed. An absent time is absent (§0).
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session_drug import SessionDrug
from app.services.flowsheet_drugs import parse_drugs_administered

logger = logging.getLogger(__name__)

#: The sheet has five drug rows (24-28). Anything beyond that is not a drug
#: table any more, and a runaway text value must not create unbounded rows.
MAX_ROWS = 5

#: The verbatim name is the text before the first "(" — the same split the
#: parser already made to separate name from dose. Verified against production:
#: reproduces `Epogene`, `Venofer`, `Sodium Citrate`, `Doxercalcif`.
_VERBATIM = re.compile(r"^([^(]+)")


def verbatim_name(raw: str) -> str:
    """The drug name as written, recovered from the parsed item."""
    match = _VERBATIM.match(raw or "")
    return (match.group(1) if match else (raw or "")).strip(" ,;")


async def sync_session_drugs(db: AsyncSession, session) -> int:
    """Populate `session_drugs` for one session that has none. Returns rows added.

    Never raises: a flowsheet that cannot be parsed must not break the save that
    carries it. The text remains the record either way, and `clinical_sources`
    falls back to parsing it, so a failure here costs structure, not data.
    """
    session_id = getattr(session, "id", None)
    user_id = getattr(session, "user_id", None)
    text = getattr(session, "drugs_administered", None)
    if not session_id or not user_id or not text or not text.strip():
        return 0

    try:
        existing = (await db.execute(
            select(SessionDrug.id).where(SessionDrug.session_id == session_id).limit(1)
        )).first()
        # Rule 1: a session that already has rows keeps them, with their route
        # and time. This function only ever fills a gap.
        if existing is not None:
            return 0

        drugs = parse_drugs_administered(text)
        if not drugs:
            return 0

        added = 0
        for index, drug in enumerate(drugs[:MAX_ROWS]):
            name = verbatim_name(drug.raw) or drug.name
            if not name:
                continue
            db.add(SessionDrug(
                session_id=session_id,
                user_id=user_id,
                row_index=index,
                name=name[:120],
                dose_text=(drug.dose or None),
                # The flattened text carries neither. Absent, not invented.
                route=None,
                administered_time=None,
                administered_at=None,
            ))
            added += 1
        return added
    except Exception:
        logger.warning("session_drugs sync failed for session %s", session_id,
                       exc_info=True)
        return 0
