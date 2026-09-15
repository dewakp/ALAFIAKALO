"""Train, evaluate and ONNX-export the Phase 5 food classifier.

Entry point: scripts/train_food_vision.py. A run writes one versioned folder,
ML/models/food_vision/<version>/:

  model.pt           weights + head sizes — the source for every conversion
  food_vision.onnx   executed here and compared with the trained model
  food_vision.json   the contract: input, outputs and classes, dataset, the
                     adoption verdict, and what each export proved
  metrics.json       per-class validation metrics, each beside a baseline
  reference.npz      real photos and the trained model's answers, so every
                     later conversion is checked against the same ground truth
  report.txt         all of the above, for a person
"""

from __future__ import annotations

import copy
import json
import math
import platform
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision.transforms import v2

from food_vision import artifacts, parity
from food_vision import dataset as ds
from food_vision import metrics as fm
from food_vision.model import FoodNet

FORMAT = "alafia-food-vision/1"
ML_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ML_ROOT / "models" / "food_vision"
DEFAULT_CACHE = ML_ROOT / "data" / "food_vision_cache"
REFERENCE_PHOTOS = 16


def _read_cached(cache_dir: Path, photo: ds.Photo, size: int) -> Image.Image:
    with Image.open(ds.cache_path(cache_dir, photo, size)) as image:
        return image.convert("RGB")


class PhotoDataset(Dataset):
    def __init__(self, photos: list[ds.Photo], heads: dict[str, ds.Head], cache_dir: Path, *, train: bool):
        self.photos = photos
        self.cache_dir = Path(cache_dir)
        self.train = train
        self.targets = [ds.encode(photo, heads) for photo in photos]
        self.augment = v2.Compose([
            # Crops stay large: a tight crop drops the plantain at the plate's
            # edge while its label still says it is there.
            v2.RandomResizedCrop(ds.INPUT_SIZE, scale=(0.7, 1.0), ratio=(0.85, 1.18), antialias=True),
            v2.RandomHorizontalFlip(),
            # No hue jitter: colour is how raw differs from cooked, and ripe
            # plantain from unripe.
            v2.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
        ])

    def __len__(self) -> int:
        return len(self.photos)

    def __getitem__(self, i: int):
        photo = self.photos[i]
        if self.train:
            image = self.augment(_read_cached(self.cache_dir, photo, ds.TRAIN_CACHE_SIZE))
        else:
            image = _read_cached(self.cache_dir, photo, ds.INPUT_SIZE)
        pixels = torch.from_numpy(np.array(image, dtype=np.uint8)).permute(2, 0, 1).float()
        return pixels, self.targets[i]


def head_losses(logits: dict[str, torch.Tensor], targets: dict[str, torch.Tensor], pos_weight) -> dict[str, torch.Tensor]:
    """Each head learns only from photos labelled for it."""
    parts = {}
    for name, scores in logits.items():
        if ds.HEAD_KIND[name] == "multi":
            rows = targets[f"{name}_mask"] > 0
            if rows.any():
                parts[name] = F.binary_cross_entropy_with_logits(scores[rows], targets[name][rows], pos_weight=pos_weight)
        else:
            rows = targets[name] >= 0
            if rows.any():
                parts[name] = F.cross_entropy(scores[rows], targets[name][rows], label_smoothing=0.1)
    return parts


@torch.no_grad()
def predict(model: FoodNet, loader: DataLoader, device) -> tuple[dict, dict]:
    model.eval()
    probs, targets = defaultdict(list), defaultdict(list)
    for pixels, batch_targets in loader:
        for name, value in zip(model.head_names, model(pixels.to(device))):
            probs[name].append(value.cpu().numpy())
        for key, value in batch_targets.items():
            targets[key].append(np.asarray(value))
    return ({k: np.concatenate(v) for k, v in probs.items()},
            {k: np.concatenate(v) for k, v in targets.items()})


def evaluate(heads: dict[str, ds.Head], probs: dict, targets: dict, threshold: float) -> dict:
    results = {}
    for name, head in heads.items():
        if head.kind == "single":
            results[name] = fm.single_label(probs[name], targets[name], head.labels, head.train_support)
        else:
            results[name] = fm.multi_label(probs[name], targets[name], targets[f"{name}_mask"], head.labels, threshold)
    return results


def _device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def export_onnx(model: FoodNet, out: Path, images: np.ndarray, reference: dict, kinds: dict, threshold: float) -> dict:
    import onnxruntime as ort

    path = out / "food_vision.onnx"
    # dynamo=False: the dynamo exporter writes the weights to a separate
    # food_vision.onnx.data — a two-file artifact every consumer must keep together.
    torch.onnx.export(
        model, (torch.zeros(1, 3, ds.INPUT_SIZE, ds.INPUT_SIZE),), str(path),
        input_names=["image"], output_names=list(model.head_names), opset_version=17, dynamo=False,
    )
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    got = defaultdict(list)
    for image in images:
        outputs = session.run(list(model.head_names), {"image": image.transpose(2, 0, 1)[None].astype(np.float32)})
        for name, value in zip(model.head_names, outputs):
            got[name].append(value)
    result = parity.compare(reference, {k: np.concatenate(v) for k, v in got.items()}, kinds, threshold)
    result.update(file=path.name, bytes=path.stat().st_size,
                  runtime=f"onnxruntime {ort.__version__} ({platform.machine()})")
    return result


def train(
    photos_dir: Path,
    *,
    out_dir: Path | None = None,
    cache_dir: Path | None = None,
    epochs: int = 25,
    freeze_epochs: int = 3,
    batch_size: int = 32,
    lr: float = 1e-3,
    min_support: int = 8,
    val_fraction: float = 0.2,
    threshold: float = 0.5,
    patience: int = 6,
    seed: int = 0,
    workers: int = 0,
    pretrained: bool = True,
    log=print,
) -> Path:
    started = time.time()
    manifest = ds.read_manifest(photos_dir)
    sessions = {p.session for p in manifest.photos}
    train_photos, val_photos = ds.split_photos(manifest.photos, val_fraction, seed)
    if not train_photos or not val_photos:
        raise ds.ManifestError([
            f"{len(sessions)} session(s) split into {len(train_photos)} training and {len(val_photos)} "
            f"validation photos at --val-fraction {val_fraction}; both sides need photos, so add sessions"
        ])
    heads, notes = ds.build_heads(train_photos, val_photos, manifest.display, min_support)
    if not heads:
        raise ds.ManifestError([f"nothing to learn at --min-support {min_support}"] + notes)
    for warning in manifest.warnings:
        log(f"! {warning}")
    for note in notes:
        log(f"- {note}")

    cache_dir = Path(cache_dir or DEFAULT_CACHE)
    log(f"decoding {len(manifest.photos)} photos (cache: {cache_dir}) ...")
    ds.build_cache(manifest.photos, cache_dir)

    torch.manual_seed(seed)
    device = _device()
    model = FoodNet({name: len(head.classes) for name, head in heads.items()}, pretrained=pretrained).to(device)
    train_set = PhotoDataset(train_photos, heads, cache_dir, train=True)
    val_set = PhotoDataset(val_photos, heads, cache_dir, train=False)
    train_loader = DataLoader(train_set, batch_size=batch_size, shuffle=True, num_workers=workers,
                              generator=torch.Generator().manual_seed(seed))
    val_loader = DataLoader(val_set, batch_size=batch_size, shuffle=False, num_workers=workers)

    pos_weight = None
    if "components" in heads:
        labelled = np.array([t["components"] for t in train_set.targets if t["components_mask"] > 0])
        positives = labelled.sum(axis=0)
        # Without this a component in 3 photos of 300 is learned as "never there".
        pos_weight = torch.tensor(np.clip((len(labelled) - positives) / np.maximum(positives, 1), 1.0, 10.0),
                                  dtype=torch.float32, device=device)

    trunk = list(model.features.parameters())
    rest = [p for n, p in model.named_parameters() if not n.startswith("features.")]
    optimizer = torch.optim.AdamW([{"params": trunk, "lr": lr * 0.3}, {"params": rest, "lr": lr}], weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda e: 0.5 * (1 + math.cos(math.pi * min(e, epochs) / epochs)))

    best_score, best_epoch, best_state = None, 0, None
    history = []
    log(f"training on {device}: {len(train_photos)} photos, validating on {len(val_photos)}")
    for epoch in range(1, epochs + 1):
        frozen = epoch <= freeze_epochs
        model.set_trunk_trainable(not frozen)
        model.train()
        if frozen:
            model.features.eval()  # keep ImageNet batch statistics while the heads warm up
        running, batches = 0.0, 0
        for pixels, targets in train_loader:
            pixels = pixels.to(device)
            targets = {k: v.to(device) for k, v in targets.items()}
            parts = head_losses(model.logits(pixels), targets, pos_weight)
            if not parts:
                continue
            loss = sum(parts.values())
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            running += float(loss.item())
            batches += 1
        scheduler.step()

        scores = evaluate(heads, *predict(model, val_loader, device), threshold)
        score = fm.selection_score(scores)
        mean_loss = running / max(batches, 1)
        history.append({"epoch": epoch, "loss": mean_loss, "score": score, "trunk_frozen": frozen})
        log(f"epoch {epoch:>3}/{epochs}  loss {mean_loss:.4f}  {fm.headline(scores)}"
            + ("  [trunk frozen]" if frozen else ""))
        if score is not None and (best_score is None or score > best_score + 1e-4):
            best_score, best_epoch, best_state = score, epoch, copy.deepcopy(model.state_dict())
        elif not frozen and epoch - max(best_epoch, freeze_epochs) >= patience:
            log(f"no validation improvement in {patience} epochs; stopping")
            break

    if best_state is None:  # nothing in validation could be scored — keep the last weights
        best_epoch, best_state = history[-1]["epoch"], copy.deepcopy(model.state_dict())
    model.load_state_dict(best_state)
    final = evaluate(heads, *predict(model, val_loader, device), threshold)
    adoptable, reasons = fm.adoptability(final)

    version = "fv-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = Path(out_dir or DEFAULT_OUT) / version
    out.mkdir(parents=True)
    model = model.to("cpu").eval()
    torch.save({"format": FORMAT, "head_sizes": model.head_sizes, "state_dict": model.state_dict()}, out / "model.pt")

    reference_photos = (val_photos + train_photos)[:REFERENCE_PHOTOS]
    images = np.stack([np.array(_read_cached(cache_dir, p, ds.INPUT_SIZE), dtype=np.uint8) for p in reference_photos])
    with torch.no_grad():
        answers = [model(torch.from_numpy(image).permute(2, 0, 1).float().unsqueeze(0)) for image in images]
    reference = {name: np.concatenate([a[i].numpy() for a in answers]) for i, name in enumerate(model.head_names)}
    np.savez(out / artifacts.REFERENCE_NAME, images=images, **{f"probs_{k}": v for k, v in reference.items()})

    meta = {
        "format": FORMAT,
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": {
            "architecture": "MobileNetV3-Small, " + ("ImageNet-pretrained trunk" if pretrained else "untrained trunk"),
            "outputs": list(model.head_names),
        },
        "input": ds.INPUT_CONTRACT,
        "outputs": [
            {
                "name": name,
                "kind": head.kind,
                "activation": "sigmoid" if head.kind == "multi" else "softmax",
                **({"threshold": threshold} if head.kind == "multi" else {}),
                "classes": head.labels,
                "keys": head.classes,
            }
            for name, head in heads.items()
        ],
        "dataset": {
            "photos": len(manifest.photos),
            "sessions": len(sessions),
            "train": {"photos": len(train_photos), "sessions": len({p.session for p in train_photos})},
            "validation": {"photos": len(val_photos), "sessions": len({p.session for p in val_photos})},
            "fingerprint": manifest.fingerprint,
            "min_support": min_support,
            "val_fraction": val_fraction,
            "seed": seed,
            "excluded": {name: head.excluded for name, head in heads.items()},
            "validation_only": {name: head.val_only for name, head in heads.items()},
            "notes": notes,
            "warnings": manifest.warnings,
        },
        "training": {
            "epochs_requested": epochs,
            "epochs_run": len(history),
            "best_epoch": best_epoch,
            "freeze_epochs": freeze_epochs,
            "batch_size": batch_size,
            "lr": lr,
            "device": str(device),
            "torch": torch.__version__,
            "seconds": None,
            "history": history,
        },
        "evaluation": {
            "adoptable": adoptable,
            "reasons": reasons,
            "headline": fm.headline(final),
            "details": artifacts.METRICS_NAME,
        },
        "exports": {},
    }
    (out / artifacts.METRICS_NAME).write_text(json.dumps(final, indent=2) + "\n")
    kinds = {name: head.kind for name, head in heads.items()}
    try:
        meta["exports"]["onnx"] = export_onnx(model, out, images, reference, kinds, threshold)
    finally:
        meta["training"]["seconds"] = round(time.time() - started, 1)
        artifacts.write_meta(out, meta)
    if not meta["exports"]["onnx"]["decisions_agree"]:
        raise RuntimeError(f"the ONNX export disagrees with the trained model: {meta['exports']['onnx']}")
    return out
