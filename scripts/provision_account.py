#!/usr/bin/env python3
"""Provision a test account through the ALAFIA API — never by writing rows.

Creating a user with INSERTs looks equivalent and is not: `POST /auth/register`
also provisions the account in the shared 6IGMA Identity service, mints the
canonical System Identifier and writes its SystemIdLog row. An account hand-made
in SQL has none of that, so it diverges from every real account in exactly the
places a login path cares about.

So this script only speaks HTTP:

    register → login → claim roles → professional profile → seed sample data

Everything is idempotent. An account that already exists is reused, a role
already held is left alone, and the sample data is skipped whenever the account
already has entries of that kind — so re-running never doubles anything.

What it deliberately CANNOT do is grant the complimentary subscription: there is
no admin write surface, and `/subscription` only accepts verified provider
purchases. Use `scripts/db/grant_comp.sh` for that. On a paywalled deployment
(SUBSCRIPTION_REQUIRED=true) run the comp FIRST, because every seeding endpoint
is behind the paywall and will 402 without it.

Usage:
    export ALAFIA_NEW_PASSWORD='…'          # never pass secrets on argv
    scripts/provision_account.py \
        --api https://api.alafia.app/api/v1 \
        --email deji.adesida@alafia.app --name 'Deji Adesida' \
        --role physician --primary --seed

    scripts/provision_account.py --api http://localhost:8005/api/v1 …
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

import httpx

TIMEOUT = 30.0


def log(msg: str) -> None:
    print(f"[provision] {msg}", flush=True)


class Api:
    """Thin API client that keeps the CSRF double-submit cookie in step.

    Unauthenticated POSTs (register, login) are rejected without a matching
    `csrf_token` cookie + `X-CSRF-Token` header. Bearer-authenticated requests
    are CSRF-exempt by design, but sending the header anyway costs nothing.
    """

    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.client = httpx.Client(timeout=TIMEOUT, follow_redirects=True)
        self.token: str | None = None
        self.client.get(f"{self.base}/auth/csrf-cookie")

    def _headers(self) -> dict[str, str]:
        h = {"X-CSRF-Token": self.client.cookies.get("csrf_token", "")}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def get(self, path: str, **kw) -> httpx.Response:
        return self.client.get(f"{self.base}{path}", headers=self._headers(), **kw)

    def post(self, path: str, **kw) -> httpx.Response:
        return self.client.post(f"{self.base}{path}", headers=self._headers(), **kw)

    def put(self, path: str, **kw) -> httpx.Response:
        return self.client.put(f"{self.base}{path}", headers=self._headers(), **kw)


def fail(r: httpx.Response, what: str) -> None:
    raise SystemExit(f"[provision] {what} failed — HTTP {r.status_code}: {r.text[:400]}")


def register(api: Api, email: str, password: str, name: str, **profile) -> None:
    r = api.post("/auth/register", json={
        "email": email, "password": password, "full_name": name,
        **{k: v for k, v in profile.items() if v is not None},
    })
    if r.status_code == 201:
        log(f"created user {email} (id {r.json().get('id')})")
    elif r.status_code == 400 and "already registered" in r.text:
        log(f"user {email} already exists — reusing it")
    elif r.status_code == 410:
        raise SystemExit(
            "[provision] direct registration is closed on this deployment "
            "(TWO_STEP_SIGNUP_REQUIRED=true). Sign the account up through "
            "/auth/signup/start, then re-run with --skip-register."
        )
    else:
        fail(r, "register")


def login(api: Api, email: str, password: str) -> None:
    # OAuth2PasswordRequestForm — form-encoded, and the field is `username`.
    r = api.post("/auth/login", data={"username": email, "password": password})
    if r.status_code != 200:
        fail(r, "login")
    api.token = r.json()["access_token"]
    log("logged in")


def claim_role(api: Api, role: str, primary: bool) -> int:
    """Claim a professional role; returns the role assignment id."""
    existing = api.get("/users/roles")
    if existing.status_code != 200:
        fail(existing, "list roles")
    for ra in existing.json():
        if ra["role"] == role:
            log(f"role '{role}' already assigned (id {ra['id']})")
            if primary and not ra["is_primary"]:
                r = api.put(f"/users/roles/{ra['id']}/primary")
                if r.status_code != 200:
                    fail(r, "set primary role")
                log(f"role '{role}' set primary")
            return ra["id"]

    r = api.post("/users/roles", json={"role": role, "is_primary": primary})
    if r.status_code != 201:
        fail(r, f"claim role {role}")
    rid = r.json()["id"]
    log(f"claimed role '{role}' (id {rid}, primary={primary})")
    return rid


def set_profile(api: Api, role_id: int, profile: dict) -> None:
    r = api.put(f"/users/roles/{role_id}/profile", json=profile)
    if r.status_code != 200:
        fail(r, "upsert professional profile")
    log("professional profile saved")


# ── Sample clinical data ─────────────────────────────────────────────────
# Deliberately unremarkable, internally consistent values for a healthy adult,
# so a clinician view has something to render without implying a real history.

def seed(api: Api) -> None:
    today = date.today()

    def day(n: int) -> str:
        return (today - timedelta(days=n)).isoformat()

    def push(path: str, label: str, rows: list[dict]) -> None:
        listing = api.get(path)
        if listing.status_code == 402:
            raise SystemExit(
                "[provision] 402 Payment Required while seeding. This deployment "
                "is paywalled — grant the subscription first:\n"
                "  scripts/db/grant_comp.sh --emails <email> --apply"
            )
        if listing.status_code != 200:
            fail(listing, f"list {label}")
        if listing.json():
            log(f"{label}: account already has entries — not seeding")
            return
        for row in rows:
            r = api.post(path, json=row)
            if r.status_code != 201:
                fail(r, f"create {label}")
        log(f"{label}: seeded {len(rows)} entries")

    push("/vitals/", "vitals", [
        {"log_date": day(n), "blood_pressure_systolic": sys_, "blood_pressure_diastolic": dia,
         "heart_rate_bpm": hr, "weight_kg": wt, "height_cm": 178.0,
         "body_temperature_c": 36.7, "blood_oxygen_pct": 98.0,
         "notes": "Sample data — provisioned test account"}
        for n, sys_, dia, hr, wt in [
            (21, 128, 82, 74, 82.5), (14, 126, 80, 71, 82.1),
            (7, 124, 79, 69, 81.8), (1, 122, 78, 68, 81.4),
        ]
    ])

    push("/labs/", "labs", [
        {"test_date": day(10), "test_name": name, "value": value, "unit": unit,
         "reference_range_low": lo, "reference_range_high": hi,
         "is_abnormal": abnormal, "category": "chemistry", "status": "final",
         "performing_lab": "Sample data — provisioned test account"}
        for name, value, unit, lo, hi, abnormal in [
            ("Hemoglobin A1c", 5.9, "%", 4.0, 5.6, True),
            ("Creatinine", 1.0, "mg/dL", 0.7, 1.3, False),
            ("eGFR", 92.0, "mL/min/1.73m2", 60.0, 120.0, False),
            ("Potassium", 4.2, "mmol/L", 3.5, 5.1, False),
            ("LDL Cholesterol", 138.0, "mg/dL", 0.0, 100.0, True),
        ]
    ])

    push("/medications/", "medications", [
        {"name": "Lisinopril", "dosage": "10", "dosage_unit": "mg", "frequency": "once daily",
         "route": "oral", "start_date": day(180), "reason": "Hypertension",
         "is_active": True, "notes": "Sample data — provisioned test account"},
        {"name": "Atorvastatin", "dosage": "20", "dosage_unit": "mg", "frequency": "once daily at night",
         "route": "oral", "start_date": day(120), "reason": "Elevated LDL",
         "is_active": True, "notes": "Sample data — provisioned test account"},
    ])

    push("/mood/", "mood", [
        {"entry_date": day(n), "mood_score": m, "energy_level": e, "stress_level": s,
         "sleep_quality": q, "sleep_hours": h,
         "notes": "Sample data — provisioned test account"}
        for n, m, e, s, q, h in [
            (5, 7, 6, 4, 7, 7.0), (3, 6, 6, 5, 6, 6.5), (1, 8, 7, 3, 8, 7.5),
        ]
    ])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", required=True, help="API base, e.g. https://api.alafia.app/api/v1")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True, help="full name")
    p.add_argument("--role", help="professional role to claim (e.g. physician)")
    p.add_argument("--primary", action="store_true", help="make that role primary")
    p.add_argument("--specialty", default=None)
    p.add_argument("--practice", default=None, help="practice / organisation name")
    p.add_argument("--seed", action="store_true", help="seed sample clinical data")
    p.add_argument("--skip-register", action="store_true",
                   help="account already exists; log in and continue")
    args = p.parse_args()

    password = os.environ.get("ALAFIA_NEW_PASSWORD")
    if not password:
        print("ALAFIA_NEW_PASSWORD is not set — export it rather than passing a "
              "password on the command line (argv is visible in `ps` and in "
              "shell history).", file=sys.stderr)
        return 1

    log(f"api={args.api}")
    api = Api(args.api)

    if not args.skip_register:
        register(api, args.email, password, args.name)
    login(api, args.email, password)

    if args.role:
        role_id = claim_role(api, args.role, args.primary)
        profile = {k: v for k, v in {
            "specialty": args.specialty,
            "practice_name": args.practice,
            "accepting_patients": True,
            "telemedicine_available": True,
        }.items() if v is not None}
        if profile:
            set_profile(api, role_id, profile)

    if args.seed:
        seed(api)

    me = api.get("/users/me")
    if me.status_code == 200:
        u = me.json()
        log(f"done — id={u['id']} primary_role={u.get('primary_role')} "
            f"active_roles={u.get('active_roles')}")
    else:
        log(f"done (could not re-read /users/me: HTTP {me.status_code})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
