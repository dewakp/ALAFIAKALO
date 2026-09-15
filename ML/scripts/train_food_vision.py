"""Train the ALAFIA Phase 5 food classifier from a folder of labelled photos.

The folder needs a labels.csv — the format is in VISION_TRAINING.md. Runs in
Docker (CLAUDE.md §4); the photos mount read-only from FOOD_PHOTOS:

    cd WEB
    FOOD_PHOTOS=/path/to/photos docker compose --profile ml run --rm food-vision \
        python scripts/train_food_vision.py

Writes ML/models/food_vision/<version>/ with a verified ONNX export and
report.txt. Convert for the phones afterwards with scripts/export_food_vision.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from food_vision.dataset import ManifestError  # noqa: E402
from food_vision.train import train  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the ALAFIA food classifier.")
    parser.add_argument("--photos", type=Path, default=Path("/photos"),
                        help="folder holding labels.csv (default /photos, the compose mount)")
    parser.add_argument("--out", type=Path, default=None, help="default ML/models/food_vision")
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--freeze-epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--min-support", type=int, default=8,
                        help="training photos a class needs before it gets an output")
    parser.add_argument("--val-fraction", type=float, default=0.2,
                        help="share of SESSIONS held out for validation")
    parser.add_argument("--threshold", type=float, default=0.5, help="component probability that counts as present")
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args(argv)

    try:
        out = train(
            args.photos, out_dir=args.out, epochs=args.epochs, freeze_epochs=args.freeze_epochs,
            batch_size=args.batch_size, lr=args.lr, min_support=args.min_support,
            val_fraction=args.val_fraction, threshold=args.threshold, patience=args.patience,
            seed=args.seed, workers=args.workers,
        )
    except ManifestError as exc:
        print(exc, file=sys.stderr)
        return 2
    print()
    print((out / "report.txt").read_text())
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
