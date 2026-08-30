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
import json
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


def backend_route_methods() -> dict[str, set[str]]:
    """{normalised path: {METHOD, ...}} as the running app actually serves it.

    The path-only check below reported "every client call resolves to a real
    route" while Android declared `@PUT("nutrition/{id}")` against a path the
    server serves only as PATCH. A call that reaches a real path with a method
    nobody handles is a 405, which is exactly the class of dead client call this
    script exists to catch — its own docstring cites two of them.
    """
    code = (
        "from app.main import app;"
        "import json;"
        "print(json.dumps([[r.path, sorted(getattr(r,'methods',None) or [])] "
        "for r in app.routes if getattr(r,'path','').startswith('/api/v1')]))"
    )
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "-e", "PYTHONPATH=/app", "backend", "python", "-c", code],
        cwd=ROOT / "WEB", capture_output=True, text=True,
    )
    line = next((l for l in out.stdout.splitlines() if l.startswith("[")), None)
    if not line:
        return {}
    table: dict[str, set[str]] = collections.defaultdict(set)
    for path, methods in json.loads(line):
        table[normalise(path)].update(m.upper() for m in methods)
    return table


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


#: {normalised path: {METHOD, ...}} the clients actually use.
CALL_METHODS: dict[str, set[str]] = collections.defaultdict(set)
#: {(path, METHOD): {file, ...}} — so a wrong-method report names the client
#: that actually used that verb, not every client that touches the path.
CALL_METHOD_FILES: dict[tuple[str, str], set[str]] = collections.defaultdict(set)


def client_calls() -> dict[str, set[str]]:
    calls: dict[str, set[str]] = collections.defaultdict(set)
    sources = [
        (ROOT / "WEB/frontend/src", ("*.jsx", "*.js"),
         r"""api\.(?P<verb>get|post|put|patch|delete)\(\s*[`'"](?P<path>[^`'"]+)""", "web"),
        (ROOT / "IOS/ALAFIA", ("*.swift",),
         r"""APIClient\.shared\.(?P<verb>\w+)\(\s*"(?P<path>[^"]+)""", "ios"),
        (ROOT / "Android/app/src/main", ("*.kt",),
         r"""@(?P<verb>GET|POST|PUT|PATCH|DELETE)\(\s*"(?P<path>[^"]+)""", "android"),
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
                    #
                    # Only when there IS a `${`. Without that guard the test was
                    # `count("${") != count("}")`, which is 0 != 1 for a Kotlin
                    # or Swift path parameter — so EVERY Android route written
                    # `"nutrition/{id}"` was silently discarded, along with
                    # mood/{id}, labs/{id}, medications/{id} and the rest. The
                    # checker reported "every client call resolves" while never
                    # having looked at them.
                    if "${" in raw and raw.count("${") != raw.count("}"):
                        continue
                    key = normalise(raw)
                    calls[key].add(f"{label}:{f.relative_to(ROOT)}")
                    verb = (m.groupdict().get("verb") or "").upper()
                    # iOS wraps verbs (getWithCache, postForm, postImages…);
                    # take the leading HTTP verb off the method name.
                    for known in ("DELETE", "PATCH", "POST", "PUT", "GET"):
                        if verb.startswith(known):
                            CALL_METHODS[key].add(known)
                            CALL_METHOD_FILES[(key, known)].add(
                                f"{label}:{f.relative_to(ROOT)}")
                            break
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

    # A real path reached with a method nobody serves is a 405 — just as dead as
    # a missing path, and invisible to the check above. Android declared
    # `@PUT("nutrition/{id}")` against a route served only as PATCH.
    served_methods = backend_route_methods()
    wrong_method: list[str] = []
    for path, verbs in sorted(CALL_METHODS.items()):
        if path in KNOWN_INDIRECT:
            continue
        allowed: set[str] = set()
        for route, methods in served_methods.items():
            if matches(path, route):
                allowed |= methods
        if not allowed:
            continue                       # path check above already covered it
        for verb in sorted(verbs):
            if verb not in allowed:
                wrong_method.append(
                    f"  {verb:6s} {path}\n"
                    f"      served as: {', '.join(sorted(allowed))}\n"
                    f"      " + "\n      ".join(
                        sorted(CALL_METHOD_FILES.get((path, verb), ()))))
    if wrong_method:
        print("Client calls using a method the route does NOT serve (405):\n")
        print("\n".join(wrong_method))
        sys.exit(f"\n{len(wrong_method)} client call(s) with the wrong method.")

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
