"""Whose "today" is it?

The containers run UTC. `date.today()` therefore answers with the SERVER's date,
and from early evening in the Americas that is already tomorrow for the patient.
Asked "what did I eat today?" at 20:54 on 2026-09-05, the tool queried
2026-09-06, found nothing, and told a patient with six logged meals and 58.4 g
of sugar that they had eaten nothing — an empty result presented as a finding
(§3aa), firing every evening, in production, where Cloud Run is also UTC.

`log_date` is a plain DATE written in the patient's own terms, so it can only be
compared against the patient's own date. Resolution order:

  1. the timezone the client just told us (it always knows its own),
  2. `users.timezone`, when it holds a name that actually resolves,
  3. UTC — the old behaviour, and the only honest fallback.

Step 2 is not enough on its own: 83 of 85 production users have it NULL, and one
of the two that are set reads "America/New York", which is not a valid IANA name
(`America/New_York` is). A column that is usually empty and sometimes wrong
cannot be the only source.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

#: The header every client sets from its own clock. One header rather than a
#: field on each request schema, so it applies to every endpoint at once.
TIMEZONE_HEADER = "X-Client-Timezone"


def resolve_zone(hint: str | None = None, stored: str | None = None) -> ZoneInfo:
    """The patient's zone, or UTC. Never raises on bad input.

    A name we cannot resolve is DISCARDED rather than guessed at: silently
    "correcting" `America/New York` to `America/New_York` would be inventing a
    fact about where someone lives.
    """
    for candidate in (hint, stored):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate.strip())
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            logger.info("unusable timezone %r; ignoring", candidate)
    return ZoneInfo("UTC")


def patient_today(hint: str | None = None, stored: str | None = None) -> date:
    """The date it is where the patient is."""
    return datetime.now(timezone.utc).astimezone(resolve_zone(hint, stored)).date()


def zone_name(hint: str | None = None, stored: str | None = None) -> str:
    return str(resolve_zone(hint, stored))
