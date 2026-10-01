"""Does the LOINC resolver answer CORRECTLY — not merely often?

`docparse_corpus_check.py` scores reference-range recall, and §3ab records what
that cost: a parser can emit a hundred prose rows and still report 100%. The
first measurement of this resolver repeated the mistake one level up. It
reported "LOINC resolves 33.8% of production's stored names, against the hand
written dictionary's 33.1%" — and counted `Hemoglobin -> 786-4` among the
successes. 786-4 is MCHC. The right answer is 718-7.

A coverage number cannot see that, because a wrong code and a right code are
both "resolved". This script measures the thing that matters: of the names we DO
resolve, how many were decided by COMMON_TEST_RANK between tests the authority
itself says are different?

THE AMBIGUITY TEST, AND WHY IT NEEDS NO JUDGEMENT
-------------------------------------------------
LOINC's six axes exist because no single axis identifies an observation. When a
printed name resolves through an index whose key is shared by terms differing in
(SYSTEM, PROPERTY), the resolver has CHOSEN between clinically distinct tests
using a popularity tiebreak, with nothing in the document supporting the choice.

That is computable, and it asserts no clinical identity of our own: the
authority's axes decide what counts as distinct.

⚠️ THE FIRST VERSION OF THIS SCRIPT MIS-ATTRIBUTED EVERY TIER.
`_tier_of` was written before `_by_long_head` existed and probed only shortname,
component and synonym — so a name answered from the head index was reported as
"component" whenever its key also sat there, and the per-tier counts summed to
73 against 76 resolved. It reported "32.9% chosen by rank" about a code path
that is not the one `resolve()` takes. A guard measuring the wrong path is §3aa
again, so the tier walk below is kept in the SAME ORDER as `loinc.resolve()` and
a test asserts the two agree.

Run it against the dev copy of production (§1), which is where the real
vocabulary lives:

    docker compose --profile test run --rm \
      -e DATABASE_URL="postgresql+asyncpg://alafia:alafia@db:5432/alafia" \
      backend-test python scripts/loinc_precision_audit.py

With no database it falls back to the hand-written dictionary's own keys and
says so — a weaker sample, being the names somebody already thought of, so the
figure is always reported with its source attached.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/app")

from app.services.docparse import loinc  # noqa: E402


async def _names_from_db() -> tuple[list[str], str]:
    """Distinct stored test names, or an empty list if no database is reachable."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return [], "no DATABASE_URL"
    try:
        import asyncpg
    except ImportError:
        return [], "asyncpg not installed"

    dsn = url.replace("postgresql+asyncpg://", "postgresql://")
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=10)
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"
    try:
        rows = await conn.fetch(
            "SELECT test_name, count(*) AS n FROM lab_results "
            "WHERE test_name IS NOT NULL AND btrim(test_name) <> '' "
            "GROUP BY test_name ORDER BY n DESC"
        )
    except Exception as exc:
        await conn.close()
        return [], f"{type(exc).__name__}: {exc}"
    await conn.close()
    return [r["test_name"] for r in rows], "production vocabulary (dev copy)"


def _names_from_dictionary() -> list[str]:
    from app.services.docparse import dictionaries

    names = getattr(dictionaries, "ANALYTE_NAMES", {})
    return sorted(names.keys() if isinstance(names, dict) else names)


def _head(term) -> str:
    """The analyte head of LONG_COMMON_NAME — mirrors the resolver's index."""
    return loinc._norm((term.long_name or "").split("[")[0])


def _rival_index(cat):
    """key -> {(system, property): best term}, per index the resolver consults.

    Two terms in the same bucket with different (SYSTEM, PROPERTY) are the
    authority saying they are different observations.
    """
    short: dict[str, dict] = defaultdict(dict)
    head: dict[str, dict] = defaultdict(dict)
    comp: dict[str, dict] = defaultdict(dict)
    for term in cat.terms:
        group = (term.system, term.property)
        for key, bucket in (
            (loinc._norm(term.short_name), short),
            (_head(term), head),
            (loinc._norm(term.component), comp),
        ):
            if not key:
                continue
            prev = bucket[key].get(group)
            if prev is None or term.rank < prev.rank:
                bucket[key][group] = term
    return short, head, comp


def _answering_tier(cat, key: str) -> str:
    """Which tier `loinc.resolve()` would answer from — SAME ORDER as resolve()."""
    if key in cat._by_short:
        return "shortname"
    if key in cat._by_long_head:
        return "head"
    if key in cat._by_comp:
        return "component"
    if key in cat._by_synonym:
        return "synonym"
    return "-"


async def main() -> int:
    cat = loinc._catalog()
    if not cat.terms:
        print("catalog absent — nothing to audit")
        return 1

    names, source = await _names_from_db()
    if not names:
        names, source = _names_from_dictionary(), (
            f"hand-written dictionary keys ({source})"
        )

    short_rivals, head_rivals, comp_rivals = _rival_index(cat)
    rivals_for = {"shortname": short_rivals, "head": head_rivals,
                  "component": comp_rivals}

    resolved = 0
    by_tier: dict[str, int] = defaultdict(int)
    suspect: list[tuple[str, object, str, list]] = []

    for name in names:
        term = loinc.resolve(name)
        if term is None:
            continue
        resolved += 1
        key = loinc._norm(name)
        tier = _answering_tier(cat, key)
        by_tier[tier] += 1
        bucket = rivals_for.get(tier, {}).get(key, {})
        if len(bucket) > 1:
            suspect.append((name, term, tier, list(bucket.values())))

    total = len(names)
    print(f"source: {source}")
    print(f"names:  {total}")
    print(f"catalog: {loinc.catalog_version()}  ({len(cat.terms)} terms)\n")

    print(f"resolved        {resolved:4d}  ({resolved / total:.1%} of names)")
    for tier in ("shortname", "head", "component", "synonym"):
        print(f"  via {tier:12s}{by_tier[tier]:4d}")
    counted = sum(by_tier[t] for t in ("shortname", "head", "component", "synonym"))
    # The per-tier counts MUST sum to `resolved`. When they did not, the walk had
    # drifted from resolve()'s own order and every figure below was about a path
    # the resolver does not take.
    print(f"  {'(sum)':16s}{counted:4d}"
          f"{'' if counted == resolved else '   <-- DISAGREES WITH resolve()'}")
    print()

    # ⚠️ The SYNONYM tier is UNMEASURED, and saying so is the whole point.
    #
    # `_rival_index` can only build rival buckets for shortname, head and
    # component: those three live on `LoincTerm`. RELATEDNAMES2 is consumed at
    # load time into `_by_synonym` and never kept per term, so there is nothing
    # here to group by (SYSTEM, PROPERTY).
    #
    # The first version of this report therefore scored every synonym answer as
    # CONFIDENT — because `rivals_for.get("synonym", {})` is empty, so no synonym
    # answer could ever be flagged. That graded the resolver's own
    # self-described "weakest and noisiest" index as its cleanest, and reported
    # 47 confident resolutions when 46 of them had simply never been looked at.
    # Exactly the fault `_tier_of` had one function above: an index nobody
    # measures reads as clean (§3aa).
    #
    # So they are counted apart. An unmeasured answer is not a good one.
    unmeasured = by_tier["synonym"]
    confident = resolved - len(suspect) - unmeasured
    print(f"CHOSEN BY RANK BETWEEN DISTINCT TESTS: {len(suspect)}"
          f"  ({len(suspect) / max(resolved, 1):.1%} of resolutions)")
    print(f"UNMEASURED (synonym tier — no rival data to check): {unmeasured}")
    print(f"DETERMINATE (one distinct test for the key): {confident}"
          f"  ({confident / total:.1%} of all names)\n")

    for name, term, tier, group in suspect[:20]:
        print(f"  {name!r} [{tier}] -> {term.loinc_num} {term.short_name!r}")
        for rival in sorted(group, key=lambda t: t.rank)[:4]:
            mark = "  <-- chosen" if rival.loinc_num == term.loinc_num else ""
            print(f"        {rival.loinc_num:10s} rank={rival.rank:<11}"
                  f" {rival.system:12s} {rival.property:12s}"
                  f" {rival.short_name}{mark}")
        print()
    if len(suspect) > 20:
        print(f"  … and {len(suspect) - 20} more\n")

    # Named cases worth watching: a singular/plural difference in the PRINTED
    # word flips the analyte between a count and a volume, because LOINC heads
    # them 'platelet' and 'platelets'. Neither index can see that; only the
    # document's own context could.
    print("singular/plural, same report, different analyte:")
    for probe in ("Platelet", "Platelets", "Platelet Count"):
        t = loinc.resolve(probe)
        print(f"  {probe:16s} -> {t.loinc_num if t else '-':10s}"
              f" {t.short_name if t else '-'}")

    return 1 if suspect else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
