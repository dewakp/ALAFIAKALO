"""Does a converted model make the same decisions as the model that was evaluated?

numpy only: this runs in the training image (ONNX), the conversion image
(TFLite) and on the Mac host (Core ML).

The gate is DECISIONS, not a tolerance on the numbers. A 0.001 shift that
carries a component across the threshold changes what the patient is told; a
0.01 shift that changes no decision does not. The maximum difference is still
recorded, because a large one on unchanged decisions is worth knowing about.
"""

from __future__ import annotations

import numpy as np


def compare(reference: dict[str, np.ndarray], got: dict[str, np.ndarray], kinds: dict[str, str], threshold: float) -> dict:
    heads: dict[str, dict] = {}
    agree = True
    images = 0
    for name, expected in reference.items():
        expected = np.asarray(expected, dtype=np.float64)
        actual = np.asarray(got[name], dtype=np.float64).reshape(expected.shape)
        images = len(expected)
        if kinds[name] == "multi":
            flips = int(((actual >= threshold) != (expected >= threshold)).sum())
        else:
            flips = int((actual.argmax(axis=-1) != expected.argmax(axis=-1)).sum())
        heads[name] = {"max_abs_diff": float(np.abs(actual - expected).max()), "decision_flips": flips}
        agree = agree and flips == 0
    return {"decisions_agree": agree, "images": images, "heads": heads}
