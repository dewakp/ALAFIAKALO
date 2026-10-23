# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Sanity-audit every stored per-100 g food profile. READ-ONLY.

For every row of food_nutrient_cache and learned_food_nutrients:

  1. ARITHMETIC (deterministic, no opinion):
       - energy above pure fat (>902 kcal/100 g) is impossible
       - protein + carbs + fat above 100 g per 100 g is impossible
       - Atwater disagreement: stated kcal vs 4P + 4C + 9F
       - an all-zero / empty profile
  2. RETRIEVAL: the USDA record the lookup actually matched (description,
     data type, category), fetched by fdc_id from FoodData Central.
  3. LLM JUDGEMENT, given 1 and 2: is the matched record the same food the
     name means, and what per-100 g range would that food have?

Output: one JSON line per row in results.jsonl, plus summary on stdout.
Nothing is written to any database.

    docker compose run --rm --no-deps -v "$PWD/audit:/audit" \
      -e OLLAMA_FIRST=false -e OLLAMA_REQUIRED=false -e PYTHONPATH=/ml/src:/app \
      -e DATABASE_URL=postgresql+asyncpg://alafia:alafia@db:5432/alafia \
      backend python scripts/audit_food_cache.py
"""
import asyncio, json, os, time
from pathlib import Path

import httpx
from sqlalchemy import text

from app.core.database import async_session  # type: ignore
from app.services.alafia_model_service import alafia_chat, ALAFIAModelError

OUT = Path(os.environ.get("AUDIT_OUT", "/audit"))
USDA_KEY = os.environ.get("USDA_API_KEY", "DEMO_KEY")
BATCH = int(os.environ.get("AUDIT_BATCH", "12"))
LIMIT = int(os.environ.get("AUDIT_LIMIT", "0"))

KEYS = ["calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g",
        "sodium_mg", "potassium_mg", "phosphorus_mg", "cholesterol_mg"]


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def arithmetic(n: dict) -> list[str]:
    out = []
    kcal, p, c, fat = (f(n.get(k)) for k in ("calories", "protein_g", "carbs_g", "fat_g"))
    vals = [v for v in (f(n.get(k)) for k in KEYS) if v is not None]
    if not vals or all(v == 0 for v in vals):
        out.append("empty_profile")
    if kcal is not None and kcal > 902:
        out.append(f"energy_above_pure_fat:{kcal:.0f}")
    macro = sum(v for v in (p, c, fat) if v is not None)
    if macro > 102:
        out.append(f"macros_exceed_100g:{macro:.0f}")
    for k in KEYS:
        v = f(n.get(k))
        if v is not None and v < 0:
            out.append(f"negative:{k}")
    if None not in (kcal, p, c, fat) and kcal > 0:
        atw = 4 * p + 4 * c + 9 * fat
        if abs(kcal - atw) > max(40.0, 0.30 * max(kcal, atw)):
            out.append(f"atwater_mismatch:{kcal:.0f}_vs_{atw:.0f}")
    return out


async def usda_records(ids: list[int]) -> dict[int, dict]:
    cache_p = OUT / "usda_records.json"
    have = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    todo = [i for i in ids if str(i) not in have]
    async with httpx.AsyncClient(timeout=60) as cx:
        for k in range(0, len(todo), 20):
            chunk = todo[k:k + 20]
            for attempt in range(4):
                r = await cx.post(f"https://api.nal.usda.gov/fdc/v1/foods?api_key={USDA_KEY}",
                                  json={"fdcIds": chunk, "format": "full"})
                if r.status_code == 200:
                    break
                await asyncio.sleep(5 * (attempt + 1))
            r.raise_for_status()
            got = {d["fdcId"]: d for d in r.json()}
            for i in chunk:
                d = got.get(i)
                have[str(i)] = None if d is None else {
                    "description": d.get("description"),
                    "dataType": d.get("dataType"),
                    "category": (d.get("foodCategory") or {}).get("description")
                    if isinstance(d.get("foodCategory"), dict) else d.get("brandedFoodCategory"),
                    "brand": d.get("brandOwner") or d.get("brandName"),
                }
            cache_p.write_text(json.dumps(have))
            print(f"  usda {min(k + 20, len(todo))}/{len(todo)}", flush=True)
    return {int(k): v for k, v in have.items()}


SYSTEM = """You audit a food-nutrient lookup table for a clinical nutrition app.
Each row is a NAME a patient typed and the per-100 g profile the system stored
for it. Some rows also carry the USDA record the system MATCHED to that name.

For each row answer strictly from food science, independently of the stored
numbers:
- name_kind: "single_food" | "composite_meal" | "not_food"
- match: only when a USDA record is given — "same_food" if the record is the
  food the name means (a reasonable form of it: raw/cooked/canned all count),
  "different_food" if it is a different food (e.g. an oil extracted from the
  named food, a dried/powdered concentrate when the name is the fresh food, an
  unrelated product sharing a word), else "unsure". Omit/null when no record.
- expected: the plausible per-100 g range for what the NAME means, as
  {"kcal":[lo,hi],"protein_g":[lo,hi],"fat_g":[lo,hi],"carbs_g":[lo,hi]}.
  Ranges should be wide enough to cover ordinary preparations, not one recipe.
- verdict: "ok" | "wrong" | "unsure" — is the STORED profile a credible
  per-100 g profile for the name?
- reason: one short sentence.

Reply with JSON only: {"rows":[{"id":<id>, "name_kind":..., "match":...,
"expected":{...}, "verdict":..., "reason":...}, ...]} — one entry per input row.
"""


def row_text(r: dict) -> str:
    n = r["nutrients"]
    prof = ", ".join(f"{k}={round(f(n.get(k)), 2)}" for k in KEYS if f(n.get(k)) is not None)
    s = f'id={r["id"]} | name="{r["name"]}" | source={r["source"]} | stored per 100 g: {prof}'
    u = r.get("usda")
    if u:
        s += (f' | MATCHED USDA fdc {r["fdc_id"]}: "{u["description"]}" '
              f'({u["dataType"]}; category: {u.get("category")}; brand: {u.get("brand")})')
    return s


async def judge(batch: list[dict]) -> dict[str, dict]:
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "\n".join(row_text(r) for r in batch)}]
    for attempt in range(3):
        try:
            raw = await alafia_chat(msgs, temperature=0.0, max_tokens=4000, json_mode=True)
            s = raw[raw.find("{"): raw.rfind("}") + 1]
            rows = json.loads(s)["rows"]
            return {str(x["id"]): x for x in rows}
        except (ALAFIAModelError, ValueError, KeyError) as e:
            print(f"  judge retry {attempt}: {type(e).__name__}: {e}"[:200], flush=True)
            await asyncio.sleep(3)
    return {}


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_session() as db:
        rows = [dict(m) for m in (await db.execute(text(
            "select 'cache:'||id as id, food_name_normalized as name, source, fdc_id, "
            "nutrients::text as nutrients, band_category, hit_count from food_nutrient_cache "
            "union all select 'learned:'||id, food_name_normalized, source, null, "
            "nutrients::text, null, sample_count from learned_food_nutrients order by 1"
        ))).mappings()]
    for r in rows:
        r["nutrients"] = json.loads(r["nutrients"])
    if LIMIT:
        rows = rows[:LIMIT]
    print(f"rows: {len(rows)}", flush=True)

    ids = sorted({r["fdc_id"] for r in rows if r["fdc_id"]})
    print(f"fdc ids to retrieve: {len(ids)}", flush=True)
    recs = await usda_records(ids)
    for r in rows:
        r["usda"] = recs.get(r["fdc_id"]) if r["fdc_id"] else None
        r["arith"] = arithmetic(r["nutrients"])

    done_p = OUT / "results.jsonl"
    done = {}
    if done_p.exists():
        for line in done_p.read_text().splitlines():
            x = json.loads(line)
            done[x["id"]] = x
    todo = [r for r in rows if r["id"] not in done]
    print(f"to judge: {len(todo)}", flush=True)
    sem = asyncio.Semaphore(int(os.environ.get("AUDIT_CONCURRENCY", "4")))

    async def run(batch):
        async with sem:
            j = await judge(batch)
            with done_p.open("a") as fh:
                for r in batch:
                    fh.write(json.dumps({**{k: r[k] for k in ("id", "name", "source", "fdc_id",
                                         "band_category", "hit_count", "nutrients", "usda", "arith")},
                                         "llm": j.get(r["id"])}) + "\n")
            print(f"  judged {len(batch)} ({'ok' if j else 'NO ANSWER'})", flush=True)

    t = time.time()
    await asyncio.gather(*(run(todo[i:i + BATCH]) for i in range(0, len(todo), BATCH)))
    print(f"done in {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
