"""Matching a typed phone number against the forms it may have been stored as.

Numbers reach us in whatever shape a person types — `(971) 260-6446`,
`9712606446`, `+19712606446` — and are stored in one shape per account. A
lookup that compares the typed string literally therefore misses the account it
is looking for, which is precisely why the Phone tab on the login page answered
"Incorrect email or password" to a correct number and password.

**Compare against candidate stored FORMS, not a normalised column.** The obvious
alternative — `regexp_replace(phone_number, '\\D', '', 'g') = :digits` in the
WHERE clause — silently makes the query Postgres-only and cannot use an index.
This lives here rather than in one API module because two callers now need it:
recipient lookup (§3e) and login.
"""

import phonenumbers

#: Below this a string is a name fragment or a typo, not a phone number.
MIN_PHONE_DIGITS = 7


def to_e164(value: str | None, region: str | None = None) -> str | None:
    """The canonical `+<country><national>` form, or None if it is not a number.

    **Uniqueness on a phone number is only meaningful once there is ONE form of
    it.** `users.phone_number` carries a UNIQUE index, but the index compares
    the literal string — so `9712606446` and `+19712606446` are two different
    values and the same human can hold two accounts without the constraint ever
    firing. Email has had this right all along (`email.strip().lower()` on the
    way in); phone was stored exactly as typed.

    `region` is the account's ISO-3166 country (`users.country`), needed only
    when the number arrives without a `+`. A number that already carries one is
    unambiguous and the region is ignored.

    **None means "not a usable number", and the caller must not invent one.**
    Production holds a 9-digit value on a US account: too short to be a US
    number, so there is no honest way to canonicalise it. Prefixing `+1` would
    fabricate a different person's number in a clinical record. Same rule as an
    unreadable unit (§3am) — refuse rather than assume.

    Parsing is delegated to libphonenumber rather than hand-written: country
    calling codes and national number lengths are exactly the kind of table
    §3aj says never to type from memory, and ALAFIA serves eleven locales — a
    hardcoded `+1` would be wrong for most of them.
    """
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, (region or "").strip().upper() or None)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def phone_candidates(term: str | None) -> list[str]:
    """Plausible stored forms of a typed number, or [] if it is not one.

    Returning [] for a short string is what keeps this safe to call on EVERY
    login attempt: an email address yields no digits, so it adds no clause.
    """
    d = digits(term)
    if len(d) < MIN_PHONE_DIGITS:
        return []
    forms = {d, f"+{d}"}
    # A 10-digit US number is stored E.164 as +1XXXXXXXXXX. Someone typing it
    # without the country code must still find their own account.
    if not d.startswith("1"):
        forms |= {f"+1{d}", f"1{d}"}
    return sorted(forms)
