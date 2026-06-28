"""Backfill existing ALAFIA users into the shared 6IGMA Identity store (Phase 1.4).

For each ALAFIA user not yet linked, this either (a) links to an identity user
that already has the same email, or (b) provisions a new identity user — minting
a canonical SID, copying the profile into `identity.user_identity`, recording the
old `firebase_uid` in `identity.legacy_auth_links`, and marking the account
`password_unset` (Firebase-era users had no local password → onboard via reset).
It then sets ALAFIA `users.identity_uid` + adopts the canonical SID so the SAME
SID lives on both sides. Zero duplication: ALAFIA keeps only the reference key.

SAFE BY DEFAULT (dry-run). Use --apply to write. Idempotent (skips linked users).

    python -m scripts.backfill_identity            # preview
    python -m scripts.backfill_identity --apply    # write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

from app.core.database import async_session
from app.models.user import User
from app.services import canonical_sid

MAP_PATH = Path(__file__).with_name("identity_backfill_map.json")


def _split_name(full_name: str | None) -> tuple[str, str]:
    parts = (full_name or "").strip().split()
    if not parts:
        return ("User", "X")
    return (parts[0], parts[-1] if len(parts) > 1 else "X")


def _base_username(email: str) -> str:
    local = (email or "user").split("@")[0]
    return re.sub(r"[^a-zA-Z0-9_.-]", "", local) or "user"


async def _unique_username(db, base: str) -> str:
    candidate, n = base, 0
    while True:
        exists = (await db.execute(
            text("SELECT 1 FROM identity.users WHERE lower(username)=lower(:u)"), {"u": candidate}
        )).first()
        if not exists:
            return candidate
        n += 1
        candidate = f"{base}{n}"


async def main(apply: bool) -> None:
    out: dict[str, dict] = {}
    linked = provisioned = skipped = 0

    async with async_session() as db:
        users = (await db.execute(select(User))).scalars().all()
        print(f"scanning {len(users)} ALAFIA users…")

        for u in users:
            if u.identity_uid:
                skipped += 1
                continue

            # (a) Link to an existing identity user with the same email.
            existing = (await db.execute(
                text("SELECT id, system_id FROM identity.users WHERE lower(email)=lower(:e)"),
                {"e": u.email},
            )).first()

            if existing:
                iid, isid = str(existing[0]), (existing[1] or "").strip() or None
                out[str(u.id)] = {"email": u.email, "action": "link", "identity_uid": iid, "sid": isid}
                if apply:
                    await db.execute(
                        text("UPDATE users SET identity_uid=:iid, system_id=COALESCE(:sid, system_id) WHERE id=:id"),
                        {"iid": iid, "sid": isid, "id": u.id},
                    )
                linked += 1
                continue

            # (b) Provision a new identity user.
            iid = str(uuid.uuid4())
            first, last = _split_name(u.full_name)
            sex = u.gender_at_birth or u.gender
            created = u.created_at or datetime.now(timezone.utc)
            sid = canonical_sid.generate_sid(first, last, u.date_of_birth, sex, created)
            role = "admin" if getattr(u, "is_superuser", False) else "patient"
            username = await _unique_username(db, _base_username(u.email))
            out[str(u.id)] = {"email": u.email, "action": "provision",
                              "identity_uid": iid, "username": username, "sid": sid}

            # Carry over ALAFIA's bcrypt hash so existing passwords work via identity
            # (passlib + raw bcrypt produce compatible $2b$ hashes). Users without a
            # usable hash (Firebase-era) keep it but can onboard via password reset.
            pw_hash = u.hashed_password or "migrated-no-local-password"
            status_val = "active" if u.hashed_password else "password_unset"
            if apply:
                await db.execute(text("""
                    INSERT INTO identity.users
                      (id, email, username, password_hash, account_role, tier,
                       account_status, email_verified, system_id, created_at, updated_at)
                    VALUES (:id, lower(:email), :username, :pw, :role, 'full',
                       :status, false, :sid, :created, :created)
                """), {"id": iid, "email": u.email, "username": username,
                       "pw": pw_hash, "role": role, "status": status_val,
                       "sid": sid, "created": created})
                await db.execute(text("""
                    INSERT INTO identity.user_identity
                      (id, user_id, first_name, last_name, date_of_birth, gender, biological_sex, created_at, updated_at)
                    VALUES (:rid, :uid, :fn, :ln, :dob, :gender, :sex, :created, :created)
                """), {"rid": str(uuid.uuid4()), "uid": iid, "fn": first, "ln": last,
                       "dob": (u.date_of_birth or None), "gender": u.gender, "sex": sex, "created": created})
                segs = canonical_sid.segments_for_log(first, last, u.date_of_birth, sex, created)
                await db.execute(text("""
                    INSERT INTO identity.user_identity_sid_log
                      (user_id, system_id, seg_version, seg_fn3, seg_ln3, seg_dob8, seg_gen1, seg_epoch10, generated_at)
                    VALUES (:uid, :sid, :v, :fn3, :ln3, :dob8, :gen1, :epo, :created)
                """), {"uid": iid, "sid": sid, "v": segs["seg_version"], "fn3": segs["seg_fn3"],
                       "ln3": segs["seg_ln3"], "dob8": segs["seg_dob8"], "gen1": segs["seg_gen1"],
                       "epo": segs["seg_epoch10"], "created": created})
                if u.firebase_uid:
                    await db.execute(text("""
                        INSERT INTO identity.legacy_auth_links (user_id, provider, provider_uid, created_at)
                        VALUES (:uid, 'firebase', :fuid, :created)
                    """), {"uid": iid, "fuid": u.firebase_uid, "created": created})
                await db.execute(
                    text("UPDATE users SET identity_uid=:iid, system_id=:sid WHERE id=:id"),
                    {"iid": iid, "sid": sid, "id": u.id},
                )
            provisioned += 1

        if apply:
            await db.commit()

    MAP_PATH.write_text(json.dumps(out, indent=2, default=str))
    verb = "APPLIED" if apply else "DRY-RUN (no writes)"
    print(f"{verb}: provisioned={provisioned} linked={linked} skipped(already linked)={skipped}")
    print(f"map written to {MAP_PATH}")
    if not apply:
        print("Re-run with --apply to persist.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    asyncio.run(main(ap.parse_args().apply))
