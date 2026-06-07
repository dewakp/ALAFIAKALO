"""
HEBCS Predictor — Wellness Score Framework
═════════════════════════════════════════════════════════════

Single-file inference module. Loads trained models once, then predicts
health scores and clinical risk probabilities from raw daily feature vectors.

Usage:
    from predict import HEBCSPredictor

    predictor = HEBCSPredictor.load("models/")
    result = predictor.predict(features_dict)
    # result.health_score   → float  (0–100)
    # result.risk_flags     → dict[str, float]  (11 risk probabilities)
    # result.clinical_risks → dict[str, float]  (12 NB06 risk probabilities)
    # result.whatif(calories=2500, potassium=1800)  → WhatIfResult

CLI:
    python predict.py --features data/features/health_features.csv --row -1
    python predict.py --whatif calories=2500 potassium=1800 blood_flow=400
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd
import yaml

from feature_bridge import bridge_nb04_to_nb06


# ═══════════════════════════════════════════════════════════════════════════════
#  Data classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PredictionResult:
    """Output of a single prediction."""
    health_score: float
    risk_flags: dict[str, float]
    clinical_risks: dict[str, float]
    feature_vector: np.ndarray
    feature_names: list[str]

    def to_dict(self) -> dict:
        return {
            "health_score": round(self.health_score, 2),
            "risk_flags": {k: round(v, 4) for k, v in self.risk_flags.items()},
            "clinical_risks": {k: round(v, 4) for k, v in self.clinical_risks.items()},
        }

    def __repr__(self):
        flags = ", ".join(f"{k}={v:.2f}" for k, v in sorted(self.risk_flags.items()) if v > 0.5)
        return f"PredictionResult(health_score={self.health_score:.1f}, elevated_risks=[{flags}])"


@dataclass
class WhatIfResult:
    """Output of a what-if scenario."""
    scenario_name: str
    baseline_score: float
    scenario_score: float
    delta: float
    inputs: dict[str, float]
    risk_flags: dict[str, float]
    clinical_risks: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "baseline_score": round(self.baseline_score, 2),
            "scenario_score": round(self.scenario_score, 2),
            "delta": round(self.delta, 2),
            "inputs": self.inputs,
            "elevated_risks": {k: round(v, 4) for k, v in self.risk_flags.items() if v > 0.5},
            "clinical_risks": {k: round(v, 4) for k, v in self.clinical_risks.items()},
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  Predictor
# ═══════════════════════════════════════════════════════════════════════════════

class HEBCSPredictor:
    """
    Loads and serves all HEBCS models.

    Models loaded:
        1. holistic_health_model  (GradientBoosting, R²=0.808, 284 features → score)
        2. 11 risk classifiers     (284 features → P(risk))
        3. 12 clinical risk v2     (141 features → P(risk))
    """

    def __init__(
        self,
        holistic_model: dict,
        risk_models: dict[str, dict],
        clinical_risk_models: dict[str, Any],
        clinical_risk_manifest: dict,
        schema: dict,
        config: dict,
    ):
        self._holistic = holistic_model
        self._risk_models = risk_models
        self._clinical_risk_models = clinical_risk_models
        self._clinical_manifest = clinical_risk_manifest
        self._schema = schema
        self._config = config

        # Cache feature names
        self.feature_names: list[str] = holistic_model["feature_names"]
        self.n_features: int = len(self.feature_names)

        # What-if baseline (median of training data)
        pipeline = holistic_model["pipeline"]
        imputer = pipeline.named_steps.get("preprocess", pipeline[0])
        if hasattr(imputer, "named_steps"):
            imp_step = imputer.named_steps.get("impute", imputer[0])
        else:
            imp_step = imputer
        if hasattr(imp_step, "statistics_"):
            self._baseline = imp_step.statistics_.copy()
        else:
            self._baseline = np.zeros(self.n_features)

        # Fix: SimpleImputer medians are 0 for nutrition features because
        # most NB04 rows have no nutrition logged. Override with representative
        # nonzero medians from the 917+ days that DO have nutrition data.
        self._patch_nutrition_baseline()

    # Representative nonzero medians for nutrition features.
    # Computed from the 100+ NB04 rows where nutrition was logged.
    # The raw data has 917+ days of nutrition — these are representative.
    _NUTR_REPRESENTATIVE: dict[str, float] = {
        "nutr_calories":        1213.0,
        "nutr_protein_g":         60.1,
        "nutr_sodium_mg":        737.5,
        "nutr_potassium_mg":    1651.0,
        "nutr_phosphorus_mg":    669.5,
        "nutr_calcium_mg":       268.5,
        "nutr_fat_g":             53.75,
        "nutr_carbs_g":          126.5,
        "nutr_fiber_g":            9.95,
        "nutr_iron_mg":            9.30,
        "nutr_sugar_g":           38.05,
        "nutr_cholesterol":      250.0,
        "nutr_folic_acid":       129.0,
        "nutr_vitamin_b12":        3.20,
        "nutr_vitamin_d":          2.10,
        "nutr_carb_ratio":        0.56,
        "nutr_fat_ratio":         0.20,
        "nutr_protein_ratio":     0.22,
        "nutr_logged_today":      1.0,
        "nutr_meal_count":        2.0,
    }

    def _patch_nutrition_baseline(self):
        """Override zero-valued nutrition baseline with representative medians."""
        patched = 0
        for feat, val in self._NUTR_REPRESENTATIVE.items():
            if feat in self.feature_names:
                idx = self.feature_names.index(feat)
                if self._baseline[idx] == 0 or np.isnan(self._baseline[idx]):
                    self._baseline[idx] = val
                    patched += 1
        # Also patch 7-day rolling averages with same values
        for feat, val in self._NUTR_REPRESENTATIVE.items():
            feat_7d = f"{feat}_7d"
            if feat_7d in self.feature_names:
                idx = self.feature_names.index(feat_7d)
                if self._baseline[idx] == 0 or np.isnan(self._baseline[idx]):
                    self._baseline[idx] = val
                    patched += 1

    # ─── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, models_dir: str = "models/", config_path: str = "config.yaml") -> "HEBCSPredictor":
        """Load all models from disk."""
        models_dir = Path(models_dir)

        # 1. Holistic health model
        holistic = joblib.load(models_dir / "holistic_health_model.joblib")

        # 2. Risk classifiers (NB04)
        risk_models = {}
        for f in sorted(models_dir.glob("risk_*_model.joblib")):
            name = f.stem.replace("risk_", "").replace("_model", "")
            risk_models[name] = joblib.load(f)

        # 3. Clinical risk v2 (NB06)
        clin_dir = models_dir / "clinical_risk"
        clinical_risk_models = {}
        clinical_manifest = {}
        if clin_dir.exists():
            manifest_path = clin_dir / "manifest.json"
            if manifest_path.exists():
                clinical_manifest = json.loads(manifest_path.read_text())
            for f in sorted(clin_dir.glob("*.joblib")):
                name = f.stem.replace("risk_", "")
                clinical_risk_models[name] = joblib.load(f)

        # 4. Schema
        schema_path = models_dir / "schema.json"
        schema = json.loads(schema_path.read_text()) if schema_path.exists() else {}

        # 5. Config
        config_p = Path(config_path)
        config = yaml.safe_load(config_p.read_text()) if config_p.exists() else {}

        print(f"[HEBCS] Loaded: holistic (R²={holistic['metrics']['R²']:.3f}), "
              f"{len(risk_models)} risk v1, {len(clinical_risk_models)} risk v2",
              file=sys.stderr)

        return cls(
            holistic_model=holistic,
            risk_models=risk_models,
            clinical_risk_models=clinical_risk_models,
            clinical_risk_manifest=clinical_manifest,
            schema=schema,
            config=config,
        )

    # ─── Prediction ───────────────────────────────────────────────────────────

    def predict(
        self,
        features: dict[str, float] | pd.Series | np.ndarray,
    ) -> PredictionResult:
        """
        Predict health score and risks from a feature vector.

        Args:
            features: dict mapping feature names → values,
                      or pd.Series indexed by feature names,
                      or np.ndarray of length 284.
        """
        x = self._to_array(features)
        df = pd.DataFrame([x], columns=self.feature_names)

        # Health score
        score = float(self._holistic["pipeline"].predict(df)[0])
        score = max(0.0, min(100.0, score))

        # Risk classifiers v1
        risk_flags = {}
        for name, rm in self._risk_models.items():
            pipe = rm["pipeline"]
            try:
                prob = float(pipe.predict_proba(df)[0, 1])
            except Exception:
                prob = float(pipe.predict(df)[0])
            risk_flags[name] = prob

        # Clinical risk v2
        clin_risks = self._predict_clinical_risks(features)

        return PredictionResult(
            health_score=score,
            risk_flags=risk_flags,
            clinical_risks=clin_risks,
            feature_vector=x,
            feature_names=self.feature_names,
        )

    def _predict_clinical_risks(self, features: dict | pd.Series | np.ndarray) -> dict[str, float]:
        """Run NB06 clinical risk models (141-feature input).

        Uses the feature bridge to translate NB04 (284-feature)
        inputs into NB06 (141-feature) space automatically.
        """
        if not self._clinical_risk_models:
            return {}

        # Get NB06 feature list from manifest
        nb06_features = self._get_nb06_feature_names()
        if not nb06_features:
            return {}

        # Convert input to dict (NB04 space)
        if isinstance(features, np.ndarray):
            nb04_dict = dict(zip(self.feature_names, features))
        elif isinstance(features, pd.Series):
            nb04_dict = features.to_dict()
        elif isinstance(features, dict):
            nb04_dict = features
        else:
            return {}

        # Bridge NB04 → NB06
        nb06_dict = bridge_nb04_to_nb06(nb04_dict, nb06_features)

        x_clin = np.array([nb06_dict[f] for f in nb06_features]).reshape(1, -1)
        df_clin = pd.DataFrame(x_clin, columns=nb06_features)

        # Known calibration issues (see models/schema.json → known_issues)
        _POORLY_CALIBRATED = {"bloody_bm_target"}

        results = {}
        for name, model in self._clinical_risk_models.items():
            try:
                if hasattr(model, "predict_proba"):
                    prob = float(model.predict_proba(df_clin)[0, 1])
                else:
                    prob = float(model.predict(df_clin)[0])
                if name in _POORLY_CALIBRATED:
                    # Flag: model over-predicts (67% positive on 10.6% prevalence)
                    results[name] = prob
                    results[f"{name}_calibration_warning"] = True
                else:
                    results[name] = prob
            except Exception as e:
                results[name] = float("nan")

        return results

    def _get_nb06_feature_names(self) -> list[str]:
        """Get the ordered feature list for NB06 clinical risk models."""
        # Try manifest first (always has the training feature list)
        if self._clinical_manifest:
            first_key = next(iter(self._clinical_manifest))
            feats = self._clinical_manifest[first_key].get("features", [])
            if feats:
                return feats
        # Fallback: schema
        return (
            self._schema
            .get("features", {})
            .get("clinical_risk_features", {})
            .get("ordered_names", [])
        )

    # ─── What-If ──────────────────────────────────────────────────────────────

    def whatif(
        self,
        scenario_name: str = "custom",
        **inputs: float,
    ) -> WhatIfResult:
        """
        Run a what-if scenario.

        Pass any of the 9 what-if inputs as keyword arguments:
            calories, protein, sodium, potassium, phosphorus,
            blood_flow, n_readings, pre_bp_sys, sessions_7d

        Returns baseline vs scenario comparison.
        """
        whatif_map = self._schema.get("whatif_inputs", {}).get("inputs", {})

        # Build baseline vector
        x_base = self._baseline.copy()
        x_scenario = self._baseline.copy()

        for input_name, value in inputs.items():
            if input_name not in whatif_map:
                raise ValueError(
                    f"Unknown input '{input_name}'. "
                    f"Valid: {list(whatif_map.keys())}"
                )
            feat = whatif_map[input_name]["feature"]
            idx = self.feature_names.index(feat)
            x_scenario[idx] = value

        # Predict both
        base_result = self.predict(x_base)
        scen_result = self.predict(x_scenario)

        return WhatIfResult(
            scenario_name=scenario_name,
            baseline_score=base_result.health_score,
            scenario_score=scen_result.health_score,
            delta=scen_result.health_score - base_result.health_score,
            inputs=inputs,
            risk_flags=scen_result.risk_flags,
            clinical_risks=scen_result.clinical_risks,
        )

    def whatif_sweep(
        self,
        input_name: str,
        values: list[float] | np.ndarray,
    ) -> pd.DataFrame:
        """Sweep a single input over a range, returning scores."""
        rows = []
        for v in values:
            r = self.whatif(**{input_name: v})
            rows.append({"value": v, "score": r.scenario_score, "delta": r.delta})
        return pd.DataFrame(rows)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _to_array(self, features) -> np.ndarray:
        if isinstance(features, np.ndarray):
            if features.shape[0] != self.n_features:
                raise ValueError(f"Expected {self.n_features} features, got {features.shape[0]}")
            return features.astype(np.float64)
        if isinstance(features, pd.Series):
            features = features.to_dict()
        if isinstance(features, dict):
            x = np.full(self.n_features, np.nan)
            for k, v in features.items():
                if k in self.feature_names:
                    x[self.feature_names.index(k)] = v
            return x
        raise TypeError(f"Unsupported feature type: {type(features)}")

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """Return top feature importances from the holistic model."""
        pipe = self._holistic["pipeline"]
        model = pipe.named_steps.get("model", pipe[-1])
        if hasattr(model, "feature_importances_"):
            imp = model.feature_importances_
            df = pd.DataFrame({"feature": self.feature_names, "importance": imp})
            return df.sort_values("importance", ascending=False).head(top_n).reset_index(drop=True)
        return pd.DataFrame()

    @property
    def info(self) -> dict:
        """Model system summary."""
        return {
            "patient": self._config.get("patient", {}),
            "holistic_model": {
                "algorithm": self._holistic.get("model_name"),
                "r_squared": self._holistic.get("metrics", {}).get("R²"),
                "n_features": self.n_features,
                "trained_at": self._holistic.get("trained_at"),
                "training_samples": self._holistic.get("training_samples"),
            },
            "risk_classifiers_v1": list(self._risk_models.keys()),
            "clinical_risk_v2": list(self._clinical_risk_models.keys()),
            "whatif_inputs": list(
                self._schema.get("whatif_inputs", {}).get("inputs", {}).keys()
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="HEBCS Predictor — Wellness Score Framework"
    )
    parser.add_argument(
        "--models", default="models/", help="Path to models directory"
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Path to config.yaml"
    )
    parser.add_argument(
        "--features", help="CSV file with feature vectors (one row = one day)"
    )
    parser.add_argument(
        "--row", type=int, default=-1,
        help="Row index to predict (default: last row, i.e. most recent day)"
    )
    parser.add_argument(
        "--whatif", nargs="*",
        help="What-if inputs as key=value pairs, e.g. calories=2500 potassium=1800"
    )
    parser.add_argument(
        "--info", action="store_true", help="Print model system info and exit"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON"
    )

    args = parser.parse_args()

    predictor = HEBCSPredictor.load(args.models, args.config)

    if args.info:
        info = predictor.info
        if args.json:
            print(json.dumps(info, indent=2, default=str))
        else:
            print(f"\n{'═' * 60}")
            print(f"  HEBCS Model System")
            print(f"{'═' * 60}")
            p = info["patient"]
            print(f"  Patient:    {p.get('name', 'N/A')} ({p.get('sex', '')}, Age {p.get('age', '')})")
            print(f"  Diagnosis:  {p.get('diagnosis', '')} — {p.get('modality', '')}")
            h = info["holistic_model"]
            print(f"  Model:      {h['algorithm']} (R²={h['r_squared']:.3f}, {h['n_features']} features)")
            print(f"  Trained:    {h['trained_at']} ({h['training_samples']} samples)")
            print(f"  Risk v1:    {len(info['risk_classifiers_v1'])} classifiers")
            print(f"  Risk v2:    {len(info['clinical_risk_v2'])} classifiers")
            print(f"  What-if:    {info['whatif_inputs']}")
            print(f"{'═' * 60}\n")
        return

    if args.whatif:
        inputs = {}
        for kv in args.whatif:
            k, v = kv.split("=")
            inputs[k.strip()] = float(v.strip())
        result = predictor.whatif(scenario_name="cli", **inputs)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"\n  What-If Scenario: {inputs}")
            print(f"  Baseline: {result.baseline_score:.1f}")
            print(f"  Scenario: {result.scenario_score:.1f}")
            print(f"  Delta:    {result.delta:+.1f}")
            rd = result.to_dict()
            if rd["elevated_risks"]:
                print(f"  Elevated (v1): {rd['elevated_risks']}")
            if rd["clinical_risks"]:
                elevated_v2 = {k: v for k, v in rd["clinical_risks"].items() if v > 0.5}
                if elevated_v2:
                    print(f"  Elevated (v2): {elevated_v2}")
            print()
        return

    if args.features:
        df = pd.read_csv(args.features)
        row = df.iloc[args.row]
        result = predictor.predict(row)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"\n  Health Score: {result.health_score:.1f} / 100")
            elevated = {k: v for k, v in result.risk_flags.items() if v > 0.5}
            if elevated:
                print(f"  Elevated risks (v1): {elevated}")
            else:
                print(f"  No elevated risks v1 (all P < 0.5)")
            if result.clinical_risks:
                elevated_v2 = {k: round(v, 4) for k, v in result.clinical_risks.items() if v > 0.5}
                if elevated_v2:
                    print(f"  Elevated risks (v2): {elevated_v2}")
                else:
                    print(f"  No elevated risks v2 (all P < 0.5)")
            print()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
