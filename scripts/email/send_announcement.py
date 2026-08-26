#!/usr/bin/env python3
"""Send the "return to ALAFIA" announcement to dormant users.

    python scripts/email/send_announcement.py                 # DRY RUN (default)
    python scripts/email/send_announcement.py --to me@x.com   # send one test copy
    python scripts/email/send_announcement.py --apply         # the real send

Dry run is the default deliberately: this mails real patients, and an email
cannot be recalled. The dry run resolves the identical audience with the
identical query and renders the identical HTML — it just stops before Resend.

WHO GETS IT
-----------
Active accounts that have not signed in for --days (default 7), have not opted
out of marketing, and are not operational accounts.

Two judgement calls are encoded here, both of which change who is mailed:

  * `last_login IS NULL` is NOT treated as dormant by default. The column
    shipped after most of these accounts were created, and the SSO branch did
    not stamp it at first (app/api/auth.py:234), so NULL means "not seen since
    the column shipped", not "never used the app". Mailing all of them would
    include people who use ALAFIA constantly. Pass --include-never-seen to add
    them, and read the count before you do.

  * Operational accounts are excluded by address: the owner, the App Store
    review account and the developer account. Mailing the Apple reviewer a
    marketing message during a review is an avoidable way to fail one.

Every recipient gets their OWN unsubscribe token, so the link identifies them
without carrying an email address in the URL, and List-Unsubscribe headers are
set so the mail client's native button works (RFC 8058).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

# Import the app package from wherever this runs: from a checkout (scripts/email/…)
# or from inside the backend container, where /app is already the package root.
_here = Path(__file__).resolve()
for _candidate in (
    *(p / "WEB" / "backend" for p in _here.parents),
    Path("/app"),
):
    if (_candidate / "app" / "core" / "database.py").exists():
        sys.path.insert(0, str(_candidate))
        break

TEMPLATE = Path(__file__).with_name("return_to_alafia.html")

SUBJECT = "What's new in ALAFIA"

# Never mail these, whatever the query says.
OPERATIONAL_ADDRESSES = {
    "dew@6igma.com",              # owner
    "ios_reviewr@alafia.app",     # App Store review account
    "developer@hntsolutions.com", # development account
}

# Addresses that are not real people. The last three are this database's own
# synthetic accounts, found by reading the rows rather than assumed: the Firebase
# migration minted `firebase_<uid>@alafia.local`, the deploy smoke test mints
# `plus_<ts>@alafiasmoke.com`, and paywall testing left `@alafia.dev`. All three
# look like ordinary addresses to a naive query and would have been mailed.
EXCLUDED_DOMAINS = (
    "@example.com", "@test.com", "@localhost",
    "@alafia.local", "@alafiasmoke.com", "@alafia.dev",
)


def _render(html: str, *, name: str | None, unsubscribe_url: str,
            app_url: str, postal_address: str) -> str:
    first = (name or "").strip().split(" ")[0] if name else ""
    return (
        html.replace("{name_comma}", f" {first}, " if first else " ")
            .replace("{unsubscribe_url}", unsubscribe_url)
            .replace("{app_url}", app_url)
            .replace("{app_domain}", app_url.replace("https://", "").replace("http://", ""))
            .replace("{postal_address}", postal_address)
    )


async def _send_one(client: httpx.AsyncClient, api_key: str, sender: str,
                    to: str, html: str, unsubscribe_url: str) -> tuple[bool, str]:
    """One Resend call, with the unsubscribe headers a bulk send requires."""
    resp = await client.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "from": sender,
            "to": [to],
            "subject": SUBJECT,
            "html": html,
            # RFC 8058. Without List-Unsubscribe-Post the mail client shows no
            # native unsubscribe button and recipients reach for "spam" instead,
            # which is what actually damages a sending domain.
            "headers": {
                "List-Unsubscribe": f"<{unsubscribe_url}>, <mailto:privacy@alafia.app?subject=unsubscribe>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        },
    )
    if resp.status_code in (200, 201):
        return True, (resp.json() or {}).get("id", "")
    return False, f"{resp.status_code} {resp.text[:200]}"


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually send (default is a dry run)")
    ap.add_argument("--days", type=int, default=7, help="dormant threshold in days (default 7)")
    ap.add_argument("--include-never-seen", action="store_true",
                    help="also mail accounts whose last_login is NULL — read the note above first")
    ap.add_argument("--to", help="send a single test copy to this address and exit")
    ap.add_argument("--app-url", default=os.environ.get("APP_URL", "https://alafia.app"))
    ap.add_argument("--api-url", default=os.environ.get("API_URL", "https://api.alafia.app"))
    ap.add_argument("--limit", type=int, help="cap the audience (for a staged send)")
    args = ap.parse_args()

    postal_address = os.environ.get("POSTAL_ADDRESS", "").strip()
    if not postal_address:
        print("ERROR: POSTAL_ADDRESS is not set.\n"
              "  CAN-SPAM requires a valid physical postal address in commercial email.\n"
              "  Set it and re-run:  POSTAL_ADDRESS='ALAFIA, 123 ... ' ...", file=sys.stderr)
        return 2

    api_key = os.environ.get("RESEND_API_KEY", "")
    sender = os.environ.get("SENDER", "ALAFIA <noreply@alafia.app>")
    if args.apply and not api_key:
        print("ERROR: RESEND_API_KEY is not set; refusing to --apply.", file=sys.stderr)
        return 2

    html_template = TEMPLATE.read_text()

    # Imported here so --help works without a database or app config.
    from sqlalchemy import select
    from app.core.database import async_session
    from app.models.user import User
    from app.api.marketing import create_unsubscribe_token

    def unsub_url(uid: int) -> str:
        return f"{args.api_url}/unsubscribe?token={create_unsubscribe_token(uid)}"

    # ── Single test copy ────────────────────────────────────────────────
    if args.to:
        html = _render(html_template, name=None, unsubscribe_url=unsub_url(0),
                       app_url=args.app_url, postal_address=postal_address)
        if not args.apply:
            print(f"DRY RUN — would send one test copy to {args.to}")
            out = Path("/tmp/alafia_announcement_preview.html")
            out.write_text(html)
            print(f"rendered preview: {out}")
            return 0
        async with httpx.AsyncClient(timeout=30.0) as c:
            ok, info = await _send_one(c, api_key, sender, args.to, html, unsub_url(0))
        print(("sent " if ok else "FAILED ") + f"{args.to}: {info}")
        return 0 if ok else 1

    # ── Resolve the audience ────────────────────────────────────────────
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    async with async_session() as db:
        stmt = select(User).where(
            User.is_active.is_(True),
            User.marketing_opt_out_at.is_(None),
            User.email.isnot(None),
        )
        rows = (await db.execute(stmt)).scalars().all()

    never_seen = [u for u in rows if u.last_login is None]
    dormant = [u for u in rows if u.last_login is not None and u.last_login < cutoff]
    recent = [u for u in rows if u.last_login is not None and u.last_login >= cutoff]

    audience = list(dormant)
    if args.include_never_seen:
        audience += never_seen

    def excluded(u) -> str | None:
        email = (u.email or "").strip().lower()
        if not email or "@" not in email:
            return "no usable address"
        if email in OPERATIONAL_ADDRESSES:
            return "operational account"
        if email.endswith(EXCLUDED_DOMAINS):
            return "test domain"
        return None

    kept, skipped = [], []
    for u in audience:
        reason = excluded(u)
        (skipped if reason else kept).append((u, reason))

    kept.sort(key=lambda p: (p[0].last_login or datetime.min.replace(tzinfo=timezone.utc)))
    if args.limit:
        kept = kept[: args.limit]

    # ── Report ──────────────────────────────────────────────────────────
    print(f"\n  eligible pool (active, not opted out)      {len(rows)}")
    print(f"  signed in within {args.days}d — NOT mailed        {len(recent)}")
    print(f"  dormant >{args.days}d                             {len(dormant)}")
    print(f"  last_login NULL ({'included' if args.include_never_seen else 'EXCLUDED'})"
          f"{'':>15}{len(never_seen)}")
    print(f"  excluded (operational/test)                {len(skipped)}")
    print(f"  → will receive                             {len(kept)}\n")

    for u, _ in skipped:
        print(f"    skip  {u.email:<40} {excluded(u)}")
    if skipped:
        print()

    for u, _ in kept:
        seen = u.last_login.strftime("%Y-%m-%d") if u.last_login else "never"
        print(f"    send  {u.email:<40} last seen {seen}")

    if not args.apply:
        preview = _render(html_template, name=kept[0][0].full_name if kept else None,
                          unsubscribe_url="https://api.alafia.app/unsubscribe?token=SAMPLE",
                          app_url=args.app_url, postal_address=postal_address)
        out = Path("/tmp/alafia_announcement_preview.html")
        out.write_text(preview)
        print(f"\nDRY RUN — nothing sent. Rendered preview: {out}")
        print("Re-run with --apply to send.")
        return 0

    # ── Send ────────────────────────────────────────────────────────────
    sent = failed = 0
    async with httpx.AsyncClient(timeout=30.0) as c:
        for u, _ in kept:
            url = unsub_url(u.id)
            html = _render(html_template, name=u.full_name, unsubscribe_url=url,
                           app_url=args.app_url, postal_address=postal_address)
            ok, info = await _send_one(c, api_key, sender, u.email, html, url)
            if ok:
                sent += 1
                print(f"    sent    {u.email}")
            else:
                failed += 1
                print(f"    FAILED  {u.email}: {info}")
            # Resend's default is 2 requests/second; stay under it.
            await asyncio.sleep(0.6)

    print(f"\n  sent {sent}, failed {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
