#!/usr/bin/env python3
"""Send ONE complimentary-membership invitation to a named person.

    python scripts/email/send_comp_invitation.py --email a@b.com --name "Dr. Owolabi" \\
        --months 12 --deadline "11 October 2026"            # DRY RUN (default)
    ... --apply                                              # actually send

WHY THIS IS NOT `send_announcement.py`
--------------------------------------
That script resolves its audience with `select(User)` — it can only mail people
who already have an account. An invitation goes to someone who does NOT, which
is the entire point: they are being asked to create one. Its `--to` flag reaches
an arbitrary address but renders with `name=None` and signs the unsubscribe for
**user id 0**, which its own comment calls "fine for a preview, wrong for a real
person, whose opt-out must actually work against their own account."

So this is a separate, deliberately small sender: one recipient, named, no
audience query, no unsubscribe token to mint (there is no account to attach one
to — the letter discloses why it arrived and offers a reply path instead).

WHAT IT PROMISES, AND WHAT MUST FOLLOW
--------------------------------------
The letter tells the recipient to STOP at the payment step and says we will
activate the membership. That is a commitment with a clock on it. When they
verify, run BOTH of these promptly or they are left holding nothing:

    python scripts/activate_comp_signup.py --email <addr> --apply   # in backend
    scripts/db/grant_comp.sh --emails <addr> --months 12 --apply

The 2026-09-15 invitation made that same promise with no tooling behind it.

RUN IT AGAINST PRODUCTION
-------------------------
Never from the dev compose container: `run_against_prod.sh` documents why —
the sender would resolve against the DEV COPY of prod and sign with the DEV
SECRET_KEY, and both failures are invisible. This script needs no database at
all, but it DOES need production's Resend key to reach a real mailbox:

    RESEND_API_KEY="$(gcloud secrets versions access latest --secret=resend-api-key)" \\
    POSTAL_ADDRESS="ALAFIA · 8201 164th Ave NE, Suite 200, Redmond, WA 98052" \\
    PYTHONPATH=WEB/backend python scripts/email/send_comp_invitation.py ... --apply

Without RESEND_API_KEY (and no SMTP configured) `send_email` logs
"No email provider configured" and returns False — a send that quietly did
nothing. This script treats that as a FAILURE and exits non-zero, rather than
printing success over it.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from app.services.email import (
    is_clinical_role,
    send_complimentary_invitation_email,
)


async def run(args: argparse.Namespace) -> int:
    # CAN-SPAM requires a physical address in commercial mail, and this letter
    # is unsolicited. Refuse rather than send without one — the same gate
    # run_against_prod.sh holds.
    postal = os.environ.get("POSTAL_ADDRESS", "").strip()
    if not postal:
        print("ERROR: POSTAL_ADDRESS is not set.\n"
              "       CAN-SPAM requires a physical postal address in commercial\n"
              "       email, and this letter is unsolicited.\n"
              '       POSTAL_ADDRESS="ALAFIA · 8201 164th Ave NE, Suite 200, '
              'Redmond, WA 98052"', file=sys.stderr)
        return 2

    # The letter says "go to <url> and sign up with this address exactly", so a
    # wrong base URL is not cosmetic — it sends the recipient somewhere that
    # does not exist. PUBLIC_WEB_URL defaults to localhost, and a dry run inside
    # a container renders `http://localhost:8080/signup` perfectly happily.
    # Caught by READING the rendered letter; nothing else would have shown it.
    from app.core.config import settings
    web = (settings.PUBLIC_WEB_URL or "").rstrip("/")
    if "localhost" in web or "127.0.0.1" in web or not web.startswith("https://"):
        print(f"ERROR: PUBLIC_WEB_URL is {web!r}.\n"
              f"       The letter would tell them to sign up at {web}/signup.\n"
              f'       Set PUBLIC_WEB_URL="https://alafia.app" and re-run.',
              file=sys.stderr)
        return 2

    clinical = is_clinical_role(args.role)
    if args.role and not clinical:
        print(f"ERROR: {args.role!r} is not a clinical role in the UserRole "
              f"enum.", file=sys.stderr)
        print("       Pass a role ONLY if it will actually be granted — the "
              "letter's\n       wording and the entitlement must not drift "
              "apart.", file=sys.stderr)
        return 2

    print(f"recipient : {args.email}")
    print(f"name      : {args.name or '(none — letter opens with a plain Welcome)'}")
    print(f"months    : {args.months}")
    print(f"deadline  : {args.deadline}")
    print(f"role      : {args.role or '(none — PATIENT wording, no clinician block)'}")
    if args.practice and not clinical:
        print("note      : --practice ignored; it only appears in the clinician letter")
    print(f"postal    : {postal}")

    if not args.apply:
        # Render through a stubbed transport so the exact bytes can be read
        # before anyone receives them. An email cannot be recalled.
        import app.services.email as E
        captured: dict[str, str] = {}

        async def _capture(to: str, subject: str, html: str) -> bool:
            captured.update(to=to, subject=subject, html=html)
            return True

        real, E.send_email = E.send_email, _capture
        try:
            await send_complimentary_invitation_email(
                args.email, display_name=args.name, months=args.months,
                signup_deadline=args.deadline, clinical_role=args.role,
                practice=args.practice)
        finally:
            E.send_email = real

        out = Path("/tmp/alafia_comp_invitation_preview.html")
        out.write_text(captured.get("html", ""))
        print(f"\nsubject   : {captured.get('subject')}")
        print(f"preview   : {out}")
        print("\n*** DRY RUN — nothing sent. Read the preview, then re-run "
              "with --apply. ***")
        return 0

    ok = await send_complimentary_invitation_email(
        args.email, display_name=args.name, months=args.months,
        signup_deadline=args.deadline, clinical_role=args.role,
        practice=args.practice)

    if not ok:
        # send_email returns False when no provider is configured or the send
        # failed. Never report success over that.
        print("\nFAILED — nothing was delivered. Check RESEND_API_KEY is set to "
              "production's\nkey; without a provider send_email logs a warning "
              "and returns False.", file=sys.stderr)
        return 1

    print(f"\n*** SENT to {args.email}. ***")
    print("They will sign up, verify, and STOP at payment. Then run promptly:")
    print(f"  python scripts/activate_comp_signup.py --email {args.email} --apply")
    print(f"  scripts/db/grant_comp.sh --emails {args.email} "
          f"--months {args.months} --apply")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True, help="the recipient's address")
    ap.add_argument("--name", help='shown in the greeting, e.g. "Dr. Owolabi". '
                                   'An honorific here implies NOTHING about role.')
    ap.add_argument("--months", type=int, default=12,
                    help="length of the complimentary period (default 12)")
    ap.add_argument("--deadline", required=True,
                    help='sign-up deadline as it should read, e.g. "11 October 2026". '
                         "Required: a letter with no deadline fails silently — "
                         "nobody can tell a lapsed offer from a pending one.")
    ap.add_argument("--role", help="clinical role, ONLY if it will actually be "
                                   "granted (e.g. nephrologist). Omit for patients.")
    ap.add_argument("--practice", help="practice name, clinician letters only")
    ap.add_argument("--apply", action="store_true",
                    help="actually send (default is a dry run that writes a preview)")
    args = ap.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
