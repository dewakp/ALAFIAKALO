"""A model folder's contract (food_vision.json) and its human report.

torch-free: the Mac writes here too, after verifying Core ML.
"""

from __future__ import annotations

import json
from pathlib import Path

from food_vision import metrics as fm

META_NAME = "food_vision.json"
METRICS_NAME = "metrics.json"
REPORT_NAME = "report.txt"
REFERENCE_NAME = "reference.npz"


def read_meta(model_dir: Path) -> dict:
    return json.loads((Path(model_dir) / META_NAME).read_text())


def write_meta(model_dir: Path, meta: dict) -> None:
    """Write the contract, and regenerate report.txt from it so the two never disagree."""
    model_dir = Path(model_dir)
    (model_dir / META_NAME).write_text(json.dumps(meta, indent=2) + "\n")
    metrics_path = model_dir / METRICS_NAME
    if metrics_path.exists() and "dataset" in meta:
        report = fm.render_report(meta, json.loads(metrics_path.read_text()))
        (model_dir / REPORT_NAME).write_text(report)
