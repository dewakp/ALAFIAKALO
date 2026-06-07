#!/usr/bin/env python3
"""Extract hyperparameters from all clinical risk models."""
import json, joblib, sys
from pathlib import Path

ML = Path(__file__).resolve().parent.parent
manifest = json.load(open(ML / "models" / "clinical_risk" / "manifest.json"))

for k, v in manifest.items():
    pipe = joblib.load(ML / "models" / "clinical_risk" / v["pipeline_file"])
    steps = [(s[0], type(s[1]).__name__) for s in pipe.steps]
    model = pipe.steps[-1][1]
    params = {}
    for attr in ["n_estimators", "max_depth", "learning_rate", "C", "penalty",
                  "min_samples_split", "min_samples_leaf", "max_features",
                  "subsample", "loss", "criterion"]:
        if hasattr(model, attr):
            val = getattr(model, attr)
            if val is not None:
                params[attr] = val
    auc = v.get("auc")
    auc_str = f"{auc:.4f}" if auc is not None else "N/A"
    print(f"TARGET: {k}")
    print(f"  Algorithm: {v['algorithm']}")
    print(f"  AUC: {auc_str}")
    print(f"  Pipeline: {steps}")
    print(f"  Hyperparams: {params}")
    print()
