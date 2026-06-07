#!/usr/bin/env python3
"""Get the full 284 feature list from holistic model."""
import joblib
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

m = joblib.load(MODELS_DIR / "holistic_health_model.joblib")
feats = list(m['pipeline'].feature_names_in_)
print(f"Total features: {len(feats)}")

# Group by prefix
groups = {}
for f in feats:
    prefix = f.split('_')[0]
    groups.setdefault(prefix, []).append(f)

for prefix in sorted(groups.keys()):
    print(f"\n{prefix} ({len(groups[prefix])}):")
    for f in groups[prefix][:5]:
        print(f"  {f}")
    if len(groups[prefix]) > 5:
        print(f"  ... +{len(groups[prefix])-5} more")
