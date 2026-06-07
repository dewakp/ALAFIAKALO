# ═══════════════════════════════════════════════════════════════════════════════
#  HEBCS Pipeline Makefile
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Usage:
#    make all          — run full Python + MATLAB pipeline
#    make python       — run all Python notebooks (NB01–NB07)
#    make matlab       — run all MATLAB scripts (S01–S08)
#    make predict      — run inference on latest features
#    make whatif       — run a sample what-if scenario
#    make test         — validate models + cross-platform parity
#    make clean        — remove generated artifacts
#    make env          — create virtual environment + install deps
#
# ═══════════════════════════════════════════════════════════════════════════════

SHELL := /bin/zsh
.DEFAULT_GOAL := help

# ─── Paths ────────────────────────────────────────────────────────────────────
ML_ROOT     := $(shell pwd)
VENV        := $(ML_ROOT)/.venv-health-ml
PYTHON      := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
JUPYTER     := $(VENV)/bin/jupyter
MATLAB      := /Applications/MATLAB_R2025b.app/bin/matlab
MATLAB_ROOT := $(ML_ROOT)/../HEBCSL_MATLAB
NB_DIR      := $(ML_ROOT)/notebooks
MODELS_DIR  := $(ML_ROOT)/models
DATA_DIR    := $(ML_ROOT)/data

# ─── Notebook runner ──────────────────────────────────────────────────────────
# Execute a notebook in place, fail on error
define run_notebook
	@echo "══ Running $(1) ══"
	@$(JUPYTER) nbconvert --to notebook --execute \
		--ExecutePreprocessor.timeout=600 \
		--ExecutePreprocessor.kernel_name=python3 \
		--inplace $(NB_DIR)/$(1)
	@echo "✓ $(1) complete"
endef

# ─── MATLAB runner ────────────────────────────────────────────────────────────
define run_matlab
	@echo "══ Running $(1) ══"
	@cd $(MATLAB_ROOT) && $(MATLAB) -batch "run('$(1)')" 2>&1 | tail -20
	@echo "✓ $(1) complete"
endef

# ═══════════════════════════════════════════════════════════════════════════════
#  Targets
# ═══════════════════════════════════════════════════════════════════════════════

.PHONY: help env python matlab all predict whatif test clean info

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ─── Environment ──────────────────────────────────────────────────────────────

env:  ## Create venv and install dependencies
	@echo "Creating virtual environment..."
	@python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip
	@$(PIP) install -r requirements.txt
	@echo "✓ Environment ready: $(VENV)"

# ─── Python Pipeline ─────────────────────────────────────────────────────────

nb01: ## NB01: Data ingestion
	$(call run_notebook,01_data_ingestion.ipynb)

nb02: nb01  ## NB02: Data exploration
	$(call run_notebook,02_data_exploration.ipynb)

nb03: nb02  ## NB03: Feature engineering
	$(call run_notebook,03_feature_engineering.ipynb)

nb04: nb03  ## NB04: Model training
	$(call run_notebook,04_model_training.ipynb)

nb05: nb04  ## NB05: HEBCS thesis validation
	$(call run_notebook,05_HEBCS_thesis_validation.ipynb)

nb06: nb03  ## NB06: Clinical risk prediction
	$(call run_notebook,06_clinical_risk_prediction.ipynb)

nb07: nb04  ## NB07: What-if simulator
	$(call run_notebook,07_whatif_simulator.ipynb)

python: nb01 nb02 nb03 nb04 nb05 nb06 nb07  ## Run all Python notebooks

# ─── MATLAB Pipeline ─────────────────────────────────────────────────────────

s01:  ## S01: Load data
	$(call run_matlab,S01_load_data.m)

s02: s01  ## S02: Pathway scoring
	$(call run_matlab,S02_pathway_scoring.m)

s03: s02  ## S03: Aggregation comparison
	$(call run_matlab,S03_aggregation_comparison.m)

s04: s03  ## S04: Independence analysis
	$(call run_matlab,S04_independence_analysis.m)

s05: s04  ## S05: Hypothesis tests
	$(call run_matlab,S05_hypothesis_tests.m)

s06: s05  ## S06: Full validation
	$(call run_matlab,S06_full_validation.m)

s07: s06  ## S07: Clinical risk prediction
	$(call run_matlab,S07_clinical_risk_prediction.m)

s08: s07  ## S08: What-if Simulink
	$(call run_matlab,S08_whatif_simulink.m)

matlab: s01 s02 s03 s04 s05 s06 s07 s08  ## Run all MATLAB scripts

# ─── Full Pipeline ────────────────────────────────────────────────────────────

all: python matlab  ## Run complete pipeline (Python + MATLAB)

# ─── Inference ────────────────────────────────────────────────────────────────

predict:  ## Run inference on latest day
	@$(PYTHON) predict.py --features $(DATA_DIR)/features/health_features.csv --row -1

whatif:  ## Sample what-if scenario (optimal ESRD diet)
	@$(PYTHON) predict.py --whatif calories=2100 protein=60 sodium=1500 potassium=1200 phosphorus=600 blood_flow=400

info:  ## Print model system info
	@$(PYTHON) predict.py --info

# ─── Validation ───────────────────────────────────────────────────────────────

test:  ## Validate models + thesis (Python NB05 + MATLAB S06)
	@echo "══ Unit Tests (48 tests) ══"
	$(PYTHON) -m pytest tests/ -v --tb=short
	@echo ""
	@echo "══ Python Thesis Validation ══"
	$(call run_notebook,05_HEBCS_thesis_validation.ipynb)
	@echo ""
	@echo "══ MATLAB Thesis Validation ══"
	$(call run_matlab,S06_full_validation.m)
	@echo ""
	@echo "✓ All validations complete"

test-unit:  ## Run unit tests only (fast)
	$(PYTHON) -m pytest tests/ -v --tb=short

drift:  ## Run drift check on latest feature data
	$(PYTHON) drift_monitor.py --schema models/schema.json \
		--features $(DATA_DIR)/features/health_features.csv --json

# ─── Schema ───────────────────────────────────────────────────────────────────

schema:  ## Regenerate schema.json from current models
	@$(PYTHON) /tmp/build_schema_final.py
	@echo "✓ schema.json updated"

# ─── Cleanup ──────────────────────────────────────────────────────────────────

clean:  ## Remove generated artifacts (keeps raw data + models)
	@echo "Removing generated intermediates..."
	@rm -f $(DATA_DIR)/features/*.png
	@rm -f $(MATLAB_ROOT)/figures/*.png
	@rm -f $(MATLAB_ROOT)/results/*.mat
	@echo "✓ Clean complete (models and raw data preserved)"

distclean: clean  ## Remove everything including models
	@rm -rf $(MODELS_DIR)/*.joblib
	@rm -rf $(MODELS_DIR)/clinical_risk/*.joblib
	@rm -rf $(VENV)
	@echo "✓ Full clean complete"
