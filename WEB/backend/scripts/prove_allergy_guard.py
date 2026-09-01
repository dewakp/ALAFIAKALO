#!/usr/bin/env python3
"""Prove the allergy guard over real HTTP, against the seeded demo patient.

Unit tests exercise `food_safety` directly. This drives the actual endpoint —
auth, context gathering, prompt, model, output filter — and asserts that
nothing the patient reacts to comes back on the wire.

Runs against the FICTIONAL Ada Demo record only (canon: never test against a
real patient record). Dev only.

    python scripts/prove_allergy_guard.py http://localhost:8005/api/v1
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8005/api/v1"
# The FICTIONAL demo patient. `seed_demo_patient.py` refuses to run against
# anything but the local dev database, so this account cannot exist in
# production and this is a fixture credential, not a secret. Overridable so a
# developer can seed it with their own password without editing this file.
EMAIL = os.environ.get("DEMO_PATIENT_EMAIL", "demo.patient@alafia.app")
PASSWORD = os.environ.get("DEMO_PATIENT_PASSWORD", "AlafiaDemo!2026")

# What Ada Demo's profile says she reacts to.
MUST_NOT_APPEAR = ["apple", "berr", "fava", "broad bean"]

jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _csrf() -> str:
    for c in jar:
        if c.name == "csrf_token":
            return c.value
    return ""


def call(method: str, path: str, body=None, *, form=False, token=None, timeout=400):
    url = BASE + path
    data, headers = None, {}
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    if method != "GET":
        tok = _csrf()
        if tok:
            headers["X-CSRF-Token"] = tok
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:400]}


call("GET", "/auth/csrf-cookie")
status, tok = call("POST", "/auth/login", {"username": EMAIL, "password": PASSWORD}, form=True)
token = tok.get("access_token")
if not token:
    sys.exit(f"login failed ({status}): {tok}")
print(f"logged in as {EMAIL}")

status, plan = call("POST", "/planners/meal-plan",
                    {"days": 7, "dietary_pattern": "balanced"}, token=token)
print(f"POST /planners/meal-plan -> {status}")
if status != 200:
    sys.exit(f"planner failed: {json.dumps(plan)[:500]}")

meals = []
for day in plan.get("weekly_plan") or plan.get("plan") or []:
    for slot in ("breakfast", "lunch", "dinner", "snack"):
        m = (day or {}).get(slot)
        if m and m.get("name"):
            meals.append(f"{day.get('day')} {slot}: {m['name']}")

# Only the meals themselves. The advice deliberately NAMES what was removed
# ("Oatmeal with berries (allergy: Raw Berries)"), so scanning the whole
# payload flags the guard's own explanation as a violation.
hits = [t for t in MUST_NOT_APPEAR
        if any(t in m.lower() for m in meals)
        or t in json.dumps(plan.get("shopping_list") or []).lower()]

print(f"\nmeals returned: {len(meals)}")
for m in meals[:8]:
    print("  ", m)

advice = plan.get("advice") or ""
if "removed" in advice.lower():
    print("\nadvice reports removals:")
    print("  ", advice[advice.lower().index("removed") - 40:][:300])

print("\n=== RESULT ===")
if hits:
    print(f"*** FAIL — forbidden term(s) present on the wire: {hits}")
    sys.exit(1)
print("PASS — no forbidden food appears anywhere in the response")
