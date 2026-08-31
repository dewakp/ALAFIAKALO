"""How a patient is referred to in anything sent to a model. One place.

Canon §3al: the patient's IDENTITY never leaves — their clinical detail does.
`ML/src/alafia_model/privacy.py` redacts at the single egress point, but that
is a BACKSTOP with two real limits: it runs only on the hosted path (so the
Ollama path, which dev prefers, is unprotected), and it can only redact what it
recognises. The control is not assembling the identifier at all.

There were two separate implementations of this before — one in `api/ai.py`,
one added to `api/planners.py` — which is the same shape of drift that let
three Anthropic header sites disagree. There is now one.

`tests/test_no_pii_in_prompts.py` fails the build if a direct identifier is
interpolated into a string outside its allow-list.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def subject_reference(user: Any) -> str:
    """The handle for this patient, safe to send to any model provider.

    An HMAC of the app id and our internal user id: stable, so a conversation
    keeps its subject, and meaningless outside our database.

    Falls back to a plainly non-identifying string rather than to the name — a
    failure here must never degrade into leaking the thing it exists to hide.
    """
    uid = getattr(user, "id", None)
    if uid is None:
        return "alafia-unknown-subject"
    try:
        from alafia_model import privacy
        return privacy.subject_token(uid)
    except Exception:  # noqa: BLE001 - never fail a request over the pseudonym
        logger.warning("subject_token unavailable; sending an opaque id", exc_info=True)
        return f"alafia-user-{uid}"
