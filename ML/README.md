# HEBCS — Multi-Pathway Wellness Score Framework

A patient-specific machine learning system that computes a continuous wellness score and clinical risk predictions for an ESRD (End-Stage Renal Disease) patient on home hemodialysis.

Built from 10+ years of real clinical data: dialysis sessions, lab results, nutrition logs, vitals, symptoms, and medications.

---

## Quick Start

```bash
# 1. Activate environment
source .venv-health-ml/bin/activate

# 2. Run a prediction on the latest day
python predict.py --features data/features/health_features.csv --row -1

# 3. What-if scenario
python predict.py --whatif calories=2500 potassium=1800 --json

# 4. Model system info
python predict.py --info
```

## Docker

```bash
docker build -t hebcs .
docker run --rm hebcs --info
docker run --rm -v $(pwd)/data:/app/data hebcs \
  --features data/features/health_features.csv --row -1 --json
```

> **No patient data is baked into the image.** Mount `data/` at runtime via `-v`.

---

## Models

| Model | Type | Metric | Features | Samples |
|-------|------|--------|----------|---------|
| **Holistic Health Score** | GradientBoosting regressor | R² = 0.808 | 284 | 3,584 |
| **Risk Classifiers v1** (×11) | Mixed classifiers | AUC 0.95–1.00 | 284 | 3,584 |
| **Clinical Risk v2** (×11) | Mixed classifiers | AUC 0.89–1.00 | 141 | 1,798 |

All models stored in `models/`. Schema contract in `models/schema.json` (v1.1.0).

### Feature Bridge

The two model sets use different feature spaces (NB04: 284 daily features, NB06: 141 session features). `feature_bridge.py` translates between them automatically:

- 104 direct semantic mappings
- 7 computed features (e.g., BP drop = pre − post)
- 30 median fallbacks for session-only features
- 78.7% total coverage

### Known Issues

- **bloody_bm_target**: Poorly calibrated (10.6% prevalence, 67% predicted positive). Flagged with `calibration_warning` in output. See `schema.json → known_issues`.

---

## Project Structure

```
ML/
├── predict.py               # Unified inference (CLI + importable API)
├── feature_bridge.py        # NB04↔NB06 feature translation
├── drift_monitor.py         # Feature-distribution drift detection
├── config.yaml              # Pipeline configuration
├── requirements.txt         # 169 pinned packages
├── Makefile                 # Automation targets
├── Dockerfile               # Container (no PHI baked in)
├── pytest.ini               # Test config
├── tests/
│   └── test_hebcs.py        # 48 unit tests (7 classes)
├── notebooks/
│   ├── 01_data_ingestion.ipynb
│   ├── 02_data_exploration.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_model_training.ipynb
│   ├── 05_HEBCS_thesis_validation.ipynb
│   ├── 06_clinical_risk_prediction.ipynb
│   └── 07_whatif_simulator.ipynb
├── models/
│   ├── holistic_health_model.joblib
│   ├── risk_*_model.joblib  (×11)
│   ├── schema.json          (v1.1.0)
│   └── clinical_risk/       (11 models + manifest)
└── data/
    ├── raw/                 # Firestore, PDF, Excel sources
    ├── processed/           # Normalized CSVs
    └── features/            # Engineered feature matrices
```

---

## Makefile Targets

```
make predict       # Run prediction on latest day
make whatif        # Example what-if scenario
make test          # Full validation (pytest + NB05 + MATLAB S06)
make test-unit     # Fast unit tests only (48 tests, ~7s)
make drift         # Check feature distributions for drift
make schema        # Regenerate schema.json
make clean         # Remove generated intermediates
```

---

## HEBCS Thesis

The system validates the **HEBCS wellness score** thesis through 5 statistical tests:

| # | Hypothesis | Method | Result |
|---|-----------|--------|--------|
| H1 | Pathway scores predict composite | F-test (R²) | **SUPPORTED** |
| H2 | All pathways contribute | Feature importance | **SUPPORTED** |
| H3 | Composite detects clinical events | AUC ≥ 0.80 | **SUPPORTED** |
| H4 | Cross-validated performance holds | 5-fold CV | **SUPPORTED** |
| H5 | Pathway scores are independent | VIF < 10 | **SUPPORTED** |

**5/5 PASSED** — independently confirmed in both Python (NB05) and MATLAB (S06) with cross-validation correlation r = 1.0000.

---

## MATLAB Parallel Pipeline

An independent MATLAB implementation at `../HEBCSL_MATLAB/`:

| Script | Purpose |
|--------|---------|
| S01 | Data loading |
| S02 | Pathway scoring |
| S03 | Aggregation comparison |
| S04 | Independence analysis |
| S05 | Hypothesis tests |
| S06 | Full validation (5/5 PASSED) |
| S07 | Clinical risk prediction |
| S08 | Simulink/Stateflow what-if simulator |

---

## Monitoring

```bash
# Check a single row for drift
python drift_monitor.py --schema models/schema.json \
  --features data/features/health_features.csv --row -1

# Batch check all rows
python drift_monitor.py --schema models/schema.json \
  --features data/features/health_features.csv --json
```

Checks: out-of-range (vs training min/max), missing values, extreme shifts (> 2× range from median).

---

## Data Sources

| Source | Records | Period |
|--------|---------|--------|
| Firestore API | 2,509 | 2020–2026 |
| PDF lab reports | 853 | 2016–2026 |
| Excel spreadsheets | 8,969 | 2016–2026 |
| Nutrition (raw) | 917 days | 2021–2026 |
| LLM backfill | 1,646 entries | Gap-fill |

---

*Patient: De-identified — ESRD on Home Hemodialysis*
*Last updated: February 19, 2026*
