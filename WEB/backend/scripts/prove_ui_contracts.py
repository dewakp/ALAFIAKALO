"""Drive every endpoint the three UIs call, against the running dev backend.

Not a unit test: this is real HTTP to http://localhost:8005 with a real account
and a real token, exercising the exact request/response shapes the web, iOS and
Android screens use. Run it after `docker compose up -d`.

Proves, in order:
  1. the dose guard REFUSES calcitriol at mg (the calcium-calcitriol class of error)
  2. the same dose in mcg is accepted
  3. an explicit acknowledgement can still record an unusual dose
  4. /medications/intake-intent reads "I take X" and supplies the dose from the
     history just written, WITH provenance, and writes nothing
  5. a meal that used to log as "unavailable" now resolves and its
     nutrient_status says so
"""

import sys
import time
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request
import json

# The real clients carry a CSRF cookie + matching header; so must this.
_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def _csrf() -> str:
    for c in _jar:
        if c.name == "csrf_token":
            return c.value
    return ""
from datetime import date

BASE = "http://localhost:8005/api/v1"
EMAIL = "uiproof@example.com"
PASSWORD = "ProofPassw0rd!23"

_failures: list[str] = []


def call(method, path, body=None, token=None, form=False, expect=None):
    url = f"{BASE}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    if method != "GET":
        token_value = _csrf()
        if token_value:
            headers["X-CSRF-Token"] = token_value
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _opener.open(req, timeout=60) as r:
            payload = json.loads(r.read() or b"null")
            status = r.status
    except urllib.error.HTTPError as e:
        payload = json.loads(e.read() or b"null")
        status = e.code
    if expect is not None and status != expect:
        _failures.append(f"{method} {path}: expected {expect}, got {status} — {payload}")
    return status, payload


def check(label, condition, detail=""):
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{(' — ' + str(detail)) if detail else ''}")
    if not condition:
        _failures.append(label)


print(f"account: {EMAIL}")
call("GET", "/auth/csrf-cookie")      # seeds the cookie the header must match
# Direct registration is closed in dev (TWO_STEP_SIGNUP_REQUIRED defaults on),
# so the account is seeded by scripts/make_proof_user.py. Everything below is
# real HTTP through the same paths the three UIs use.
_, tok = call("POST", "/auth/login", {"username": EMAIL, "password": PASSWORD}, form=True)
token = tok.get("access_token")
if not token:
    sys.exit(f"login failed: {tok}")

today = str(date.today())

print("\n1. dose guard refuses calcitriol in mg")
status, body = call("POST", "/medications/dose-logs", {
    "medication_name": "Calcitriol", "log_date": today,
    "dose_amount": 1000, "dose_unit": "mg",
}, token=token)
detail = (body or {}).get("detail") or {}
codes = [f.get("code") for f in (detail.get("findings") or [])]
check("refused with 422", status == 422, status)
check("names the reason", bool(codes), codes)

print("\n2. a real calcitriol dose is accepted")
# log_time is part of `uq_dose_log_per_user_date_med_dose`, so three identical
# doses need three distinct times AND the script has to be re-runnable.
#
# Two bugs lived here in turn. It first derived the minute from
# `int(time.time()) % 60` — the seconds hand — so three fast calls landed in the
# same second and the 2nd was refused 409 as a duplicate, reporting itself as
# "0.5 mcg accepted — 409", i.e. as a broken dose guard. Replacing that with
# fixed times fixed the race and introduced a worse one: the script could then
# only pass ONCE PER DAY, and a second run that day failed the same way.
#
# Its own rows for today are cleared first — through the ordinary
# DELETE /medications/dose-logs/{id} the clients use, not a test-only endpoint
# — so the run proves the guard rather than the calendar.
_st, _existing = call("GET", "/medications/dose-logs", token=token)
for _row in (_existing if isinstance(_existing, list) else []):
    if (str(_row.get("log_date", "")).startswith(today)
            and str(_row.get("medication_name", "")).lower() == "calcitriol"):
        call("DELETE", f"/medications/dose-logs/{_row['id']}", token=token)

for i, amount in enumerate((0.5, 0.5, 0.5)):
    status, body = call("POST", "/medications/dose-logs", {
        "medication_name": "Calcitriol", "log_date": today,
        "log_time": f"{8 + i:02d}:15",
        "dose_amount": amount, "dose_unit": "mcg",
    }, token=token)
    if status != 201:
        break
check("0.5 mcg accepted", status == 201, status)

print("\n3. an acknowledged unusual dose still records")
status, _ = call("POST", "/medications/dose-logs", {
    "medication_name": "Calcitriol", "log_date": today, "log_time": "23:59",
    "dose_amount": 1000, "dose_unit": "mg", "acknowledge_unusual": True,
}, token=token)
check("override accepted", status == 201, status)

print("\n4. intake-intent reads free text and supplies the dose from history")
status, proposal = call("POST", "/medications/intake-intent",
                        {"text": "I take Calcitriol"}, token=token)
check("200", status == 200, status)
check("names the medication", (proposal or {}).get("medication_name", "").lower() == "calcitriol",
      (proposal or {}).get("medication_name"))
check("supplied a dose", (proposal or {}).get("dose_amount") is not None,
      (proposal or {}).get("dose_amount"))
check("says where it came from", bool((proposal or {}).get("provenance")),
      (proposal or {}).get("provenance"))
check("requires confirmation", (proposal or {}).get("needs_confirmation") is True)

before = call("GET", "/medications/dose-logs", token=token)[1]
call("POST", "/medications/intake-intent", {"text": "I take Calcitriol"}, token=token)
after = call("GET", "/medications/dose-logs", token=token)[1]
check("wrote NOTHING", len(before or []) == len(after or []),
      f"{len(before or [])} -> {len(after or [])}")

print("\n5. a meal that used to log as 'unavailable'")
status, meal = call("POST", "/nutrition/estimate-meal", {
    "description": "8 Fl oz Boost Glucose Control + 0.5 cup of Roasted corn flour",
    "log_date": today, "meal_type": "snack",
}, token=token)
check("200", status == 200, status)
agg = (meal or {}).get("aggregate_nutrients") or {}
check("resolved nutrients", bool(agg.get("calories")), agg.get("calories"))

logs = call("GET", "/nutrition/", token=token)[1] or []
row = next((r for r in logs if "Boost" in (r.get("food_name") or "")), None)
check("log row exists", row is not None)
if row:
    check("nutrient_status is done", row.get("nutrient_status") == "done",
          row.get("nutrient_status"))
    check("calories stored", bool(row.get("calories")), row.get("calories"))

print("\n" + ("ALL CONTRACTS PROVED" if not _failures
              else f"{len(_failures)} FAILURE(S):\n  - " + "\n  - ".join(_failures)))
sys.exit(1 if _failures else 0)
