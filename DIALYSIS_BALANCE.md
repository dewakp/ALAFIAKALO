# Dialysis balance — what a treatment does to the day's nutrition

A dialysis session changes a patient's nutrient balance in gram quantities.
Potassium eaten at breakfast can be gone by the afternoon; calcium the patient
never ate crosses in from the dialysate and is retained. Treating a treatment
day and a rest day as nutritionally identical is wrong in both directions.

---

## 0. The rule that governs everything here

> **A treatment changes the day's TOTALS. It never changes the LIMIT.**

KDOQI's 2,000–3,000 mg/day of potassium is already the figure *for a patient on
dialysis* — the clearance is baked into the guideline. Raising the limit on a
treatment day counts the same clearance twice, and a typical session clears
~3,900 mg against a 3,000 mg limit, so the limit would more than double.

The API therefore leaves `goal` untouched and adds `dialysis_balance`:

```
intake   what the food log says was eaten     ← `current`, unchanged
delta    signed: −removed by treatment, +gained from the bath
net      intake + delta — the body's actual balance
```

The intake-versus-limit comparison is preserved because that is the guideline
check. `net` is reported beside it, **never in place of it** — a potassium total
driven near zero by dialysis must not read as licence to eat more.

---

## 1. The model — `app/services/dialysis_balance.py`

Pure: no database, no patient record. Takes session parameters and serum
concentrations, returns masses, so it can be fitted offline and unit-tested
without fixtures.

**Positive mass = removed. Negative = gained**, which is the normal outcome for
calcium against a 3.0 mEq/L bath and is not an error.

Removal is limited by two sides and both are applied:

| side | term |
|---|---|
| dialysate | `volume × (diffusible − bath) × saturation × flow_efficiency` |
| blood | hard ceiling at `blood_volume_processed × concentration × 0.9` |

All four prescription parameters reach the arithmetic:

| parameter | how it is used |
|---|---|
| **dialysate quantity** | `effective_volume_l`; *delivered* beats ordered, so a session cut short is not credited with the full prescription |
| **duration** | derives Qd (`volume/duration`), and drives phosphorus's rebound plateau |
| **blood volume processed** | `Qb × duration`; sets the Qb:Qd efficiency and the blood-side ceiling |
| **dialysate mix** | bath K from the record; Ca/Mg recorded-or-assumed and **declared** when assumed |

### Why saturation, not Kt/V

These sessions run ~30 L against Qb ~350 for ~3 h. Dialysate flow is well below
blood flow, so effluent leaves near equilibrium and removal is bounded by volume
and gradient. Kt/V is the right frame for a high-flux in-centre machine and
would answer a different question here.

### flow_sensitivity — why blood flow is not applied uniformly

Urea is genuinely flow-limited. Potassium, phosphorus and magnesium are not:
their bottleneck is release from the intracellular pool, not the membrane.
Applying a blood-flow term to them made hold-out error **worse** on this
patient's own bloods (potassium 0.340 → 0.344, phosphorus 0.375 → 0.390) while
improving urea by 14%. Hence a per-analyte `flow_sensitivity` (1.0 for urea,
0.25 for the intracellularly-buffered solutes).

### Data-quality guards

- Bath potassium outside 0–4 mEq/L is rejected: 11 sessions record **45**, which
  is the *lactate* value in the potassium column.
- `intradialytic_readings.blood_flow_rate` is banded to 50–600 mL/min; the raw
  column spans 0–4660.
- **`therapy_sessions.blood_flow_rate` is the PRESCRIBED rate — a flat 350 on
  every row.** The delivered rate is the per-session mean of the intradialytic
  readings, which really varies (median 397, SD 61, range ~150–480). Using the
  session column instead makes blood flow a constant and silently removes it
  from the model.

---

## 2. Calibration — `ML/scripts/fit_dialysis_coefficients.py`

Fits each analyte to this patient's own serum, scored on a **chronological**
hold-out against *predict-the-previous-value*. A random split would leak future
information backwards through a time series.

**A coefficient that cannot beat that baseline is not adopted.** The analyte
keeps its literature prior and is marked uncalibrated, which halves the credit
it earns at runtime.

Current result — 5/5 adopted:

| analyte | method | n_fit / n_test | MAE | baseline | improvement |
|---|---|---|---|---|---|
| BUN | direct | 77 / 34 | 4.878 | 31.853 | 84.7% |
| phosphorus | direct | 44 / 19 | 0.382 | 2.753 | 86.1% |
| magnesium | derived-post | 18 / 9 | 0.223 | 0.444 | 49.7% |
| potassium | derived-post | 54 / 24 | 0.341 | 0.554 | 38.4% |
| calcium | direct | 91 / 40 | 0.426 | 0.514 | 17.3% |
| ~~potassium~~ | interdialytic | 26 / 12 | 0.523 | 0.467 | **−12% → rejected** |

**Independent check:** the fitted volume of distribution for BUN is **51.9 L**.
Total body water for this patient is ~45–50 L, and urea distributes in TBW.
Nothing in the fit was told that. Potassium's 154 L and calcium's 136 L are
correspondingly large — correct, because cells buffer potassium and bone buffers
calcium.

### Finding post-dialysis potassium

There is **no "POST" test name for potassium or magnesium** anywhere in the
corpus. Searching by name concludes no post value exists; it does. What
identifies it is *where and when the blood was drawn*:

- the monthly pre-dialysis panel is drawn by the provider (`lab_name = DaVita Labs`);
- the outside lab (Kaiser, via the records spreadsheet) drawn **on a treatment
  day** is taken afterwards.

`_build_post_labs_v2.py` already implements this as rule 4 — it simply never
listed potassium or magnesium in `test_groups`. Only same-day draws are used: a
next-morning potassium has re-equilibrated and would bias the coefficient down.

### `nutrition_backfilled.csv` must be deduped

26,400 rows, **1,600 unique `row_hash`** — appended across ~16 resumed runs.
Read naively it reports 26,600 mg of dietary potassium a day; deduped, 1,796 mg.

---

## 3. Safety — `app/services/dialysis_day_adjustment.py`

Only **removals** are gated. Crediting a removal lowers a total and so looks like
room to eat more; a gain raises it and needs no permission.

A removal is credited only if all of:

1. the session is recorded **completed** — not scheduled, not in progress;
2. the most recent serum is **below** the block threshold (K 5.5 mmol/L, PO₄ 5.5,
   Mg 2.6, Ca 10.5 mg/dL);
3. a draw exists within the staleness window — full credit ≤45 days, tapering to
   zero at 120;
4. uncalibrated analytes get **40%** of the modelled amount.

Gains are applied unconditionally. A guard that only ever relaxes is not a guard.

---

## 4. Verification

```bash
cd WEB
docker compose --profile test run --rm backend-test     # 528
docker compose --profile test run --rm frontend-test    # 76
docker compose --profile test run --rm e2e              # 18
```

Calibration (local — reads the real PHI corpus, deliberately not in CI):

```bash
ML/.venv-health-ml/bin/python ML/scripts/fit_dialysis_coefficients.py --report
docker compose exec -T backend python -m scripts.load_dialysis_coefficients \
    --file /tmp/coeffs.json --email developer@hntsolutions.com --apply
```

Canon §3 — iOS and Android too:
`xcodebuild -scheme ALAFIA` · `./gradlew :app:assembleDebug`

### Observed on a real treatment day (2025-09-15)

30 L / 141 min / Qb 340 measured / bath K 1.0 → 47.9 L blood processed, flow
efficiency 0.94:

```
nutrient        limit   intake   dialysis      net   note
Potassium        3000   1800.0       -0.0   1800.0   last K was 6.0 — removal withheld
Phosphorus        900   1044.0     -300.7    743.3
Calcium          1000    400.0     +360.2    760.2   gain from bath
Protein            82     70.0       -9.0     61.0   (estimated)
limits unchanged: True
```

The potassium gate firing on a real serum of 6.0 mmol/L, and calcium arriving at
760 mg from an intake of 400, are the two behaviours this feature exists for.

## Out of scope

- **Water-soluble vitamins** (folate, B1, B6, C) — real losses, no serum data to
  calibrate against.
- **Population coefficients** — n=1. Every fit is per-patient.
- **Peritoneal dialysis** — different kinetics; `PDSession` is untouched.
- Sodium and acid-base.
