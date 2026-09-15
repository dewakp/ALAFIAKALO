"""Convert a trained food model for Android (TFLite) and iOS (Core ML).

    cd WEB
    docker compose --profile ml run --rm food-vision-export \
        python scripts/export_food_vision.py models/food_vision/<version>

Then on the Mac. Core ML executes only on macOS, so this one step cannot run in
a container — the same exception as Xcode (CLAUDE.md §4):

    ML/.venv-health-ml/bin/python ML/scripts/verify_food_vision_coreml.py ML/models/food_vision/<version>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from food_vision import export  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a trained food model for the phones.")
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("--allow-unproven", action="store_true",
                        help="convert a model that has not beaten its baseline (e.g. to test an app integration)")
    args = parser.parse_args(argv)
    try:
        export.export_mobile(args.model_dir, allow_unproven=args.allow_unproven)
    except export.NotAdoptable as exc:
        print(exc, file=sys.stderr)
        return 3
    except export.ParityError as exc:
        print(exc, file=sys.stderr)
        return 4
    print((args.model_dir / "report.txt").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
