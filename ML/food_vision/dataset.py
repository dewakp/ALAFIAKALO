"""Photo folder → validated, split, vocabulary-coded training data.

A photo collection is described by ONE file at its root, ``labels.csv``, one
row per photo::

    file,session,dish,stage,components
    egusi-0412/01.heic,egusi-0412,Egusi soup,raw,melon seeds;spinach;palm oil
    egusi-0412/05.heic,egusi-0412,Egusi soup,plated,melon seeds;spinach;palm oil
    jollof-0415/02.jpg,jollof-0415,Jollof rice,plated,rice;tomato;chicken;fried plantain

``session`` is required. It is one preparation, and every stage of it must land
on the same side of the train/validation split. Split photo by photo and the
validation set holds the very pot the model trained on a few minutes of cooking
earlier — it would report memory as recognition.

``components`` lists what the food in the frame is MADE OF, including what
cooking has hidden. That is the point of photographing the stages: the raw shot
shows melon seeds the plated shot no longer does, and the model learns to name
them from the finished dish.

Nothing here decides what a food is called. The vocabulary is whatever the
labels say — no alias table and no hand-typed class list (CLAUDE.md §3c, §3ad)
— and near-identical spellings are REPORTED, never silently merged.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

try:  # iPhone photos are HEIC; Pillow cannot decode them on its own.
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # the conversion image never decodes photos
    pillow_heif = None

MANIFEST_NAME = "labels.csv"
COMPONENT_SEPARATOR = ";"

# Output order of the exported model — part of the contract every client reads.
HEAD_ORDER = ("dish", "components", "stage")
HEAD_KIND = {"dish": "single", "components": "multi", "stage": "single"}

INPUT_SIZE = 224        # what the model sees, in evaluation and on the phone
TRAIN_CACHE_SIZE = 320  # decoded once; augmentation crops 224 out of it

# Written into food_vision.json. Every client must prepare a photo exactly this
# way, and `to_input` below is the one implementation training evaluates with.
INPUT_CONTRACT = {
    "name": "image",
    "color": "RGB",
    "values": "float32 in 0-255; normalisation is inside the model",
    "size": [INPUT_SIZE, INPUT_SIZE],
    "orientation": "apply EXIF orientation first",
    "resize": "squash the whole photo to 224x224 (no crop), bilinear",
    "layout": {
        "onnx": "NCHW [1,3,224,224]",
        "tflite": "NHWC [1,224,224,3]",
        "coreml": "Image RGB 224x224",
    },
}


class ManifestError(ValueError):
    """The photo folder cannot be trained on. Carries every problem, not the first."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__(
            f"{len(self.problems)} problem(s) with the photo folder:\n  "
            + "\n  ".join(self.problems)
        )


def normalise(name: str) -> str:
    return " ".join(name.split()).lower()


@dataclass(frozen=True)
class Photo:
    line: int
    path: Path
    session: str
    dish: str | None
    stage: str | None
    components: tuple[str, ...]
    sha256: str


@dataclass
class Manifest:
    root: Path
    photos: list[Photo]
    display: dict[str, str]  # normalised key -> the spelling people used most
    warnings: list[str]
    fingerprint: str         # sha256 over labels.csv and every photo's bytes


def read_manifest(root: Path) -> Manifest:
    """Read and validate ``labels.csv``. Raises ManifestError listing every bad row."""
    root = Path(root).resolve()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ManifestError([f"no {MANIFEST_NAME} in {root}"])

    raw = manifest_path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    columns = {(c or "").strip().lower() for c in (reader.fieldnames or [])}
    missing = [c for c in ("file", "session") if c not in columns]
    if missing:
        raise ManifestError([f"{MANIFEST_NAME} header lacks column(s): {', '.join(missing)}"])
    if not columns & {"dish", "stage", "components"}:
        raise ManifestError([f"{MANIFEST_NAME} has no label column (dish, stage or components)"])

    problems: list[str] = []
    spellings: dict[str, Counter] = defaultdict(Counter)
    listed: dict[Path, int] = {}
    uses: dict[str, list[tuple[int, str]]] = defaultdict(list)
    photos: list[Photo] = []

    def label(value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        key = normalise(value)
        spellings[key][" ".join(value.split())] += 1
        return key

    for raw_row in reader:
        row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
        if not any(row.values()):
            continue  # a blank line is not a photo
        line = reader.line_num
        file = row.get("file", "")
        if not file:
            problems.append(f"line {line}: no file")
            continue
        path = (root / file).resolve()
        if root not in path.parents:
            problems.append(f"line {line}: {file!r} is outside the photo folder")
            continue
        if not path.is_file():
            problems.append(f"line {line}: {file!r} does not exist")
            continue
        if path in listed:
            problems.append(f"line {line}: {file!r} is already listed on line {listed[path]}")
            continue
        listed[path] = line
        session = row.get("session", "")
        if not session:
            problems.append(f"line {line}: {file!r} has no session")
            continue

        dish = label(row.get("dish"))
        stage = label(row.get("stage"))
        parts = (label(p) for p in row.get("components", "").split(COMPONENT_SEPARATOR))
        components = tuple(dict.fromkeys(p for p in parts if p))
        if dish is None and stage is None and not components:
            problems.append(f"line {line}: {file!r} has no dish, stage or components — it teaches nothing")
            continue

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        uses[digest].append((line, session))
        photos.append(Photo(line, path, session, dish, stage, components, digest))

    warnings: list[str] = []
    for digest, where in uses.items():
        if len(where) < 2:
            continue
        lines = ", ".join(str(n) for n, _ in where)
        if len({s for _, s in where}) > 1:
            problems.append(
                f"lines {lines}: the same photo appears in different sessions — "
                "it would sit on both sides of the train/validation split"
            )
        else:
            warnings.append(
                f"lines {lines}: the same photo is listed more than once in one session "
                f"and will count {len(where)} times"
            )

    if problems:
        raise ManifestError(problems)
    if not photos:
        raise ManifestError([f"{MANIFEST_NAME} lists no photos"])

    display = {key: counts.most_common(1)[0][0] for key, counts in spellings.items()}
    warnings.extend(_spelling_warnings(photos, display))
    fingerprint = hashlib.sha256(raw + "".join(sorted(uses)).encode()).hexdigest()
    return Manifest(root, photos, display, warnings, fingerprint)


def _values(photos: list[Photo], head: str) -> list[str]:
    if head == "components":
        return [c for p in photos for c in p.components]
    return [getattr(p, head) for p in photos if getattr(p, head)]


def _folded_forms(key: str) -> set[str]:
    base = re.sub(r"[^a-z0-9]", "", key)
    forms = {base}
    if len(base) > 3 and base.endswith("es"):
        forms.add(base[:-2])
    if len(base) > 2 and base.endswith("s"):
        forms.add(base[:-1])
    return forms


def _spelling_warnings(photos: list[Photo], display: dict[str, str]) -> list[str]:
    """Flag labels that look like one food typed two ways. Never merges them:
    'beans' and 'bean' may be a typo, and may not — that is the labeller's call."""
    warnings = []
    for head in HEAD_ORDER:
        counts = Counter(_values(photos, head))
        groups: dict[str, set[str]] = defaultdict(set)
        for key in counts:
            for form in _folded_forms(key):
                groups[form].add(key)
        reported: set[frozenset[str]] = set()
        for members in groups.values():
            group = frozenset(members)
            if len(group) < 2 or group in reported:
                continue
            reported.add(group)
            listed = " / ".join(f"{display[k]!r} ({counts[k]} photos)" for k in sorted(group))
            warnings.append(
                f"{head}: {listed} look like one food spelled differently. They train as "
                f"SEPARATE classes — correct {MANIFEST_NAME} if they are the same."
            )
    return warnings


def split_of(session: str, val_fraction: float, seed: int = 0) -> str:
    """'train' or 'val' for a whole session. Deterministic, and adding sessions
    later never moves an existing one — so a retrain on a grown collection is
    still validated on photos it has never trained on."""
    digest = hashlib.sha256(f"{seed}:{session}".encode()).digest()
    return "val" if int.from_bytes(digest[:8], "big") / 2**64 < val_fraction else "train"


def split_photos(photos: list[Photo], val_fraction: float, seed: int = 0) -> tuple[list[Photo], list[Photo]]:
    train, val = [], []
    for photo in photos:
        (val if split_of(photo.session, val_fraction, seed) == "val" else train).append(photo)
    return train, val


@dataclass
class Head:
    name: str
    kind: str                # "single" (softmax) or "multi" (sigmoid per class)
    classes: list[str]       # normalised keys, sorted — the output index order
    labels: list[str]        # the same classes as people typed them
    train_support: list[int]
    excluded: dict[str, int] = field(default_factory=dict)  # below --min-support: label -> photos
    val_only: list[str] = field(default_factory=list)       # in validation, never in training

    def __post_init__(self):
        self.index_of = {key: i for i, key in enumerate(self.classes)}


def build_heads(
    train: list[Photo], val: list[Photo], display: dict[str, str], min_support: int,
) -> tuple[dict[str, Head], list[str]]:
    """One output per kind of label, over classes with enough TRAINING photos.

    Support is counted in training only: a class seen only in validation cannot
    be learned, and counting it would give it an output that is never trained.
    """
    heads: dict[str, Head] = {}
    notes: list[str] = []
    for name in HEAD_ORDER:
        counts = Counter(_values(train, name))
        kept = sorted(k for k, n in counts.items() if n >= min_support)
        excluded = {display.get(k, k): n for k, n in sorted(counts.items()) if n < min_support}
        val_only = sorted({display.get(k, k) for k in _values(val, name) if k not in counts})
        needed = 1 if HEAD_KIND[name] == "multi" else 2
        if len(kept) < needed:
            if counts:
                notes.append(
                    f"{name}: no output — {len(kept)} class(es) reach {min_support} training "
                    f"photos and this output needs {needed}"
                )
            else:
                notes.append(f"{name}: not labelled in any training photo")
            continue
        heads[name] = Head(
            name, HEAD_KIND[name], kept, [display.get(k, k) for k in kept],
            [counts[k] for k in kept], excluded, val_only,
        )
    return heads, notes


def encode(photo: Photo, heads: dict[str, Head]) -> dict:
    """Training targets for one photo.

    A photo that lists components makes every UNlisted component a negative.
    A photo that lists none says nothing about them, so it is masked out of the
    components loss rather than teaching "there is no rice in this jollof".
    """
    out: dict = {}
    for name, head in heads.items():
        if head.kind == "single":
            key = getattr(photo, name)
            out[name] = head.index_of.get(key, -1) if key else -1
        else:
            vector = np.zeros(len(head.classes), dtype=np.float32)
            for component in photo.components:
                index = head.index_of.get(component)
                if index is not None:
                    vector[index] = 1.0
            out[name] = vector
            out[f"{name}_mask"] = np.float32(1.0 if photo.components else 0.0)
    return out


def load_rgb(path: Path) -> Image.Image:
    """Decode a photo as the apps must: EXIF orientation applied, then RGB.
    A phone photo commonly arrives sideways without this (CLAUDE.md §3aq)."""
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def to_input(image: Image.Image) -> np.ndarray:
    """The input contract: the WHOLE photo squashed to 224x224, bilinear, uint8 RGB.

    Squashed, not centre-cropped. A crop cuts the rim of the plate, which is
    exactly where the side of plantain sits in a composite; squashing distorts
    shape slightly, keeps every item in frame, and the model trains on the same
    distortion it will see on the phone.
    """
    return np.asarray(image.resize((INPUT_SIZE, INPUT_SIZE), Image.BILINEAR), dtype=np.uint8)


def cache_path(cache_dir: Path, photo: Photo, size: int) -> Path:
    return Path(cache_dir) / f"{photo.sha256}_{size}.png"


def _save_png(image: Image.Image, path: Path) -> None:
    partial = path.with_name(path.name + ".partial")
    image.save(partial, format="PNG")
    os.replace(partial, path)  # an interrupted run never leaves a half-written cache entry


def build_cache(photos: list[Photo], cache_dir: Path) -> None:
    """Decode every photo once. A photo that will not decode is refused by line —
    silently training without it is how a collection shrinks unnoticed (§3av)."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    problems = []
    for photo in photos:
        eval_path = cache_path(cache_dir, photo, INPUT_SIZE)
        train_path = cache_path(cache_dir, photo, TRAIN_CACHE_SIZE)
        if eval_path.exists() and train_path.exists():
            continue
        try:
            image = load_rgb(photo.path)
        except Exception as exc:
            problems.append(
                f"line {photo.line}: {photo.path.name} could not be decoded ({type(exc).__name__}: {exc})"
            )
            continue
        _save_png(Image.fromarray(to_input(image)), eval_path)
        _save_png(image.resize((TRAIN_CACHE_SIZE, TRAIN_CACHE_SIZE), Image.BILINEAR), train_path)
    if problems:
        raise ManifestError(problems)
