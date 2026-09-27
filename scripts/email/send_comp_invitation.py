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
import base64
import mimetypes
import os
import sys
from pathlib import Path

from app.services.email import (
    Attachment,
    is_clinical_role,
    send_complimentary_invitation_email,
)

# Raw bytes, before base64 inflates them by 4/3. Resend's documented ceiling is
# 40 MB post-encoding; this is far below it because the limit that actually
# matters is the reader's — a screenshot straight off a Retina display is
# ~3200px and several MB, and a letter that takes a minute to open on a phone
# has failed whatever it was illustrating.
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024


def _load_screenshots(specs: list[str]) -> tuple[list[Attachment], str | None]:
    """Read each `PATH|CAPTION` spec into an inline attachment.

    Returns (attachments, error). The caller REFUSES to send on any error
    rather than mailing a letter with a picture missing from it.
    """
    shots: list[Attachment] = []
    total = 0
    for i, spec in enumerate(specs, start=1):
        raw, sep, caption = spec.partition("|")
        path = Path(raw.strip()).expanduser()
        if not path.is_file():
            return [], f"no such screenshot: {path}"

        # The PHI marker in a filename is a CONTROL, not a note to a reader.
        # Of the seven screens captured on 2026-09-27, two carry a real
        # patient's labs (Hemoglobin 9 g/dL), vitals, named medications and
        # active conditions. An email cannot be recalled, so a mistyped path
        # must fail here rather than become a disclosure.
        if "phi" in path.name.lower():
            return [], (f"REFUSED {path.name} — its name marks it as holding "
                        f"patient data. That file must never be mailed.")

        ctype, _ = mimetypes.guess_type(path.name)
        if not (ctype or "").startswith("image/"):
            return [], (f"{path.name} is {ctype or 'of unknown type'}, not an "
                        f"image")

        data = path.read_bytes()
        total += len(data)
        shots.append(Attachment(
            filename=path.name,
            content=data,
            content_type=ctype,
            # cid values are addr-spec shaped; the letter references exactly
            # this string as `cid:<id>`.
            content_id=f"shot{i}@alafia.app",
            caption=caption.strip() if sep and caption.strip() else None,
        ))

    if total > MAX_SCREENSHOT_BYTES:
        return [], (f"screenshots total {total/1_000_000:.1f} MB raw "
                    f"(~{total*4/3/1_000_000:.1f} MB base64) — too heavy. "
                    f"Downscale them first: sips -Z 1120 in.png --out out.png")
    return shots, None


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

    shots, shot_error = _load_screenshots(args.screenshot or [])
    if shot_error:
        print(f"ERROR: {shot_error}", file=sys.stderr)
        return 2

    print(f"recipient : {args.email}")
    print(f"name      : {args.name or '(none — letter opens with a plain Welcome)'}")
    print(f"months    : {args.months}")
    print(f"deadline  : {args.deadline}")
    print(f"role      : {args.role or '(none — PATIENT wording, no clinician block)'}")
    if args.practice and not clinical:
        print("note      : --practice ignored; it only appears in the clinician letter")
    print(f"postal    : {postal}")
    if shots:
        for shot in shots:
            print(f"screenshot: {shot.filename} "
                  f"({len(shot.content)/1000:.0f} kB, {shot.content_type}) "
                  f"— {shot.caption or '(no caption)'}")
    else:
        print("screenshot: (none — the letter carries no images)")

    if not args.apply:
        # Render through a stubbed transport so the exact bytes can be read
        # before anyone receives them. An email cannot be recalled.
        import app.services.email as E
        captured: dict = {}

        async def _capture(to, subject, html, attachments=None) -> bool:
            captured.update(to=to, subject=subject, html=html,
                            attachments=list(attachments or []))
            return True

        real, E.send_email = E.send_email, _capture
        try:
            await send_complimentary_invitation_email(
                args.email, display_name=args.name, months=args.months,
                signup_deadline=args.deadline, clinical_role=args.role,
                practice=args.practice, screenshots=shots,
                postal_address=postal)
        finally:
            E.send_email = real

        html = captured.get("html", "")
        # `cid:` resolves only inside a MIME message, so a browser shows the
        # preview with every image broken — which looks identical to a letter
        # whose images really are broken. Swap each reference for a data: URI
        # so the preview shows what the recipient will see. The SENT letter is
        # untouched; this is the preview copy only.
        for att in captured.get("attachments") or []:
            if att.content_id:
                data_uri = (f"data:{att.content_type};base64,"
                            f"{base64.b64encode(att.content).decode('ascii')}")
                html = html.replace(f"cid:{att.content_id}", data_uri)

        out = Path("/tmp/alafia_comp_invitation_preview.html")
        out.write_text(html)
        print(f"\nsubject   : {captured.get('subject')}")
        print(f"preview   : {out}")
        print(f"inline    : {len(captured.get('attachments') or [])} image(s) "
              f"embedded as data: URIs in the preview, cid: in the real letter")
        print("\n*** DRY RUN — nothing sent. Read the preview, then re-run "
              "with --apply. ***")
        return 0

    ok = await send_complimentary_invitation_email(
        args.email, display_name=args.name, months=args.months,
        signup_deadline=args.deadline, clinical_role=args.role,
        practice=args.practice, screenshots=shots,
        postal_address=postal)

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
    ap.add_argument("--screenshot", action="append", metavar="PATH|CAPTION",
                    help="an image to show INLINE in the letter, optionally "
                         "followed by '|' and a caption. Repeatable. Show the "
                         "reader screens they will actually be able to open: "
                         "the clinician board belongs only in a letter that "
                         "grants --role. Any file whose name contains 'PHI' is "
                         "refused outright.")
    ap.add_argument("--apply", action="store_true",
                    help="actually send (default is a dry run that writes a preview)")
    args = ap.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
