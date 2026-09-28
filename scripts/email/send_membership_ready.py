#!/usr/bin/env python3
"""Tell ONE person who already has an account that their membership is live.

    python scripts/email/send_membership_ready.py --email a@b.com --name Ruth \\
        --ends "28 October 2026"                       # DRY RUN (default)
    ... --apply                                         # actually send

WHY THIS IS NOT `send_comp_invitation.py`
-----------------------------------------
That letter is for someone with NO account: it says "no account exists yet" and
sends the reader to /signup to create one. Sent to an existing account holder it
is worse than useless — it directs them to register an address that is already
taken, and tells them a falsehood about their own record on the way.

`send_signup_incomplete_email` does not fit either. It says the account "has no
membership attached yet", which is the exact inverse of the case this script
exists for.

THE CASE
--------
An account was created, a complimentary membership was granted to it, and the
person never signed in. Nothing in the product reaches them, because every other
letter is addressed to a different problem. Found on 2026-09-28: one account
created 2025-06-24, comped 2026-07-28, `last_login` still NULL.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does NOT embed a password-reset link. A reset token lives 30 minutes
(`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`), and this letter is unsolicited — it may
be read tomorrow. A dead link on the one message whose job is getting someone in
does not read as "expired", it reads as "broken". The letter points at "Forgot
password" so the token is minted when the reader is ready to use it.

It also makes NO claim about what is in the record. The account may be empty.

CHECK BEFORE YOU SEND
---------------------
This script has no database access, so it cannot verify its own premises. Both
are the caller's to establish first:

  * the account EXISTS          SELECT id, last_login FROM users WHERE ...
  * the membership END DATE     SELECT current_period_end FROM subscriptions ...

`--ends` is therefore required and free-text: it must be the date you READ, not
one this script guessed. Sending a wrong end date is a promise about access that
the database will not honour.

RUN IT AGAINST PRODUCTION
-------------------------
Needs production's Resend key to reach a real mailbox:

    RESEND_API_KEY=... POSTAL_ADDRESS="ALAFIA · ..." PUBLIC_WEB_URL=https://alafia.app \\
      python scripts/email/send_membership_ready.py ... --apply

Without a provider `send_email` logs a warning and returns False — a send that
quietly did nothing. That is treated as FAILURE here, never printed over.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import mimetypes
import os
import sys
from pathlib import Path

from app.services.email import Attachment, send_membership_ready_email

MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024


def _load_screenshots(specs: list[str]) -> tuple[list[Attachment], str | None]:
    """Read each `PATH|CAPTION` spec into an inline attachment."""
    shots: list[Attachment] = []
    total = 0
    for i, spec in enumerate(specs, start=1):
        raw, sep, caption = spec.partition("|")
        path = Path(raw.strip()).expanduser()
        if not path.is_file():
            return [], f"no such screenshot: {path}"
        # The PHI marker in a filename is a CONTROL, not a note — an email
        # cannot be recalled, so a mistyped path must fail here rather than
        # become a disclosure.
        if "phi" in path.name.lower():
            return [], (f"REFUSED {path.name} — its name marks it as holding "
                        f"patient data. That file must never be mailed.")
        ctype, _ = mimetypes.guess_type(path.name)
        if not (ctype or "").startswith("image/"):
            return [], f"{path.name} is {ctype or 'of unknown type'}, not an image"
        data = path.read_bytes()
        total += len(data)
        shots.append(Attachment(
            filename=path.name, content=data, content_type=ctype,
            content_id=f"shot{i}@alafia.app",
            caption=caption.strip() if sep and caption.strip() else None,
        ))
    if total > MAX_SCREENSHOT_BYTES:
        return [], (f"screenshots total {total/1_000_000:.1f} MB raw — too heavy. "
                    f"Downscale first: sips -Z 1120 in.png --out out.png")
    return shots, None


async def run(args: argparse.Namespace) -> int:
    postal = os.environ.get("POSTAL_ADDRESS", "").strip()
    if not postal:
        print("ERROR: POSTAL_ADDRESS is not set.\n"
              "       This letter is unsolicited, so it carries a physical "
              "address.", file=sys.stderr)
        return 2

    # PUBLIC_WEB_URL defaults to localhost, and a dry run inside a container
    # renders http://localhost:8080/login perfectly happily. The letter's whole
    # instruction is "go here", so a wrong base URL is not cosmetic.
    from app.core.config import settings
    web = (settings.PUBLIC_WEB_URL or "").rstrip("/")
    if "localhost" in web or "127.0.0.1" in web or not web.startswith("https://"):
        print(f"ERROR: PUBLIC_WEB_URL is {web!r}.\n"
              f"       The letter would send them to {web}/login.\n"
              f'       Set PUBLIC_WEB_URL="https://alafia.app" and re-run.',
              file=sys.stderr)
        return 2

    shots, shot_error = _load_screenshots(args.screenshot or [])
    if shot_error:
        print(f"ERROR: {shot_error}", file=sys.stderr)
        return 2

    print(f"recipient  : {args.email}")
    print(f"name       : {args.name or '(none — letter opens with a plain Hello)'}")
    print(f"ends       : {args.ends}")
    print(f"postal     : {postal}")
    # Say plainly which shape the letter takes. A reset link that was meant to
    # be there and silently is not sends the reader down the slower path with no
    # sign anything was lost.
    print(f"reset link : "
          f"{'embedded — 30 minute life, send NOW' if args.reset_url else 'none — letter points at Forgot password'}")
    for shot in shots:
        print(f"screenshot : {shot.filename} ({len(shot.content)/1000:.0f} kB)"
              f" — {shot.caption or '(no caption)'}")
    if not shots:
        print("screenshot : (none)")

    if not args.apply:
        import app.services.email as E
        captured: dict = {}

        async def _capture(to, subject, html, attachments=None) -> bool:
            captured.update(to=to, subject=subject, html=html,
                            attachments=list(attachments or []))
            return True

        real, E.send_email = E.send_email, _capture
        try:
            await send_membership_ready_email(
                args.email, display_name=args.name, membership_ends=args.ends,
                reset_url=args.reset_url, screenshots=shots,
                postal_address=postal)
        finally:
            E.send_email = real

        html = captured.get("html", "")
        # cid: resolves only inside a MIME message, so swap for data: URIs in
        # the PREVIEW copy — otherwise a browser shows every image broken,
        # which looks identical to a letter whose images really are broken.
        for att in captured.get("attachments") or []:
            if att.content_id:
                html = html.replace(
                    f"cid:{att.content_id}",
                    f"data:{att.content_type};base64,"
                    f"{base64.b64encode(att.content).decode('ascii')}")
        out = Path("/tmp/alafia_membership_ready_preview.html")
        out.write_text(html)
        print(f"\nsubject    : {captured.get('subject')}")
        print(f"preview    : {out}")
        print("\n*** DRY RUN — nothing sent. Read the preview, then re-run "
              "with --apply. ***")
        return 0

    ok = await send_membership_ready_email(
        args.email, display_name=args.name, membership_ends=args.ends,
        reset_url=args.reset_url, screenshots=shots, postal_address=postal)
    if not ok:
        print("\nFAILED — nothing was delivered. Check RESEND_API_KEY is set to "
              "production's key; without a provider send_email logs a warning "
              "and returns False.", file=sys.stderr)
        return 1

    print(f"\n*** SENT to {args.email}. ***")
    print("Acceptance is not delivery — Resend returns 200 for a suppressed")
    print("address too. Confirm from the inbox or a delivery event.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True, help="the existing account's address")
    ap.add_argument("--name", help='shown in the greeting, e.g. "Ruth"')
    ap.add_argument("--ends", required=True,
                    help='membership end date as it should READ, e.g. '
                         '"28 October 2026". Required: it must be the date you '
                         'read out of subscriptions.current_period_end, not a '
                         'guess — it is a promise about access.')
    ap.add_argument("--reset-url", dest="reset_url",
                    help="a password-reset URL to embed as a button. Pass one "
                         "ONLY when the recipient is reading now: the token "
                         "lives 30 minutes, and a dead link on this letter "
                         "reads as broken rather than expired. Omitted, the "
                         "letter points at Forgot password instead, which "
                         "never goes stale.")
    ap.add_argument("--screenshot", action="append", metavar="PATH|CAPTION",
                    help="an image to show INLINE, optionally followed by '|' "
                         "and a caption. Repeatable. Any file whose name "
                         "contains 'PHI' is refused outright.")
    ap.add_argument("--apply", action="store_true",
                    help="actually send (default is a dry run that writes a preview)")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
