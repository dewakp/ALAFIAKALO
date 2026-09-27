"""Finish a complimentary signup that stopped at the payment step.

WHY THIS EXISTS
---------------
Two-step signup is verify -> pay -> account, and `materialise()` is the only
path from a pending signup to a `users` row. So someone offered a FREE
membership has nowhere to go: they verify their address, reach the payment
step, and stop — exactly as the invitation tells them to — and no account is
ever created. `grant_comp.sh` cannot help, because it resolves emails against
`users` and aborts on a row that does not exist yet.

That gap was real. The invitation sent on 2026-09-15 promised "we will activate
your membership and email you the moment it is live" and there was no tooling
behind that sentence. It was never exercised only because the recipient never
signed up.

WHAT IT DOES
------------
Records a COMPLIMENTARY payment against the pending signup, then creates the
account on the ordinary paid path:

    provider  = 'none'          <- the established comp convention in
                                   `subscriptions`; never a real rail
    reference = 'comp:<date>'   <- matches the `comp:` prefix already used for
                                   `subscription_events.event_id`

Nothing here pretends money moved. A reader of `pending_registrations` sees
`none` / `comp:…` and knows immediately what happened, which is the whole
reason for not inventing a plausible-looking Stripe reference.

It does NOT grant entitlement. That stays with `scripts/db/grant_comp.sh`,
which is idempotent, refuses to clobber a real billing rail, and writes an
audit row. Two small tools that each do one thing beat one that does both
slightly differently.

USAGE
-----
    # DRY RUN (default) — resolves everything and rolls back
    docker compose --profile test run --rm backend-test \\
        python scripts/activate_comp_signup.py --email someone@example.com

    # commit
    ... python scripts/activate_comp_signup.py --email someone@example.com --apply

Then grant the membership itself:

    scripts/db/grant_comp.sh --emails someone@example.com --months 12 --apply

Do NOT override PYTHONPATH — the container sets `/ml/src:/app`, and replacing
it with `/app` drops the canonical `alafia_model` and breaks collection.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import async_session
from app.models.pending_registration import PendingRegistration
from app.models.user import User
from app.services import signup_service as svc

COMP_PROVIDER = "none"


def _comp_reference(now: datetime) -> str:
    """Self-describing, and shaped like the audit ids comps already use."""
    return f"comp:{now.strftime('%Y-%m-%dT%H:%M:%SZ')}"


async def run(email: str, apply: bool) -> int:
    email = (email or "").strip().lower()
    if not email:
        print("ERROR: --email is required", file=sys.stderr)
        return 2

    async with async_session() as db:
        # An account may already exist — from a completed signup, or from a
        # previous run of this script. Report it rather than failing obscurely
        # further down; re-running must be safe.
        existing = (await db.execute(
            select(User).where(User.email == email)
        )).scalar_one_or_none()
        if existing is not None:
            print(f"Account already exists: id={existing.id} {existing.email} "
                  f"(active={existing.is_active})")
            print("Nothing to activate. Grant the membership with:")
            print(f"  scripts/db/grant_comp.sh --emails {email} --months 12 --apply")
            return 0

        pending = (await db.execute(
            select(PendingRegistration).where(PendingRegistration.email == email)
        )).scalar_one_or_none()
        if pending is None:
            print(f"ERROR: no signup in progress for {email}", file=sys.stderr)
            print("       They must sign up at /signup and confirm the emailed "
                  "link first.", file=sys.stderr)
            return 1

        # Each refusal below is reported separately: "not ready" is four
        # different situations and collapsing them sends the operator to the
        # wrong fix.
        if pending.is_expired():
            print(f"ERROR: the signup for {email} expired at {pending.expires_at}.",
                  file=sys.stderr)
            print("       Ask them to sign up again — a fresh row replaces this "
                  "one.", file=sys.stderr)
            return 1

        if not pending.email_verified:
            print(f"ERROR: {email} has NOT confirmed their address.", file=sys.stderr)
            print("       The email gate is never waived: an unconfirmed address "
                  "may not be theirs.", file=sys.stderr)
            print(f"       verification sent: {pending.verification_sent_at}",
                  file=sys.stderr)
            return 1

        print(f"pending signup : {pending.email}")
        print(f"  name         : {pending.full_name or '(none)'}")
        print(f"  verified at  : {pending.email_verified_at}")
        print(f"  already paid : {pending.paid}"
              f"{'  (' + str(pending.payment_provider) + ')' if pending.paid else ''}")
        print(f"  expires      : {pending.expires_at}")

        now = datetime.now(timezone.utc)
        reference = _comp_reference(now)

        if not pending.paid:
            await svc.mark_paid(db, email, COMP_PROVIDER, reference)
            print(f"\nrecording complimentary grant: provider={COMP_PROVIDER} "
                  f"reference={reference}")
        else:
            print("\nalready marked paid — leaving the existing record alone")

        # Re-read: mark_paid flushed, and materialise() reads `ready_to_create`
        # off this instance.
        pending = (await db.execute(
            select(PendingRegistration).where(PendingRegistration.email == email)
        )).scalar_one_or_none()

        try:
            user = await svc.materialise(db, pending)
        except svc.PhoneAlreadyRegistered:
            print(f"ERROR: the phone number on this signup is already registered "
                  f"to another account.", file=sys.stderr)
            await db.rollback()
            return 1

        if user is None:
            print("ERROR: materialise() refused — gates not satisfied. Nothing "
                  "was created.", file=sys.stderr)
            await db.rollback()
            return 1

        print(f"account        : id={user.id} {user.email}")

        if not apply:
            await db.rollback()
            print("\n*** DRY RUN — rolled back, nothing changed. "
                  "Re-run with --apply. ***")
            return 0

        await db.commit()
        print("\n*** APPLIED. ***")
        print("The account exists but is UNPAID, so every gated route still "
              "answers 402.")
        print("Grant the membership now:")
        print(f"  scripts/db/grant_comp.sh --emails {email} --months 12 --apply")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True,
                    help="the address that signed up and stopped at payment")
    ap.add_argument("--apply", action="store_true",
                    help="actually commit (default is a dry run)")
    args = ap.parse_args()
    return asyncio.run(run(args.email, args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
