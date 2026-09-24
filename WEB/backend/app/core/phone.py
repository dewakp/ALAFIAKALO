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

#: Below this a string is a name fragment or a typo, not a phone number.
MIN_PHONE_DIGITS = 7


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
