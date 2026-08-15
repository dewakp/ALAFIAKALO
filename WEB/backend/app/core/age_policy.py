"""Minimum-age policy for ALAFIA account holders.

CANON: **an account holder is an adult (by their jurisdiction's standard). A
child is never an account holder — a child is a dependent profile under a
consenting adult's account.**

That choice is what keeps ALAFIA out of COPPA's verifiable-parental-consent
regime. COPPA attaches when an operator collects personal information *from a
child*; here the data subject relationship runs through the adult account
holder, who supplies and controls the child's record. It also preserves the
paediatric use case the privacy page describes — a parent tracking a child's
condition — which a bare "no minors" rule would have destroyed.

Two things this module exists to prevent:

1. **A policy that only exists in prose.** The privacy page previously claimed
   ALAFIA "is not intended for children under 13" while the software collected
   no date of birth on web or iOS and validated nothing anywhere. An unenforced
   age claim is worse than none: it is a representation to regulators and users
   that the product does not honour.

2. **A client-side gate.** Clients are UX, not enforcement — anyone can POST to
   the API directly. Every account-creation path must call `assert_adult()`.

The threshold is the local digital age of consent, which is NOT uniform:
COPPA sets 13 in the US; UK GDPR sets 13; GDPR Article 8 lets each EU member
state choose between 13 and 16, defaulting to 16 where the state is silent.
When we do not know the country we apply the strictest value, because the
failure we can least afford is admitting a child we were not permitted to.
"""

from __future__ import annotations

from datetime import date

# GDPR Art. 8 leaves the digital age of consent to member states (13–16). Where
# a country is absent from this map we use STRICTEST_MINIMUM_AGE rather than a
# permissive guess.
_MINIMUM_AGE_BY_COUNTRY: dict[str, int] = {
    # 13 — COPPA (US) and UK GDPR, plus member states that legislated the floor.
    "US": 13, "GB": 13, "UK": 13, "CA": 13, "BE": 13, "DK": 13, "EE": 13,
    "FI": 13, "LV": 13, "MT": 13, "PT": 13, "SE": 13, "NO": 13, "IS": 13,
    # 14
    "AT": 14, "BG": 14, "CY": 14, "ES": 14, "IT": 14, "LT": 14,
    # 15
    "CZ": 15, "FR": 15, "GR": 15, "SI": 15,
    # 16
    "DE": 16, "HR": 16, "HU": 16, "IE": 16, "LU": 16, "NL": 16, "PL": 16,
    "RO": 16, "SK": 16,
}

#: Applied when the country is unknown, blank, or not in the map.
STRICTEST_MINIMUM_AGE = 16


class AgeRestricted(Exception):
    """The person is below the account-holder age for their jurisdiction.

    Carries the numbers so the caller can build a message that tells the user
    what the rule actually is, rather than a bare refusal.
    """

    def __init__(self, age: int, minimum_age: int, country: str | None):
        self.age = age
        self.minimum_age = minimum_age
        self.country = country
        super().__init__(f"account holder is {age}, minimum is {minimum_age}")


class InvalidDateOfBirth(Exception):
    """Missing or unparseable date of birth — we cannot evaluate the rule."""


def minimum_age_for(country: str | None) -> int:
    """Account-holder age for a country, strictest value when unknown."""
    if not country:
        return STRICTEST_MINIMUM_AGE
    return _MINIMUM_AGE_BY_COUNTRY.get(country.strip().upper(), STRICTEST_MINIMUM_AGE)


def parse_date_of_birth(value: str | date | None) -> date:
    """Parse an ISO `YYYY-MM-DD` date of birth.

    Rejects anything unparseable and anything in the future. A future date is
    not a typo we should tolerate: it would produce a negative age that sails
    through a naive `age >= minimum` comparison only if the comparison is
    written carelessly, and it means the value is untrustworthy either way.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise InvalidDateOfBirth("date of birth is required")

    if isinstance(value, date):
        dob = value
    else:
        try:
            # Tolerate a full ISO timestamp; clients have sent both.
            dob = date.fromisoformat(value.strip()[:10])
        except ValueError as exc:
            raise InvalidDateOfBirth("date of birth must be YYYY-MM-DD") from exc

    if dob > date.today():
        raise InvalidDateOfBirth("date of birth cannot be in the future")
    return dob


def age_on(dob: date, today: date | None = None) -> int:
    """Whole years elapsed, by calendar — not days/365.25.

    The `(m, d) < (m, d)` tuple comparison is what makes a birthday that has not
    yet occurred this year subtract a year, and it is correct for 29 February:
    someone born on a leap day is 18 on 1 March of a non-leap year, never a day
    early.
    """
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def assert_adult(
    date_of_birth: str | date | None,
    country: str | None = None,
    today: date | None = None,
) -> int:
    """Enforce the account-holder age rule. Returns the age when permitted.

    Raises `InvalidDateOfBirth` when the value is missing or malformed, and
    `AgeRestricted` when the person is below their jurisdiction's threshold.
    Callers translate these into HTTP responses; this module stays transport
    agnostic so the same rule can be reused off the request path.
    """
    dob = parse_date_of_birth(date_of_birth)
    age = age_on(dob, today)
    minimum = minimum_age_for(country)
    if age < minimum:
        raise AgeRestricted(age=age, minimum_age=minimum, country=country)
    return age
