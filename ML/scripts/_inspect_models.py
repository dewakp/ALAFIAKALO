#!/usr/bin/env python3
"""Inspect all available models for What-If system."""
import joblib, os, json
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

print("=== AVAILABLE FILES ===")
for f in sorted(os.listdir(MODELS_DIR)):
    print(f"  {f}")
print()

# Check joblib models
for f in sorted(os.listdir(MODELS_DIR)):
    if not f.endswith('.joblib'):
        continue
    try:
        m = joblib.load(MODELS_DIR / f)
        print(f"{f}:")
        if isinstance(m, dict):
            for k, v in m.items():
                if k in ('model_name', 'metrics', 'trained_at', 'training_samples', 'target', 'features'):
                    print(f"  {k}: {v}")
                elif hasattr(v, 'feature_names_in_'):
                    feats = list(v.feature_names_in_)
                    print(f"  pipeline features ({len(feats)}): {feats[:10]}...")
                elif hasattr(v, 'n_features_in_'):
                    print(f"  {k}: n_features={v.n_features_in_}")
        elif hasattr(m, 'feature_names_in_'):
            print(f"  features ({len(m.feature_names_in_)}): {list(m.feature_names_in_)[:10]}...")
        print()
    except Exception as e:
        print(f"  ERROR: {e}\n")

# Check JSON models
for f in sorted(os.listdir(MODELS_DIR)):
    if not f.endswith('.json'):
        continue
    try:
        with open(MODELS_DIR / f) as fh:
            d = json.load(fh)
        print(f"{f}: keys={list(d.keys())[:8]}")
        if 'pathways' in d:
            print(f"  pathways: {list(d['pathways'].keys())}")
    except Exception as e:
        print(f"  {f}: ERROR {e}")
