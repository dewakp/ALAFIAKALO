"""Execute the Core ML conversions on macOS and compare them with the trained model.

Core ML can be converted on Linux but only EXECUTED on macOS, so this is the one
step of the food-model pipeline that runs on the host rather than in Docker. It
needs only numpy, Pillow and coremltools — the ML virtualenv has all three:

    ML/.venv-health-ml/bin/python ML/scripts/verify_food_vision_coreml.py ML/models/food_vision/<version>

Ships float16 when every decision on the reference photos matches the trained
model, float32 otherwise, as food_vision.mlpackage — and records which, and why,
in food_vision.json.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from food_vision import artifacts, parity  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Core ML conversions on macOS.")
    parser.add_argument("model_dir", type=Path)
    args = parser.parse_args(argv)
    model_dir = args.model_dir

    if platform.system() != "Darwin":
        print("Core ML executes only on macOS; run this on the Mac.", file=sys.stderr)
        return 2
    import coremltools as ct

    meta = artifacts.read_meta(model_dir)
    coreml = meta.get("exports", {}).get("coreml")
    if not coreml:
        print("no Core ML conversion recorded; run scripts/export_food_vision.py first", file=sys.stderr)
        return 2

    reference = np.load(model_dir / artifacts.REFERENCE_NAME)
    outputs = meta["outputs"]
    probs = {o["name"]: reference[f"probs_{o['name']}"] for o in outputs}
    kinds = {o["name"]: o["kind"] for o in outputs}
    threshold = next((o["threshold"] for o in outputs if o["kind"] == "multi"), 0.5)

    results = {}
    for precision in ("float16", "float32"):
        package = model_dir / f"food_vision_{precision}.mlpackage"
        model = ct.models.MLModel(str(package))
        got = defaultdict(list)
        for image in reference["images"]:
            answer = model.predict({"image": Image.fromarray(image)})
            for name in probs:
                got[name].append(np.asarray(answer[name], dtype=np.float64).reshape(1, -1))
        results[precision] = parity.compare(probs, {k: np.concatenate(v) for k, v in got.items()}, kinds, threshold)
        verdict = "agree" if results[precision]["decisions_agree"] else "DISAGREE"
        worst = max(h["max_abs_diff"] for h in results[precision]["heads"].values())
        print(f"Core ML {precision}: decisions {verdict} on {results[precision]['images']} photos (max |diff| {worst:.2e})")

    chosen = next((p for p in ("float16", "float32") if results[p]["decisions_agree"]), None)
    shipped = model_dir / "food_vision.mlpackage"
    if shipped.exists():
        shutil.rmtree(shipped)  # never leave a previous run's package looking verified
    coreml.update(
        verified=chosen is not None,
        precision=chosen,
        file=shipped.name if chosen else None,
        parity=results,
        runtime=f"Core ML via coremltools {ct.__version__}, macOS {platform.mac_ver()[0]} {platform.machine()}",
    )
    if chosen:
        shutil.copytree(model_dir / f"food_vision_{chosen}.mlpackage", shipped)
    artifacts.write_meta(model_dir, meta)

    if chosen is None:
        print("Neither Core ML conversion matches the trained model; nothing shipped.", file=sys.stderr)
        return 4
    print(f"shipped {shipped} ({chosen})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
