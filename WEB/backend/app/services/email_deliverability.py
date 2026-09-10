"""Can this address receive mail at all?

Payment is now taken BEFORE the mailbox is proven, so a typo becomes a person
who paid and cannot be reached. This is the cheap check that catches the common
case without making anyone leave the app.

It asks DNS, not a list. A domain with no MX record cannot accept mail — that is
a fact about the domain, true for every typo anyone invents, and it needs no
blocklist to maintain and cannot go stale. A hand-written set of "known bad
domains" would only ever catch the typos somebody already thought of.

It does NOT prove the mailbox exists. Nothing short of sending does, which is
exactly what the verification email is for. This only rules out addresses that
could never work.

FAILS OPEN. DNS being unreachable is not evidence against the address, and
refusing a paying customer because our resolver blinked is worse than the
failure being guarded against — the same rule the dose guard follows (§3aj).
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

#: A DNS answer is not worth waiting on for long; the caller is a person
#: staring at a signup form.
_TIMEOUT_SECONDS = 4.0


def _domain_of(email: str) -> str:
    return (email or "").rsplit("@", 1)[-1].strip().lower()


def _has_mx(domain: str) -> bool | None:
    """True / False / None when DNS could not answer."""
    try:
        import dns.exception
        import dns.resolver
    except ImportError:  # pragma: no cover - dnspython ships with email-validator
        return None

    resolver = dns.resolver.Resolver()
    resolver.lifetime = _TIMEOUT_SECONDS
    resolver.timeout = _TIMEOUT_SECONDS
    try:
        answers = resolver.resolve(domain, "MX")
        return len(answers) > 0
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        # Answered, and the answer is "nothing here".
        return False
    except dns.exception.DNSException:
        # Timeout, SERVFAIL, no nameserver — we learned nothing.
        return None
    except Exception:  # noqa: BLE001
        return None


async def can_receive_mail(email: str) -> tuple[bool, str | None]:
    """(accepted, reason_if_refused).

    `accepted` is True unless DNS positively says this domain takes no mail.
    """
    domain = _domain_of(email)
    if not domain or "." not in domain:
        return False, "That email address does not look complete."

    has_mx = await asyncio.to_thread(_has_mx, domain)
    if has_mx is False:
        return False, (
            f"“{domain}” cannot receive email, so we could not send you a "
            "verification link. Please check the spelling.")
    if has_mx is None:
        # Unreachable ≠ invalid.
        logger.info("MX lookup inconclusive for %s; allowing", domain)
    return True, None
