"""
HEBCS Automated Test Suite
══════════════════════════════════════════════════════════════

Tests model loading, prediction, feature bridge, what-if scenarios,
and schema consistency.

Run:  python -m pytest tests/ -v
      make test-unit
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

# Ensure ML root is on path
ML_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ML_ROOT))

from predict import HEBCSPredictor, PredictionResult, WhatIfResult
from feature_bridge import (
    DIRECT_MAP,
    COMPUTED_MAP,
    NUTR_SCALE,
    NB06_MEDIANS,
    bridge_nb04_to_nb06,
    get_bridge_stats,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def predictor():
    """Load the predictor once for all tests."""
    os.chdir(str(ML_ROOT))
    return HEBCSPredictor.load("models/", "config.yaml")


@pytest.fixture(scope="session")
def features_df():
    """Load the full features CSV."""
    return pd.read_csv(ML_ROOT / "data" / "features" / "health_features.csv")


@pytest.fixture(scope="session")
def schema():
    """Load schema.json."""
    return json.loads((ML_ROOT / "models" / "schema.json").read_text())


@pytest.fixture(scope="session")
def clinical_manifest():
    """Load NB06 manifest."""
    return json.loads(
        (ML_ROOT / "models" / "clinical_risk" / "manifest.json").read_text()
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  1. Model Loading
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelLoading:
    """Verify all model files load and have expected structure."""

    def test_holistic_model_loads(self, predictor):
        assert predictor._holistic is not None
        assert "pipeline" in predictor._holistic
        assert "feature_names" in predictor._holistic
        assert "metrics" in predictor._holistic

    def test_holistic_feature_count(self, predictor):
        assert predictor.n_features == 284

    def test_holistic_r_squared(self, predictor):
        r2 = predictor._holistic["metrics"]["R²"]
        assert r2 > 0.7, f"R² = {r2} is too low"

    def test_risk_v1_count(self, predictor):
        assert len(predictor._risk_models) == 11

    def test_risk_v1_names(self, predictor):
        expected = {
            "anemia", "gi_distress", "hyperkalemia", "hyperparathyroid",
            "hypocalcemia", "hypokalemia", "intradialytic_hypotension",
            "iron_deficiency", "malnutrition", "metabolic_acidosis", "poor_health",
        }
        assert set(predictor._risk_models.keys()) == expected

    def test_risk_v1_all_have_pipeline(self, predictor):
        for name, model in predictor._risk_models.items():
            assert "pipeline" in model, f"risk_v1 '{name}' missing pipeline"

    def test_clinical_risk_v2_count(self, predictor):
        assert len(predictor._clinical_risk_models) == 11

    def test_clinical_manifest_exists(self, predictor):
        assert len(predictor._clinical_manifest) > 0

    def test_baseline_not_all_zeros(self, predictor):
        assert not np.all(predictor._baseline == 0), "Baseline is all zeros"


# ═══════════════════════════════════════════════════════════════════════════════
#  2. Prediction
# ═══════════════════════════════════════════════════════════════════════════════


class TestPrediction:
    """Verify prediction outputs are well-formed and reasonable."""

    def test_predict_from_csv_row(self, predictor, features_df):
        row = features_df.iloc[-1]
        result = predictor.predict(row)
        assert isinstance(result, PredictionResult)

    def test_health_score_in_range(self, predictor, features_df):
        row = features_df.iloc[-1]
        result = predictor.predict(row)
        assert 0 <= result.health_score <= 100, f"Score {result.health_score} out of range"

    def test_risk_flags_all_probabilities(self, predictor, features_df):
        row = features_df.iloc[-1]
        result = predictor.predict(row)
        for name, prob in result.risk_flags.items():
            assert 0 <= prob <= 1, f"Risk '{name}' = {prob} out of [0,1]"

    def test_clinical_risks_populated(self, predictor, features_df):
        row = features_df.iloc[-1]
        result = predictor.predict(row)
        assert len(result.clinical_risks) > 0, "No clinical risks returned"

    def test_predict_from_dict(self, predictor):
        features = {name: 0.0 for name in predictor.feature_names}
        result = predictor.predict(features)
        assert isinstance(result, PredictionResult)

    def test_predict_from_array(self, predictor):
        x = np.zeros(predictor.n_features)
        result = predictor.predict(x)
        assert isinstance(result, PredictionResult)

    def test_to_dict_keys(self, predictor, features_df):
        row = features_df.iloc[-1]
        d = predictor.predict(row).to_dict()
        assert "health_score" in d
        assert "risk_flags" in d
        assert "clinical_risks" in d

    def test_predict_deterministic(self, predictor, features_df):
        row = features_df.iloc[-1]
        r1 = predictor.predict(row)
        r2 = predictor.predict(row)
        assert r1.health_score == pytest.approx(r2.health_score)
        for k in r1.risk_flags:
            assert r1.risk_flags[k] == pytest.approx(r2.risk_flags[k], abs=1e-10)


# ═══════════════════════════════════════════════════════════════════════════════
#  3. What-If Scenarios
# ═══════════════════════════════════════════════════════════════════════════════


class TestWhatIf:
    """Verify what-if simulator produces valid, directional results."""

    def test_whatif_basic(self, predictor):
        result = predictor.whatif(calories=2500)
        assert isinstance(result, WhatIfResult)

    def test_whatif_has_clinical_risks(self, predictor):
        result = predictor.whatif(calories=2500)
        assert len(result.clinical_risks) > 0, "What-if missing clinical_risks"

    def test_whatif_baseline_matches_predict(self, predictor):
        result = predictor.whatif(calories=2500)
        baseline_result = predictor.predict(predictor._baseline)
        assert abs(result.baseline_score - baseline_result.health_score) < 0.01

    def test_whatif_delta_sign(self, predictor):
        result = predictor.whatif(calories=2500)
        assert result.delta == pytest.approx(
            result.scenario_score - result.baseline_score, abs=0.01
        )

    def test_whatif_invalid_input_raises(self, predictor):
        with pytest.raises(ValueError, match="Unknown input"):
            predictor.whatif(nonexistent_variable=999)

    def test_whatif_multiple_inputs(self, predictor):
        result = predictor.whatif(
            calories=2100, potassium=1200, blood_flow=400
        )
        assert isinstance(result, WhatIfResult)

    def test_whatif_sweep(self, predictor):
        df = predictor.whatif_sweep("calories", [1500, 2000, 2500, 3000])
        assert len(df) == 4
        assert set(df.columns) == {"value", "score", "delta"}

    def test_whatif_to_dict(self, predictor):
        d = predictor.whatif(calories=2500).to_dict()
        assert "baseline_score" in d
        assert "scenario_score" in d
        assert "delta" in d
        assert "clinical_risks" in d
        assert "elevated_risks" in d


# ═══════════════════════════════════════════════════════════════════════════════
#  4. Feature Bridge
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeatureBridge:
    """Verify NB04→NB06 feature translation."""

    def test_bridge_coverage_above_75(self, clinical_manifest):
        first = next(iter(clinical_manifest))
        feats = clinical_manifest[first]["features"]
        stats = get_bridge_stats(feats)
        assert stats["coverage_pct"] >= 75.0, f"Coverage {stats['coverage_pct']}% < 75%"

    def test_bridge_returns_all_features(self, clinical_manifest):
        first = next(iter(clinical_manifest))
        nb06_feats = clinical_manifest[first]["features"]
        nb04_dict = {f: 1.0 for f in DIRECT_MAP.values()}
        result = bridge_nb04_to_nb06(nb04_dict, nb06_feats)
        assert len(result) == len(nb06_feats)
        for f in nb06_feats:
            assert f in result, f"Missing NB06 feature: {f}"

    def test_bridge_no_nans(self, clinical_manifest):
        first = next(iter(clinical_manifest))
        nb06_feats = clinical_manifest[first]["features"]
        nb04_dict = {f: 1.0 for f in DIRECT_MAP.values()}
        result = bridge_nb04_to_nb06(nb04_dict, nb06_feats)
        for f, v in result.items():
            assert not np.isnan(v), f"NaN in bridged feature: {f}"

    def test_direct_map_targets_exist(self, predictor):
        """Every NB04 target in DIRECT_MAP should be a valid NB04 feature name."""
        nb04_features = set(predictor.feature_names)
        missing = []
        for nb06_feat, nb04_feat in DIRECT_MAP.items():
            if nb04_feat not in nb04_features:
                missing.append((nb06_feat, nb04_feat))
        # Some may map to risk_* or other derived features — allow those
        real_missing = [(a, b) for a, b in missing if not b.startswith("risk_")]
        assert len(real_missing) == 0, f"DIRECT_MAP targets not in NB04: {real_missing}"

    def test_nutr_scale_positive(self):
        for k, v in NUTR_SCALE.items():
            assert v > 0, f"NUTR_SCALE['{k}'] = {v} must be positive"

    def test_nb06_medians_count(self, clinical_manifest):
        first = next(iter(clinical_manifest))
        nb06_feats = clinical_manifest[first]["features"]
        covered = sum(1 for f in nb06_feats if f in NB06_MEDIANS)
        assert covered >= 130, f"Only {covered}/141 features have medians"

    def test_computed_map_functions_callable(self):
        for name, fn in COMPUTED_MAP.items():
            assert callable(fn), f"COMPUTED_MAP['{name}'] is not callable"
            # Test with empty dict (should use defaults)
            result = fn({})
            assert isinstance(result, (int, float))

    def test_nutr_scale_has_3d_and_prev_variants(self):
        """Verify scale factors propagated to 3d_avg and prev_ variants."""
        for base in ["calories", "protein", "sodium", "potassium"]:
            today = f"nutr_{base}_today"
            avg3d = f"nutr_{base}_3d_avg"
            prev = f"nutr_prev_{base}"
            assert today in NUTR_SCALE, f"Missing {today}"
            assert avg3d in NUTR_SCALE, f"Missing {avg3d}"
            assert prev in NUTR_SCALE, f"Missing {prev}"
            assert NUTR_SCALE[today] == NUTR_SCALE[avg3d]
            assert NUTR_SCALE[today] == NUTR_SCALE[prev]


# ═══════════════════════════════════════════════════════════════════════════════
#  5. Schema Consistency
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchema:
    """Verify schema.json is consistent with actual models."""

    def test_schema_has_whatif_inputs(self, schema):
        assert "whatif_inputs" in schema
        inputs = schema["whatif_inputs"]["inputs"]
        assert len(inputs) == 9

    def test_whatif_inputs_have_feature_mapping(self, schema):
        inputs = schema["whatif_inputs"]["inputs"]
        for name, spec in inputs.items():
            assert "feature" in spec, f"What-if input '{name}' missing feature mapping"

    def test_schema_feature_count(self, schema):
        features = schema.get("features", {}).get("holistic_features", {})
        if "ordered_names" in features:
            assert len(features["ordered_names"]) == 284

    def test_model_files_exist(self):
        models_dir = ML_ROOT / "models"
        assert (models_dir / "holistic_health_model.joblib").exists()
        assert (models_dir / "schema.json").exists()
        risk_files = list(models_dir.glob("risk_*_model.joblib"))
        assert len(risk_files) == 11, f"Found {len(risk_files)} risk models, expected 11"

    def test_clinical_risk_files_exist(self):
        clin_dir = ML_ROOT / "models" / "clinical_risk"
        assert clin_dir.exists()
        assert (clin_dir / "manifest.json").exists()
        joblib_files = list(clin_dir.glob("*.joblib"))
        assert len(joblib_files) == 11, f"Found {len(joblib_files)} clinical risk models"


# ═══════════════════════════════════════════════════════════════════════════════
#  6. Data Integrity
# ═══════════════════════════════════════════════════════════════════════════════


class TestDataIntegrity:
    """Verify feature CSVs are well-formed."""

    def test_health_features_shape(self, features_df):
        rows, cols = features_df.shape
        assert rows >= 3000, f"Only {rows} rows in health_features.csv"
        assert cols >= 280, f"Only {cols} columns"

    def test_health_features_no_duplicate_columns(self, features_df):
        dupes = features_df.columns[features_df.columns.duplicated()].tolist()
        assert len(dupes) == 0, f"Duplicate columns: {dupes}"

    def test_clinical_risk_features_exist(self):
        path = ML_ROOT / "data" / "features" / "clinical_risk_features.csv"
        assert path.exists()
        df = pd.read_csv(path)
        assert df.shape[0] >= 1500, f"Only {df.shape[0]} sessions"
        assert df.shape[1] >= 140, f"Only {df.shape[1]} features"

    def test_config_yaml_exists(self):
        assert (ML_ROOT / "config.yaml").exists()

    def test_requirements_txt_exists(self):
        path = ML_ROOT / "requirements.txt"
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) >= 100, f"Only {len(lines)} packages in requirements.txt"


# ═══════════════════════════════════════════════════════════════════════════════
#  7. Predictor Info
# ═══════════════════════════════════════════════════════════════════════════════


class TestPredictorInfo:
    """Verify the info property returns expected structure."""

    def test_info_has_patient(self, predictor):
        info = predictor.info
        assert "patient" in info

    def test_info_has_holistic(self, predictor):
        info = predictor.info
        assert "holistic_model" in info
        assert info["holistic_model"]["algorithm"] is not None

    def test_info_risk_counts(self, predictor):
        info = predictor.info
        assert len(info["risk_classifiers_v1"]) == 11
        assert len(info["clinical_risk_v2"]) == 11

    def test_info_whatif_inputs(self, predictor):
        info = predictor.info
        assert len(info["whatif_inputs"]) == 9

    def test_feature_importance(self, predictor):
        df = predictor.get_feature_importance(top_n=10)
        assert len(df) == 10
        assert "feature" in df.columns
        assert "importance" in df.columns
        assert df["importance"].iloc[0] >= df["importance"].iloc[-1]
