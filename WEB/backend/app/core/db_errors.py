"""Which constraint a database refusal actually violated.

A bare `except IntegrityError` cannot tell one uniqueness rule from another, so
`/auth/register` answered **"Email or username already registered"** to every
violation — including a duplicate phone number, naming a field the person had
not filled in. That is the same wrong-field refusal the login form used to give
someone typing a valid phone number.

The constraint name is read out of the exception TEXT rather than off a
driver-specific attribute (`exc.orig.constraint_name` exists on asyncpg and not
everywhere), and it is extracted generically rather than matched against a list
of our index names — a list like that goes stale the moment someone adds an
index, and silently: the refusal simply reverts to the wrong message.
"""

import re

_UNIQUE_RE = re.compile(r'unique constraint "([^"]+)"', re.IGNORECASE)


def violated_constraint(exc: BaseException) -> str | None:
    """The name of the unique constraint a violation names, or None.

    None means "some other integrity error" — a foreign key, a NOT NULL. The
    caller must keep its general message for that case rather than guessing at
    uniqueness.
    """
    match = _UNIQUE_RE.search(str(getattr(exc, "orig", None) or exc))
    return match.group(1) if match else None
