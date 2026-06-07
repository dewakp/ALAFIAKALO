#!/usr/bin/env python3
"""
LAFIAKALO — LLM-Based Nutrition Backfill Pipeline
==================================================

Estimates macronutrient + micronutrient breakdown for 3,600+ historical food
descriptions that were logged but never analysed.

Provider-agnostic: supports OpenAI, Anthropic, and Google Gemini.

Usage
-----
    # Set ONE of these env vars:
    export OPENAI_API_KEY="sk-..."
    export ANTHROPIC_API_KEY="sk-ant-..."
    export GOOGLE_API_KEY="AIza..."

    # Run backfill (defaults to first available key)
    python scripts/backfill_nutrition.py

    # Specify provider + model explicitly
    python scripts/backfill_nutrition.py --provider openai --model gpt-4o-mini

    # Dry-run: estimate cost without calling the API
    python scripts/backfill_nutrition.py --dry-run

    # Resume from a previous interrupted run
    python scripts/backfill_nutrition.py --resume

    # Target only rows from 2020-2024
    python scripts/backfill_nutrition.py --date-from 2020-01-01 --date-to 2024-12-31

Architecture
------------
For each food description, the LLM is asked to:
1. Parse the free-text description into individual food items with quantities
2. Estimate per-item nutrient values (using global/ethnic food knowledge)
3. Sum to a meal total
4. Return structured JSON with 15 nutrient fields + item breakdown + confidence

This is inherently an *estimation* — the LLM acts as a trained nutritionist
doing a dietary recall analysis.  For renal patients, phosphorus/potassium/sodium
are especially critical, so we ask the model to flag high-risk nutrients.

Ethnic food coverage: Nigerian (eba, garri, ogbono, egusi, chin-chin, pounded
yam, jollof rice, suya, moi-moi, etc.), Caribbean, African-American soul food,
and standard American diet items.
"""

import argparse
import csv
import json
import os
import sys
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
ML_ROOT = SCRIPT_DIR.parent
DATA_PROC = ML_ROOT / "data" / "processed"
BACKFILL_DIR = ML_ROOT / "data" / "nutrition_backfill"
BACKFILL_DIR.mkdir(parents=True, exist_ok=True)

INPUT_CSV = DATA_PROC / "unified_nutrition.csv"
OUTPUT_CSV = BACKFILL_DIR / "nutrition_backfilled.csv"
PROGRESS_CSV = BACKFILL_DIR / "backfill_progress.csv"
ERRORS_LOG = BACKFILL_DIR / "backfill_errors.log"
ENRICHED_CSV = DATA_PROC / "unified_nutrition_enriched.csv"

# ─────────────────────────────────────────────────────────
# Nutrient columns we estimate
# ─────────────────────────────────────────────────────────
NUTRIENTS = [
    "calories", "protein", "carbs", "fat", "fiber", "sugar",
    "sodium", "potassium", "calcium", "iron", "phosphorus",
    "cholesterol", "vitamin_d", "vitamin_b12", "folic_acid",
]
UNITS = {
    "calories": "kcal", "protein": "g", "carbs": "g", "fat": "g",
    "fiber": "g", "sugar": "g", "sodium": "mg", "potassium": "mg",
    "calcium": "mg", "iron": "mg", "phosphorus": "mg",
    "cholesterol": "mg", "vitamin_d": "mcg", "vitamin_b12": "mcg",
    "folic_acid": "mcg",
}

# ─────────────────────────────────────────────────────────
# LLM system prompt — renal-dietitian persona
# ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are an expert registered dietitian and clinical nutritionist specialising in \
renal diets for hemodialysis patients.  You are highly knowledgeable about:
- West African / Nigerian cuisine (eba, garri, ogbono soup, egusi, moi-moi, \
chin-chin, pounded yam, jollof rice, suya, melon soup, amala, ewedu, etc.)
- Caribbean cuisine (callaloo, rice and peas, jerk, plantain, etc.)
- American foods (including soul food, fast food, packaged items)
- Standard USDA nutrient composition data
- How cooking methods affect nutrient content

For a hemodialysis patient, phosphorus, potassium, and sodium are critical to track.

When given a food description, you MUST:
1. Parse it into individual food items with estimated quantities.
2. Estimate nutrients for EACH item using your global food knowledge.
3. Sum to produce a MEAL TOTAL.
4. Return ONLY valid JSON — no markdown fences, no explanation outside JSON.

Return this exact JSON structure:
{
  "items": [
    {
      "name": "white rice",
      "quantity": "2 cups cooked (~380g)",
      "calories": 412,
      "protein": 8.4,
      "carbs": 89.6,
      "fat": 0.8,
      "fiber": 1.2,
      "sugar": 0.0,
      "sodium": 4,
      "potassium": 110,
      "calcium": 32,
      "iron": 3.6,
      "phosphorus": 136,
      "cholesterol": 0,
      "vitamin_d": 0,
      "vitamin_b12": 0,
      "folic_acid": 164
    }
  ],
  "meal_total": {
    "calories": 412,
    "protein": 8.4,
    "carbs": 89.6,
    "fat": 0.8,
    "fiber": 1.2,
    "sugar": 0.0,
    "sodium": 4,
    "potassium": 110,
    "calcium": 32,
    "iron": 3.6,
    "phosphorus": 136,
    "cholesterol": 0,
    "vitamin_d": 0,
    "vitamin_b12": 0,
    "folic_acid": 164
  },
  "confidence": "high",
  "notes": "Quantities clearly specified. Standard USDA values applied."
}

Rules:
- All numeric values must be numbers (not strings).
- "confidence" must be one of: "high", "medium", "low".
- If quantities are vague, estimate reasonable portions and set confidence to "medium".
- If the description is too ambiguous to estimate at all, return meal_total with all zeros and confidence "none".
- Use per-item nutrient estimation, NOT database lookups. Your training data includes USDA, global food composition databases, and ethnic food nutrient profiles.
- For Nigerian dishes, use common preparation methods: palm oil, ata rodo, onions, salt, meat stock, etc.
- Return ONLY the JSON object. No markdown, no code fences, no extra text.\
"""


def make_user_prompt(description: str, meal_type: str = "", food_item: str = "") -> str:
    """Build the user message from available food fields."""
    parts = []
    if description and str(description).strip() and str(description).lower() != "nan":
        parts.append(f"Food description: {description.strip()}")
    if food_item and str(food_item).strip() and str(food_item).lower() != "nan":
        parts.append(f"Food items: {food_item.strip()}")
    if meal_type and str(meal_type).strip() and str(meal_type).lower() != "nan":
        parts.append(f"Meal type: {meal_type.strip()}")
    return "\n".join(parts) if parts else ""


# ─────────────────────────────────────────────────────────
# Provider-Agnostic LLM Client
# ─────────────────────────────────────────────────────────
class LLMClient:
    """Unified interface for OpenAI, Anthropic, and Google Gemini APIs."""

    PROVIDERS = ("openai", "anthropic", "google")

    def __init__(self, provider: str, model: Optional[str] = None, api_key: Optional[str] = None):
        self.provider = provider.lower()
        assert self.provider in self.PROVIDERS, f"Unsupported provider: {provider}"

        # Resolve API key
        env_map = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "google": "GOOGLE_API_KEY"}
        self.api_key = api_key or os.getenv(env_map[self.provider], "")
        if not self.api_key:
            raise ValueError(f"No API key found.  Set {env_map[self.provider]} or pass --api-key.")

        # Resolve model
        model_defaults = {
            "openai":    "gpt-4o-mini",
            "anthropic": "claude-3-haiku-20240307",
            "google":    "gemini-2.0-flash",
        }
        self.model = model or model_defaults[self.provider]

        # Lazy-import the SDK
        self._client = None
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def _init_client(self):
        if self._client is not None:
            return
        if self.provider == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        elif self.provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        elif self.provider == "google":
            from google import genai
            self._client = genai.Client(api_key=self.api_key)

    def estimate_nutrients(self, user_prompt: str) -> dict:
        """Send food description to LLM and return parsed JSON."""
        self._init_client()

        if self.provider == "openai":
            return self._call_openai(user_prompt)
        elif self.provider == "anthropic":
            return self._call_anthropic(user_prompt)
        elif self.provider == "google":
            return self._call_google(user_prompt)

    def _call_openai(self, user_prompt: str) -> dict:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        self.total_input_tokens += resp.usage.prompt_tokens
        self.total_output_tokens += resp.usage.completion_tokens
        return json.loads(resp.choices[0].message.content)

    def _call_anthropic(self, user_prompt: str) -> dict:
        resp = self._client.messages.create(
            model=self.model,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.1,
            max_tokens=2000,
        )
        self.total_input_tokens += resp.usage.input_tokens
        self.total_output_tokens += resp.usage.output_tokens
        text = resp.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    def _call_google(self, user_prompt: str) -> dict:
        from google.genai import types as genai_types
        resp = self._client.models.generate_content(
            model=self.model,
            contents=f"{SYSTEM_PROMPT}\n\n{user_prompt}",
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2000,
                response_mime_type="application/json",
            ),
        )
        if hasattr(resp, "usage_metadata") and resp.usage_metadata:
            self.total_input_tokens += getattr(resp.usage_metadata, "prompt_token_count", 0) or 0
            self.total_output_tokens += getattr(resp.usage_metadata, "candidates_token_count", 0) or 0
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    def estimated_cost(self) -> float:
        """Return rough USD cost based on known pricing (as of early 2026)."""
        pricing = {  # per 1M tokens (input, output)
            "gpt-4o-mini":       (0.15,  0.60),
            "gpt-4o":            (2.50, 10.00),
            "gpt-4-turbo":       (10.0, 30.00),
            "claude-sonnet-4-20250514": (3.00, 15.00),
            "claude-3-5-haiku-20241022":  (0.80,  4.00),
            "gemini-2.0-flash":  (0.075, 0.30),
            "gemini-1.5-pro":    (1.25,  5.00),
        }
        inp_rate, out_rate = pricing.get(self.model, (1.0, 3.0))
        return (self.total_input_tokens * inp_rate + self.total_output_tokens * out_rate) / 1_000_000


# ─────────────────────────────────────────────────────────
# Row-level hash for dedup / resumption
# ─────────────────────────────────────────────────────────
def row_hash(date: str, desc: str, food_item: str) -> str:
    key = f"{date}|{desc}|{food_item}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────
# Main backfill logic
# ─────────────────────────────────────────────────────────
def load_data(date_from: str = None, date_to: str = None) -> pd.DataFrame:
    """Load nutrition CSV and filter to rows needing backfill."""
    df = pd.read_csv(INPUT_CSV, low_memory=False)
    df["date"] = pd.to_datetime(df["date"])

    # Identify rows that need backfill: no nutrient data OR all-zero
    for c in NUTRIENTS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    has_nutrients = df[NUTRIENTS[:6]].apply(pd.to_numeric, errors="coerce").notna().any(axis=1)
    all_zero = (df[NUTRIENTS[:4]].fillna(0).sum(axis=1) == 0) & has_nutrients  # has cols but all 0
    needs_backfill = ~has_nutrients | all_zero

    # Must have at least a food description
    has_text = (
        (df["description"].notna() & (df["description"].str.strip() != "")) |
        (df.get("food_item", pd.Series(dtype=str)).notna() & (df.get("food_item", pd.Series(dtype=str)).str.strip() != ""))
    )
    needs_backfill = needs_backfill & has_text

    if date_from:
        needs_backfill = needs_backfill & (df["date"] >= pd.to_datetime(date_from))
    if date_to:
        needs_backfill = needs_backfill & (df["date"] <= pd.to_datetime(date_to))

    print(f"Total rows:                  {len(df)}")
    print(f"Rows already have nutrients: {(~needs_backfill).sum()}")
    print(f"Rows needing backfill:       {needs_backfill.sum()}")
    print(f"Date range of backfill rows: "
          f"{df.loc[needs_backfill, 'date'].min().date()} → {df.loc[needs_backfill, 'date'].max().date()}")

    return df, needs_backfill


def load_progress() -> set:
    """Load previously completed row hashes for resumption."""
    if not PROGRESS_CSV.exists():
        return set()
    prog = pd.read_csv(PROGRESS_CSV)
    return set(prog["row_hash"].tolist())


def save_progress_row(rh: str, result: dict, status: str):
    """Append one row to the progress CSV."""
    write_header = not PROGRESS_CSV.exists()
    with open(PROGRESS_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["row_hash", "status", "confidence", "n_items", "calories", "timestamp"])
        cal = result.get("meal_total", {}).get("calories", 0) if result else 0
        n_items = len(result.get("items", [])) if result else 0
        conf = result.get("confidence", "") if result else ""
        writer.writerow([rh, status, conf, n_items, cal, datetime.now().isoformat()])


def log_error(rh: str, desc: str, error: str):
    """Append error to the error log."""
    with open(ERRORS_LOG, "a") as f:
        f.write(f"[{datetime.now().isoformat()}] {rh} | {desc[:80]}... | {error}\n")


def run_backfill(args):
    """Main backfill execution."""
    df, needs_backfill = load_data(args.date_from, args.date_to)
    backfill_idx = df[needs_backfill].index.tolist()

    if args.dry_run:
        # Estimate tokens: ~250 input + ~400 output per row
        n = len(backfill_idx)
        est_input = n * 350
        est_output = n * 500
        pricing = {
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4o": (2.50, 10.00),
            "claude-sonnet-4-20250514": (3.00, 15.00),
            "claude-3-5-haiku-20241022": (0.80, 4.00),
            "gemini-2.0-flash": (0.075, 0.30),
        }
        print(f"\n{'='*60}")
        print(f"DRY RUN — {n} rows to backfill")
        print(f"Estimated tokens: ~{est_input:,} input + ~{est_output:,} output")
        print(f"\nEstimated cost by model:")
        for model, (inp_rate, out_rate) in pricing.items():
            cost = (est_input * inp_rate + est_output * out_rate) / 1_000_000
            print(f"  {model:35s}  ${cost:.2f}")
        print(f"{'='*60}")
        return

    # Init LLM client
    client = LLMClient(provider=args.provider, model=args.model, api_key=args.api_key)
    print(f"\nUsing: {client.provider} / {client.model}")

    # Load progress for resumption
    completed = load_progress() if args.resume else set()
    if completed:
        print(f"Resuming — {len(completed)} rows already done")

    # Prepare results storage
    results = []
    n_success = 0
    n_error = 0
    n_skipped = 0
    batch_size = args.batch_size
    start_time = time.time()

    for i, idx in enumerate(backfill_idx):
        row = df.iloc[idx]
        rh = row_hash(str(row["date"]), str(row.get("description", "")), str(row.get("food_item", "")))

        # Skip if already done
        if rh in completed:
            n_skipped += 1
            continue

        # Build prompt
        user_prompt = make_user_prompt(
            str(row.get("description", "")),
            str(row.get("meal_type", "")),
            str(row.get("food_item", "")),
        )
        if not user_prompt:
            n_skipped += 1
            continue

        try:
            result = client.estimate_nutrients(user_prompt)
            meal = result.get("meal_total", {})

            # Store result
            result_row = {
                "original_index": idx,
                "row_hash": rh,
                "date": str(row["date"]),
                "confidence": result.get("confidence", "unknown"),
                "n_items_parsed": len(result.get("items", [])),
                "items_json": json.dumps(result.get("items", [])),
                "notes": result.get("notes", ""),
            }
            for nut in NUTRIENTS:
                result_row[nut] = meal.get(nut, 0)
            results.append(result_row)

            save_progress_row(rh, result, "ok")
            completed.add(rh)
            n_success += 1

            # Progress reporting
            if (n_success % 25 == 0) or (i == len(backfill_idx) - 1):
                elapsed = time.time() - start_time
                rate = n_success / max(elapsed, 1) * 60
                cost = client.estimated_cost()
                print(f"  [{i+1}/{len(backfill_idx)}] "
                      f"✓ {n_success} ok, ✗ {n_error} err, ⇢ {n_skipped} skip | "
                      f"{rate:.0f} rows/min | ~${cost:.2f} spent")

        except json.JSONDecodeError as e:
            n_error += 1
            log_error(rh, user_prompt[:80], f"JSON parse error: {e}")
            save_progress_row(rh, None, "json_error")
        except Exception as e:
            n_error += 1
            log_error(rh, user_prompt[:80], str(e))
            save_progress_row(rh, None, "api_error")

            # Rate limit back-off
            if "rate" in str(e).lower() or "429" in str(e):
                print(f"  ⚠ Rate limited — sleeping 30s...")
                time.sleep(30)
            else:
                time.sleep(0.5)  # brief pause on other errors

        # Respect rate limits
        time.sleep(args.delay)

        # Periodic save
        if len(results) > 0 and len(results) % batch_size == 0:
            _save_batch(results)

    # Final save
    if results:
        _save_batch(results)

    elapsed = time.time() - start_time
    cost = client.estimated_cost()
    print(f"\n{'='*60}")
    print(f"BACKFILL COMPLETE")
    print(f"  Processed: {n_success} ok, {n_error} errors, {n_skipped} skipped")
    print(f"  Time:      {elapsed/60:.1f} minutes")
    print(f"  Tokens:    {client.total_input_tokens:,} in + {client.total_output_tokens:,} out")
    print(f"  Cost:      ~${cost:.2f}")
    print(f"  Results:   {OUTPUT_CSV}")
    print(f"{'='*60}")

    # Merge into enriched CSV
    if n_success > 0:
        merge_results(df)


def _save_batch(results: list):
    """Append results to the output CSV."""
    res_df = pd.DataFrame(results)
    write_header = not OUTPUT_CSV.exists()
    res_df.to_csv(OUTPUT_CSV, mode="a", header=write_header, index=False)
    print(f"  💾 Saved batch ({len(results)} rows) → {OUTPUT_CSV.name}")


def merge_results(df: pd.DataFrame):
    """Merge backfilled nutrients into the original CSV → enriched CSV."""
    if not OUTPUT_CSV.exists():
        print("No backfill results to merge.")
        return

    backfill = pd.read_csv(OUTPUT_CSV)
    print(f"\nMerging {len(backfill)} backfilled rows into enriched CSV...")

    # Apply backfilled values
    enriched = df.copy()
    for _, brow in backfill.iterrows():
        idx = int(brow["original_index"])
        if idx >= len(enriched):
            continue
        for nut in NUTRIENTS:
            val = brow.get(nut, 0)
            if pd.notna(val) and float(val) > 0:
                enriched.at[idx, nut] = float(val)

        # Add backfill metadata
        enriched.at[idx, "ai_backfill_confidence"] = brow.get("confidence", "")
        enriched.at[idx, "ai_backfill_n_items"] = brow.get("n_items_parsed", 0)
        enriched.at[idx, "ai_backfill_notes"] = brow.get("notes", "")

    enriched.to_csv(ENRICHED_CSV, index=False)
    print(f"✓ Enriched CSV saved → {ENRICHED_CSV}")
    print(f"  Total rows:      {len(enriched)}")

    # Report coverage improvement
    has_cal = pd.to_numeric(enriched["calories"], errors="coerce") > 0
    print(f"  Rows with calories (before): {(pd.to_numeric(df['calories'], errors='coerce') > 0).sum()}")
    print(f"  Rows with calories (after):  {has_cal.sum()}")
    print(f"  Improvement:                 +{has_cal.sum() - (pd.to_numeric(df['calories'], errors='coerce') > 0).sum()} rows")


# ─────────────────────────────────────────────────────────
# Standalone merge command (if backfill already done)
# ─────────────────────────────────────────────────────────
def merge_only():
    df = pd.read_csv(INPUT_CSV, low_memory=False)
    df["date"] = pd.to_datetime(df["date"])
    merge_results(df)


# ─────────────────────────────────────────────────────────
# Auto-detect provider from environment
# ─────────────────────────────────────────────────────────
def detect_provider() -> str:
    for provider, env_var in [("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY"), ("google", "GOOGLE_API_KEY")]:
        if os.getenv(env_var):
            return provider
    return "openai"  # default


# ─────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Backfill nutrition data using LLM estimation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/backfill_nutrition.py --dry-run
  python scripts/backfill_nutrition.py --provider openai --model gpt-4o-mini
  python scripts/backfill_nutrition.py --provider google --model gemini-2.0-flash
  python scripts/backfill_nutrition.py --resume
  python scripts/backfill_nutrition.py --merge-only
        """,
    )
    parser.add_argument("--provider", choices=["openai", "anthropic", "google"],
                        default=None, help="LLM provider (auto-detected from env vars if omitted)")
    parser.add_argument("--model", default=None, help="Model name (defaults to cheapest per provider)")
    parser.add_argument("--api-key", default=None, help="API key (defaults to env var)")
    parser.add_argument("--dry-run", action="store_true", help="Estimate cost without calling API")
    parser.add_argument("--resume", action="store_true", help="Resume from previous interrupted run")
    parser.add_argument("--merge-only", action="store_true", help="Just merge existing backfill results")
    parser.add_argument("--date-from", default=None, help="Start date filter (YYYY-MM-DD)")
    parser.add_argument("--date-to", default=None, help="End date filter (YYYY-MM-DD)")
    parser.add_argument("--delay", type=float, default=0.2,
                        help="Seconds between API calls (default: 0.2)")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Save to disk every N rows (default: 50)")

    args = parser.parse_args()

    if args.merge_only:
        merge_only()
        return

    if args.provider is None:
        args.provider = detect_provider()
        print(f"Auto-detected provider: {args.provider}")

    run_backfill(args)


if __name__ == "__main__":
    main()
