#!/usr/bin/env python3
"""Contract-drift check: do the iOS models still match the live backend?

The recurring class of ALAFIA bugs (Chronic Conditions "wrong format", Privacy
"is missing", Wellness recommendations silently empty) is all ONE thing: the
frontends hand-maintain copies of the backend's schema, they drift, and nothing
catches it until a user opens a broken screen.

This is the cheap first-line guard. It parses every iOS Codable/Decodable struct,
fetches the real response for each data endpoint, and flags any where a
**non-optional field is null/missing** (would throw at decode → screen silently
empties) or a **naive datetime** appears (bit us on Chronic Conditions; still a
risk for Android/Web). Exit code is non-zero on drift, so it can gate a release.

Usage:
    ALAFIA_DRIFT_USER=you@x.com ALAFIA_DRIFT_PASS=... python3 tools/contract_drift_check.py
    # optional: ALAFIA_API=https://api.alafia.app/api/v1   ALAFIA_TOKEN=<bearer to skip login>

Scope/limits: catches missing/null required fields + naive datetimes via an
auto-matcher. It does NOT yet do a full Swift decode (type mismatches, nested
shapes) — for that, generate models from /openapi.json or add golden-response
XCTest cases. Even so, this found the Wellness wrapper-vs-array bug.
"""
from __future__ import annotations
import os, re, json, glob, ssl, sys, datetime, urllib.request, urllib.parse, urllib.error, http.cookiejar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IOS = os.path.join(ROOT, "IOS", "ALAFIA")
API = os.environ.get("ALAFIA_API", "https://api.alafia.app/api/v1")
CTX = ssl._create_unverified_context()


def parse_models() -> dict:
    """name -> {'req': {backend_key,...}, 'keys': {backend_key,...}}"""
    models = {}
    struct_re = re.compile(r'struct\s+(\w+)\s*:\s*[^{\n]*\b(?:Codable|Decodable)\b[^{]*\{', re.M)
    for path in glob.glob(f"{IOS}/**/*.swift", recursive=True):
        src = open(path, encoding='utf-8', errors='ignore').read()
        for m in struct_re.finditer(src):
            name, i, depth = m.group(1), m.end(), 1
            j = i
            while j < len(src) and depth:
                depth += (src[j] == '{') - (src[j] == '}'); j += 1
            body = src[i:j - 1]
            props = {fm.group(1): fm.group(2).strip().endswith('?')
                     for fm in re.finditer(r'^\s*(?:let|var)\s+(\w+)\s*:\s*([^\n={]+?)\s*(?:=|$)', body, re.M)}
            keymap = {}
            ck = re.search(r'enum\s+CodingKeys[^{]*\{([^}]*)\}', body, re.S)
            if ck:
                for line in ck.group(1).splitlines():
                    line = line.strip()
                    if not line.startswith('case'):
                        continue
                    for part in line[4:].split(','):
                        part = part.strip()
                        mm = re.match(r'(\w+)\s*=\s*"([^"]+)"', part)
                        if mm:
                            keymap[mm.group(1)] = mm.group(2)
                        elif re.match(r'\w+$', part):
                            keymap[part] = part
                decoded = set(keymap)
            else:
                decoded = set(props); keymap = {k: k for k in props}
            req = {keymap.get(s, s) for s in decoded if s in props and not props[s]}
            keys = {keymap.get(s, s) for s in decoded}
            if keys:
                models[name] = {"req": req, "keys": keys}
    return models


def login() -> str:
    if os.environ.get("ALAFIA_TOKEN"):
        return os.environ["ALAFIA_TOKEN"]
    user, pw = os.environ.get("ALAFIA_DRIFT_USER"), os.environ.get("ALAFIA_DRIFT_PASS")
    if not (user and pw):
        sys.exit("set ALAFIA_DRIFT_USER/ALAFIA_DRIFT_PASS (or ALAFIA_TOKEN)")
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=CTX))
    op.open(API + "/auth/csrf-cookie", timeout=20)
    csrf = next((c.value for c in cj if c.name == "csrf_token"), "")
    req = urllib.request.Request(API + "/auth/login",
        data=urllib.parse.urlencode({"username": user, "password": pw}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "X-CSRF-Token": csrf})
    return json.loads(op.open(req, timeout=20).read())["access_token"]


def get(path: str, tok: str):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=25) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()


NAIVE_DT = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$')  # no Z/offset

# Parameterless data GETs the app decodes. Extend as endpoints are added.
TODAY = datetime.date.today().isoformat()
ENDPOINTS = [
 "/users/me", "/chronic/conditions", "/medications/", f"/medications/dose-logs?log_date={TODAY}",
 "/elimination/bowel?limit=50", "/elimination/vomiting?limit=50", "/elimination/urination?limit=50",
 "/fitness/", "/mood/", "/lifestyle/", "/nutrition/", "/labs/", "/pantry/", "/advanced-directives/",
 "/insurance/", "/physicians/saved/", "/sync/connections", "/wellness/score", "/wellness/improvements",
 "/mental-health/gratitude", "/mental-health/assessments", "/mental-health/stats",
 "/pharmacy/prescriptions", "/pharmacy/schedules", "/planners/exercise-plans",
 "/telehealth/sessions?limit=50", "/data-sharing/grants", "/surveillance/diseases",
 "/users/roles/me", "/privacy/settings", "/subscription/status",
]


def main() -> int:
    models = parse_models()
    tok = login()
    print(f"parsed {len(models)} iOS models; checking {len(ENDPOINTS)} endpoints\n")

    def best_model(rk):
        best, score = None, -1
        for n, mv in models.items():
            inter = len(rk & mv["keys"])
            if inter > score and inter >= max(2, len(rk) * 0.5):
                best, score = n, inter
        return best

    drift = []
    for ep in ENDPOINTS:
        code, body = get(ep, tok)
        if code != 200:
            drift.append((ep, f"HTTP {code}")); continue
        try:
            d = json.loads(body)
        except Exception:
            drift.append((ep, "non-JSON")); continue
        recs = [r for r in (d if isinstance(d, list) else [d]) if isinstance(r, dict)]
        if not recs:
            print(f"  · {ep}  (empty)"); continue
        rk = set(recs[0].keys()); model = best_model(rk)
        issue = None
        if not model:
            issue = "no matching iOS model — shape may differ (e.g. wrapper vs array)"
        else:
            for r in recs:
                miss = [k for k in models[model]["req"] if k not in r or r[k] is None]
                if miss:
                    issue = f"model {model}: required {miss} null/missing"; break
        nd = [k for k, v in recs[0].items() if isinstance(v, str) and NAIVE_DT.match(v)]
        if issue:
            drift.append((ep, issue + (f"  [naive-dt: {','.join(nd)}]" if nd else "")))
        else:
            print(f"  ✓ {ep}  ({model})" + (f"  [naive-dt: {','.join(nd)}]" if nd else ""))

    if drift:
        print("\n✗ DRIFT:")
        for ep, msg in drift:
            print(f"  {ep}\n      {msg}")
        return 1
    print("\n✓ no contract drift detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
