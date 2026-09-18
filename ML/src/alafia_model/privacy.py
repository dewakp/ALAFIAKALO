"""What may cross the boundary to a third-party model provider.

Two rules, and the second exists because the first cannot be perfect:

1. **Identify the subject with our own token, never with their PII.** A provider
   that needs continuity across turns gets `subject_token(user_id)` — an opaque,
   stable, non-reversible handle derived from the app id and the user id. It is
   meaningless outside our database, so it cannot be joined against anything the
   provider holds.

2. **Scrub the prompt on the way out anyway.** Free text — journal entries, chat
   messages, meal notes — is written by patients who will type their own name,
   their doctor's name, an email address or a phone number without thinking about
   it. Structuring the context correctly does not help when the PII is inside a
   sentence the user wrote, so redaction happens at the egress point where it
   cannot be forgotten by a new call site.

Hosted providers carry the everyday load, deliberately: production's Ollama is
scale-to-zero and warming it is a standing cost decision (canon 5), so a ~250 s
cold call is the wrong front door — a hosted answer takes seconds.

That makes THIS MODULE the privacy guarantee, not a second line of defence. What
crosses the boundary is the clinical content the model needs to answer — the
potassium value, the drug, the dose — with the patient's identity removed and
replaced by our own subject token. Anything that must not leave regardless can
still set `local_only=True` (see `capabilities/llm.py`).

Read `_TITLED_NAME` and the note beneath it before trusting this with a new kind
of free text: a bare first name in prose is not detectable by pattern, and this
module does not claim to catch it.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from collections.abc import Iterable
from contextvars import ContextVar

_APP_ID = "app.alafia"

# Order matters: email before the phone pattern, or the digits inside an address
# like "user2024@x.com" get partially redacted first and the email no longer
# matches as a whole.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("[email]", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")),
    ("[card]", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("[ssn]", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    # BEFORE [phone], and covering ISO. A date of birth is mostly digits and
    # separators, so the phone pattern swallows it and reports a birthday as
    # "[phone]" — redacted, but mislabelled, and a reader auditing the egress
    # cannot tell what actually left. The previous pattern also matched only
    # D/M/YYYY, so an ISO date (1974-03-15 — what this API returns) never
    # reached it at all.
    ("[dob]", re.compile(
        r"\b(?:(?:19|20)\d{2}[/-]\d{1,2}[/-]\d{1,2}"      # 1974-03-15
        r"|\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2})\b"        # 15/03/1974
    )),
    # +1 (555) 010-9999, 555.010.9999, 07700 900123 — 9+ digits with separators.
    ("[phone]", re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")),
    ("[url]", re.compile(r"\bhttps?://\S+")),
    ("[id]", re.compile(r"\b[A-Z]{2,4}\d{6,}\b")),          # MRN / policy numbers
)

# Names are the one identifier a pattern cannot reliably find: "Mark" is a name
# and a verb, "Dialysis" is capitalised mid-sentence, and no regex separates them.
# Three mechanisms cover the realistic cases, and none is claimed to be complete:
#
# 1. Exact known values — the account holder's own name, registered automatically
#    from the auth dependency, so no call site has to remember to pass it.
# 2. Self-introduction, which is how a patient actually volunteers a name in chat.
# 3. Titled names, which is how they refer to their clinicians.
_SELF_INTRO = re.compile(
    r"\b(I am|I'm|Im|my name is|this is|name's)\s+"
    r"([A-Z][a-z'’-]+(?:\s+[A-Z][a-z'’-]+){0,2})",
)

# A titled name is unambiguous — and clinicians are named in patient free text far
# more often than patients name themselves.
_TITLED_NAME = re.compile(
    r"\b(Dr|Doctor|Prof(?:essor)?|Mr|Mrs|Ms|Miss|Nurse|Sister|Matron)\.?\s+"
    r"[A-Z][a-z'’-]+(?:\s+[A-Z][a-z'’-]+){0,2}",
)

# WHAT THIS CANNOT DO: a bare name in passing — "tell Bola I logged my meal" — is
# not detectable by pattern. "Bola" is a name; "Mark" is also a verb; "Dialysis"
# is capitalised mid-sentence. Only a named-entity model separates them, and it
# would still miss some.
#
# That residual gap is real and is NOT closed by this module. It is the reason a
# bare first name can still slip through in free prose, and the reason the
# `known_values` registry below is populated automatically for every signed-in
# request rather than left to callers: the identifiers we actually hold are the
# ones we can guarantee to remove.


# ── Request-scoped identity ───────────────────────────────────────────────────
#
# The identifiers to redact are the ones we already hold for the signed-in user.
# They are registered ONCE, in the auth dependency every authenticated request
# passes through, and read here at the egress point.
#
# They are deliberately NOT a parameter each caller supplies. A caller-supplied
# hint is a step someone forgets, and the thing they forget is a patient's name
# on its way to a vendor. The same reasoning as scrubbing at a single egress
# point rather than in each service.
_identity: ContextVar[tuple] = ContextVar("alafia_identity", default=())

# The handle the provider sees INSTEAD of the identity it replaces. A generic
# "[name]" loses continuity across turns; this keeps a stable subject the model
# can refer to, while meaning nothing outside our own database.
_subject: ContextVar[str] = ContextVar("alafia_subject", default="")


def register_identity(
    user_id: int | str | None = None,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> None:
    """Record this request's identifiers, and the token that stands in for them.

    Called once per authenticated request. `user_id` is ours, not the user's: it
    becomes `subject_token(user_id)`, which is what actually goes out in place of
    the NAME. Email and phone are replaced by their own placeholders — swapping an
    address for the subject token would read as though the user were called that.
    """
    known = {}
    if name and len(name.strip()) > 2:
        known[name.strip()] = None            # resolved to the subject token
    if email and len(email.strip()) > 2:
        known[email.strip()] = "[email]"
    if phone and len(phone.strip()) > 2:
        known[phone.strip()] = "[phone]"
    if known:
        _identity.set(tuple(known.items()))
    if user_id is not None:
        _subject.set(subject_token(user_id))


def current_identity() -> tuple:
    """(value, placeholder) pairs; placeholder None means "use the subject token"."""
    return _identity.get()


def current_subject() -> str:
    return _subject.get()


def clear_identity() -> None:
    _identity.set(())
    _subject.set("")


def subject_token(user_id: int | str, app_id: str = _APP_ID) -> str:
    """A stable, opaque handle for a user — our id, not theirs.

    HMAC rather than a bare hash: a plain SHA-256 of a small integer user id is
    trivially reversible by enumerating every id up to a few million.
    """
    secret = os.getenv("ALAFIA_PSEUDONYM_SECRET", "")
    if not secret:
        # The fallback is a CONSTANT IN THIS FILE, so the HMAC degrades to a
        # public hash: anyone holding a token can recover the user id by trying
        # a few million of them. That is precisely the property the HMAC exists
        # to prevent, so outside development it is a hard error rather than a
        # quiet downgrade — a pseudonym nobody can rely on is worse than none,
        # because it is trusted.
        if _is_production():
            raise RuntimeError(
                "ALAFIA_PSEUDONYM_SECRET is not set. Subject tokens sent to model "
                "providers would be reversible by enumerating user ids. Mount the "
                "secret (deploy/gcp/deploy.sh) before serving traffic."
            )
        secret = f"{app_id}:dev-only-not-a-secret"
    digest = hmac.new(secret.encode(), f"{app_id}:{user_id}".encode(), hashlib.sha256)
    return f"alafia-{digest.hexdigest()[:16]}"


def _is_production() -> bool:
    """True unless this is clearly a developer machine or a test run."""
    env = os.getenv("ENVIRONMENT", os.getenv("ENV", "")).strip().lower()
    if env in ("dev", "development", "local", "test", "testing", "ci"):
        return False
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return env in ("prod", "production", "staging") or bool(os.getenv("K_SERVICE"))


def scrub_pii(text: str, known_values: Iterable[str] = ()) -> str:
    """Redact direct identifiers from text bound for a third party.

    `known_values` are identifiers we already hold for this user — their name,
    email, phone — and are removed by exact match, which is the only reliable way
    to strip a name. Pattern matching then catches what the caller did not know
    about, including a name the patient introduces themselves by.
    """
    if not text:
        return text

    # The signed-in user is replaced by OUR handle, not by a blank placeholder:
    # the model keeps a subject it can refer to across turns, and the handle maps
    # back to the user id only inside our database. Third parties named in the
    # text get the generic placeholder — we have no token for them, and they are
    # not the subject of the conversation.
    subject = current_subject() or "[name]"

    # The request's registered identifiers are merged in HERE rather than only in
    # `scrub_payload`, so both entry points redact identically. When only the
    # wrapper consulted the context, calling this function directly silently lost
    # name redaction — the kind of difference that holds until the day someone
    # reaches for the inner function.
    #
    # Accepts either bare strings (all treated as names) or (value, placeholder)
    # pairs from the request context, so an email is not swapped for the subject
    # token as though the patient were called that.
    pairs: list[tuple[str, str]] = []
    for entry in tuple(known_values) + tuple(current_identity()):
        if isinstance(entry, tuple):
            value, placeholder = entry
            pairs.append((value, placeholder or subject))
        elif entry:
            pairs.append((entry, subject))

    # Longest first: redacting "Jane" before "Jane Doe" would leave "<subject> Doe".
    for value, placeholder in sorted(
        ((v.strip(), ph) for v, ph in pairs if v and len(v.strip()) > 2),
        key=lambda p: len(p[0]), reverse=True,
    ):
        text = re.sub(rf"\b{re.escape(value)}\b", placeholder, text, flags=re.IGNORECASE)

    text = _SELF_INTRO.sub(lambda m: f"{m.group(1)} {subject}", text)
    text = _TITLED_NAME.sub("[name]", text)

    for placeholder, pattern in _PATTERNS:
        text = pattern.sub(placeholder, text)
    return text


logger = logging.getLogger(__name__)

#: Keys that carry encoded media, identifiers or machine values — NEVER prose.
#: Everything NOT named here is scrubbed.
#:
#: This is deliberately a DENY-list. The first version enumerated the prose keys
#: instead and leaked immediately: an assistant turn carrying `reasoning` went
#: out whole, because that key was not on the list somebody thought to write.
#: Enumerating what to protect is the same mistake that let the vision payload
#: escape for months — the safe default is "redact it unless we know it is not
#: prose".
#:
#: Scrubbing these WOULD be destructive: `_PATTERNS` holds a 13-19 digit card
#: matcher and an uppercase-plus-digits id matcher, and a base64 JPEG is a
#: megabyte of exactly that — redaction would corrupt the image while appearing
#: to work. `model` is here for the same reason: `gpt-4o-2024-08-06` matches the
#: date-of-birth pattern.
_OPAQUE_KEYS = frozenset({
    "data", "b64_json", "url", "image_url", "source", "media_type",
    "content_type", "image_bytes", "audio_bytes", "id", "tool_call_id", "type",
    "model", "role", "index", "finish_reason",
})

#: Structured call arguments, left exactly as composed.
#:
#: A tool call's arguments come from a model that has already been handed
#: scrubbed text, so nothing identifying survives there that redaction has not
#: seen once already — while scrubbing them breaks the call outright: `[dob]`
#: matches a plain `2026-09-18`, so `start_date` became a placeholder and the
#: tool read a different window (canon 3am, where that class of misread reported
#: 7,699 mg of potassium as one day's intake).
_STRUCTURED_KEYS = frozenset({"arguments", "input"})


def _scrub_prose(value, known: tuple):
    """Scrub every string inside `value` except media, identifiers and arguments.

    Walks lists and dicts so a message's content blocks are reached. A bare
    string is prose by construction — the text of a content block, an item in a
    list — so it is always scrubbed.
    """
    if isinstance(value, str):
        return scrub_pii(value, known)
    if isinstance(value, (bytes, bytearray)):
        return value
    if isinstance(value, list):
        return [_scrub_prose(v, known) for v in value]
    if isinstance(value, dict):
        return {
            k: (v if k in _OPAQUE_KEYS or k in _STRUCTURED_KEYS
                else _scrub_prose(v, known))
            for k, v in value.items()
        }
    return value


def scrub_payload(arg, known_values: Iterable[str] = ()):
    """Scrub whatever `_dispatch` is about to send, in EVERY shape it can take.

    The signed-in user's identifiers are picked up from the request context, so a
    call site cannot omit them by forgetting a parameter.

    Until 2026-09-18 this handled exactly one shape — a list of messages whose
    `content` is a string — and returned everything else untouched. Three real
    payloads went out unredacted as a result:

        [{"role": "assistant", "tool_calls": [...]}]   no `content` key at all
        [{"role": "user", "content": [blocks]}]        vision / Anthropic blocks
        {"task": ..., "text": ..., "image_bytes": ...} a capability payload

    A photo's BYTES still cannot be redacted — a pharmacy label carries the
    patient's printed name and no text rule reaches it. Images travel the same
    path as text by decision (canon 3al); what changes here is that the words
    travelling beside them no longer escape.
    """
    known = tuple(known_values)
    if isinstance(arg, str):
        return scrub_pii(arg, known)
    if isinstance(arg, (list, dict)):
        return _scrub_prose(arg, known)
    # A shape nobody anticipated must be visible, not silently forwarded: the
    # previous `return arg` is precisely how the vision payload escaped review.
    logger.warning("privacy: unrecognised egress payload type %s — forwarded unscrubbed",
                   type(arg).__name__)
    return arg
