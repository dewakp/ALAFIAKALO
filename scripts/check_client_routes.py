#!/usr/bin/env python3
"""Every path a client calls must exist on the backend.

Four calls to routes that never existed were shipped and invisible:

    iOS  DELETE /advanced-directives/{id}                 (route takes no id)
    iOS  POST   /chronic/therapy-sessions/{id}/clinical-notes  (route is /notes)
    iOS  POST   /diagnostics/crash-report                 (no such endpoint at all)
    web  DELETE /planners/exercise-plans/{id}             (route was never written)

All four are WRITES, and that is the pattern: a broken read shows an empty
screen and gets noticed, while a broken write fails into a `catch` that renders
as "nothing here yet". One of them silently discarded a clinician's note.

Run from the repo root with the dev stack up:

    python3 scripts/check_client_routes.py

Exits non-zero and names the offenders. Known blind spot, stated rather than
hidden: paths built from a variable (`api.get(path)`) cannot be resolved
statically — there is exactly one such call site today, `Admin.jsx`'s `call()`
wrapper, and its literals are listed in KNOWN_INDIRECT below.
"""
from __future__ import annotations

import collections
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Reachable only through a variable-path wrapper; verified by reading the caller.
KNOWN_INDIRECT = {
    "/admin/overview", "/admin/health", "/admin/token-usage", "/admin/users",
}

# Real routes that no client calls yet, on purpose. Keep this SHORT and justified.
INTENTIONALLY_UNCALLED_PREFIXES = (
    "/auth/signup/",   # two-step signup, gated off in production (DEPLOY.md)
)


def normalise(p: str) -> str:
    p = p.split("?")[0].strip()
    if p.startswith("/api/v1"):
        p = p[len("/api/v1"):]
    if not p.startswith("/"):
        p = "/" + p
    p = re.sub(r"\$\{[^}]*\}", "*", p)     # JS ${id} — before the bare-brace rule
    p = re.sub(r"\\\([^)]*\)", "*", p)     # Swift \(id)
    p = re.sub(r"\{[^}]*\}", "*", p)       # FastAPI {id}
    p = re.sub(r"\$\w+", "*", p)           # leftover $var
    p = re.sub(r"/\d+", "/*", p)           # literal ids
    return p.rstrip("/") or "/"


def backend_routes() -> set[str]:
    """Ask the running app, never grep for @router — prefixes live elsewhere."""
    code = (
        "from app.main import app;"
        "print('\\n'.join(sorted({r.path for r in app.routes "
        "if getattr(r,'path','').startswith('/api/v1')})))"
    )
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "-e", "PYTHONPATH=/app", "backend", "python", "-c", code],
        cwd=ROOT / "WEB", capture_output=True, text=True,
    )
    paths = [l for l in out.stdout.splitlines() if l.startswith("/api/v1")]
    if not paths:
        sys.exit("Could not read routes from the backend — is `docker compose up -d` running?\n"
                 + out.stderr[-400:])
    return {normalise(p) for p in paths}


def client_calls() -> dict[str, set[str]]:
    calls: dict[str, set[str]] = collections.defaultdict(set)
    sources = [
        (ROOT / "WEB/frontend/src", ("*.jsx", "*.js"),
         r"""api\.(?:get|post|put|patch|delete)\(\s*[`'"](?P<path>[^`'"]+)""", "web"),
        (ROOT / "IOS/ALAFIA", ("*.swift",),
         r"""APIClient\.shared\.\w+\(\s*"(?P<path>[^"]+)""", "ios"),
        (ROOT / "Android/app/src/main", ("*.kt",),
         r"""@(?:GET|POST|PUT|PATCH|DELETE)\(\s*"(?P<path>[^"]+)""", "android"),
    ]
    for root, globs, pattern, label in sources:
        for g in globs:
            for f in root.rglob(g):
                if any(x in str(f) for x in ("node_modules", "/build/", "DerivedData", "/dist/")):
                    continue
                src = f.read_text(errors="replace")
                for m in re.finditer(pattern, src):
                    raw = m.group("path")
                    if not raw or raw.startswith("http"):
                        continue
                    # A partial template literal (`/nutrition/${qs`) is a parse
                    # artifact of a path assembled from a variable, not a call.
                    if raw.count("${") != raw.count("}"):
                        continue
                    calls[normalise(raw)].add(f"{label}:{f.relative_to(ROOT)}")
    return calls


def matches(call: str, route: str) -> bool:
    """Segment-wise match where `*` is a wildcard on EITHER side.

    Exact string equality was wrong in both directions: a client literal
    (`/sync/status/healthkit`) has to match a route parameter
    (`/sync/status/{platform}`), and a client-side variable (an action built at
    runtime) has to match a literal route segment (`/invitations/{id}/accept`).
    Both showed up as false alarms, and a guard that cries wolf gets ignored.
    """
    a, b = call.split("/"), route.split("/")
    if len(a) != len(b):
        return False
    return all(x == y or x == "*" or y == "*" for x, y in zip(a, b))


def resolves(call: str, served: set[str]) -> bool:
    return any(matches(call, r) for r in served)


def main() -> None:
    served = backend_routes()
    calls = client_calls()

    broken = {p: who for p, who in calls.items()
              if not resolves(p, served) and p not in KNOWN_INDIRECT}
    if broken:
        print("Client calls to routes that DO NOT EXIST:\n")
        for p, who in sorted(broken.items()):
            print(f"  {p}")
            for w in sorted(who):
                print(f"      {w}")
        sys.exit(f"\n{len(broken)} broken client call(s).")

    uncalled = sorted(
        p for p in served
        if not any(matches(c, p) for c in calls) and p not in KNOWN_INDIRECT
        and not p.startswith(INTENTIONALLY_UNCALLED_PREFIXES)
    )
    print(f"OK — every client call resolves to a real route "
          f"({len(calls)} distinct paths against {len(served)} routes).")
    print(f"note: {len(uncalled)} backend routes have no client caller "
          f"(informational; run with --list-uncalled to see them).")
    if "--list-uncalled" in sys.argv:
        for p in uncalled:
            print("   ", p)


if __name__ == "__main__":
    main()
