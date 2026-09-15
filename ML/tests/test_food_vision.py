"""Phase 5 food classifier: manifest, split, vocabulary, metrics, training, export.

Runs in Docker, in BOTH images — each skips what it lacks, by name:

    cd WEB
    docker compose --profile ml run --rm food-vision          # training image
    docker compose --profile ml run --rm food-vision-export   # TFLite + Core ML

Read the skip list: the conversion test runs only in the export image, and the
scikit-learn cross-check only in the training image.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from food_vision import dataset as ds  # noqa: E402
from food_vision import metrics as fm  # noqa: E402
from food_vision import parity  # noqa: E402

HEADER = ("file", "session", "dish", "stage", "components")


def _write_manifest(root: Path, rows, header=HEADER) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with open(root / ds.MANIFEST_NAME, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def _photo(root: Path, name: str, colour=(10, 20, 30)) -> str:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    # Lossless on purpose, whatever the extension. As JPEG, colours (1,1,1) and
    # (2,1,1) encode to byte-identical files, and the manifest's duplicate-photo
    # guard — correctly — refused them as one photo in two sessions.
    Image.new("RGB", (32, 32), colour).save(path, format="PNG")
    return name


def _p(i, session, dish=None, stage=None, components=()):
    return ds.Photo(i, Path(f"{i}.jpg"), session, dish, stage, tuple(components), f"{i:064x}")


# ── manifest ────────────────────────────────────────────────────────────────

def test_labels_are_normalised_and_shown_as_people_typed_them(tmp_path):
    _write_manifest(tmp_path, [
        [_photo(tmp_path, "a.jpg", (1, 0, 0)), "s1", "Jollof Rice", "plated", "Rice; Chicken ;rice"],
        [_photo(tmp_path, "b.jpg", (2, 0, 0)), "s1", "jollof  rice", "Raw", "rice"],
        [_photo(tmp_path, "c.jpg", (3, 0, 0)), "s2", "Jollof Rice", "", ""],
    ])
    manifest = ds.read_manifest(tmp_path)
    assert [p.dish for p in manifest.photos] == ["jollof rice"] * 3
    assert manifest.photos[0].components == ("rice", "chicken")  # de-duplicated, order kept
    assert manifest.photos[1].stage == "raw"
    assert manifest.photos[2].stage is None and manifest.photos[2].components == ()
    assert manifest.display["jollof rice"] == "Jollof Rice"  # the spelling used most


def test_bad_rows_are_refused_together_and_by_line(tmp_path):
    root = tmp_path / "photos"
    ok = _photo(root, "ok.jpg", (9, 9, 9))
    _photo(tmp_path, "outside.jpg", (6, 6, 6))
    _write_manifest(root, [
        [ok, "s1", "Stew", "", ""],                                   # line 2: fine
        ["missing.jpg", "s1", "Stew", "", ""],                        # 3
        [ok, "s1", "Stew", "", ""],                                   # 4
        [_photo(root, "nosession.jpg", (8, 8, 8)), "", "Stew", "", ""],  # 5
        [_photo(root, "nolabel.jpg", (7, 7, 7)), "s2", "", "", ""],   # 6
        ["../outside.jpg", "s2", "Stew", "", ""],                     # 7
    ])
    with pytest.raises(ds.ManifestError) as refused:
        ds.read_manifest(root)
    problems = "\n".join(refused.value.problems)
    for expected in (
        "line 3: 'missing.jpg' does not exist",
        "line 4: 'ok.jpg' is already listed on line 2",
        "line 5: 'nosession.jpg' has no session",
        "line 6: 'nolabel.jpg' has no dish, stage or components",
        "line 7: '../outside.jpg' is outside the photo folder",
    ):
        assert expected in problems
    assert len(refused.value.problems) == 5  # every problem, not just the first


def test_a_manifest_without_a_session_column_is_refused(tmp_path):
    _write_manifest(tmp_path, [[_photo(tmp_path, "a.jpg"), "Stew"]], header=("file", "dish"))
    with pytest.raises(ds.ManifestError, match="session"):
        ds.read_manifest(tmp_path)


def test_the_same_photo_in_two_sessions_is_refused_because_it_leaks_across_the_split(tmp_path):
    original = _photo(tmp_path, "a.jpg", (5, 5, 5))
    (tmp_path / "copy.jpg").write_bytes((tmp_path / original).read_bytes())

    _write_manifest(tmp_path, [[original, "s1", "Stew", "", ""], ["copy.jpg", "s2", "Stew", "", ""]])
    with pytest.raises(ds.ManifestError, match="different sessions"):
        ds.read_manifest(tmp_path)

    _write_manifest(tmp_path, [[original, "s1", "Stew", "", ""], ["copy.jpg", "s1", "Stew", "", ""]])
    assert any("more than once" in w for w in ds.read_manifest(tmp_path).warnings)


def test_near_identical_spellings_are_reported_not_merged(tmp_path):
    names = ["tomato", "Tomatoes", "fried plantain", "fried-plantain", "rice"]
    _write_manifest(tmp_path, [
        [_photo(tmp_path, f"{i}.jpg", (i, 1, 1)), f"s{i}", "Stew", "", name] for i, name in enumerate(names)
    ])
    manifest = ds.read_manifest(tmp_path)
    warnings = "\n".join(manifest.warnings)
    assert "'tomato'" in warnings and "'Tomatoes'" in warnings
    assert "'fried plantain'" in warnings and "'fried-plantain'" in warnings
    assert "'rice'" not in warnings
    assert {c for p in manifest.photos for c in p.components} == {
        "tomato", "tomatoes", "fried plantain", "fried-plantain", "rice"}


# ── split and vocabulary ────────────────────────────────────────────────────

def test_a_session_is_never_split_and_adding_sessions_moves_none():
    photos = [_p(i, f"session-{i % 40}", dish="stew") for i in range(400)]
    train, val = ds.split_photos(photos, 0.25)
    assert train and val
    assert {p.session for p in train}.isdisjoint({p.session for p in val})

    before = {f"session-{i}": ds.split_of(f"session-{i}", 0.25) for i in range(40)}
    grown = [_p(1000 + i, f"new-{i}", dish="stew") for i in range(60)]
    train2, val2 = ds.split_photos(photos + grown, 0.25)
    after = {p.session: "train" for p in train2} | {p.session: "val" for p in val2}
    assert all(after[s] == side for s, side in before.items())


def test_vocabulary_counts_training_photos_only_and_reports_what_it_left_out():
    train = [_p(i, "t", dish="jollof rice", components=["rice", "chicken"]) for i in range(5)]
    train += [_p(10 + i, "t", dish="egusi soup", components=["spinach"]) for i in range(5)]
    train.append(_p(20, "t", dish="moi moi", components=["beans"]))
    val = [_p(30, "v", dish="suya", components=["onion", "rice"])]
    display = {k: k.title() for k in (
        "jollof rice", "egusi soup", "moi moi", "suya", "rice", "chicken", "spinach", "beans", "onion")}

    heads, notes = ds.build_heads(train, val, display, min_support=3)

    assert heads["dish"].classes == ["egusi soup", "jollof rice"]
    assert heads["dish"].excluded == {"Moi Moi": 1}
    assert heads["dish"].val_only == ["Suya"]
    assert heads["components"].classes == ["chicken", "rice", "spinach"]
    assert heads["components"].excluded == {"Beans": 1}
    assert heads["components"].val_only == ["Onion"]
    assert "stage" not in heads
    assert "stage: not labelled in any training photo" in notes


def test_unlisted_components_are_negatives_but_a_photo_listing_none_is_masked():
    components = ds.Head("components", "multi", ["chicken", "rice"], ["Chicken", "Rice"], [5, 5])
    listed = ds.encode(_p(1, "s", components=["rice", "beans"]), {"components": components})
    assert listed["components"].tolist() == [0.0, 1.0]
    assert listed["components_mask"] == 1.0
    silent = ds.encode(_p(2, "s", dish="jollof rice"), {"components": components})
    assert silent["components_mask"] == 0.0  # says nothing about rice, so teaches nothing about it

    dish = ds.Head("dish", "single", ["egusi soup", "jollof rice"], ["Egusi soup", "Jollof rice"], [3, 3])
    assert ds.encode(_p(3, "s", dish="jollof rice"), {"dish": dish})["dish"] == 1
    assert ds.encode(_p(4, "s", dish="moi moi"), {"dish": dish})["dish"] == -1
    assert ds.encode(_p(5, "s"), {"dish": dish})["dish"] == -1


# ── decoding ────────────────────────────────────────────────────────────────

def test_exif_orientation_is_applied(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6  # stored landscape, displayed rotated 90°
    Image.new("RGB", (40, 20), (255, 0, 0)).save(tmp_path / "sideways.jpg", exif=exif)
    assert ds.load_rgb(tmp_path / "sideways.jpg").size == (20, 40)


def test_heic_photos_decode(tmp_path):
    pytest.importorskip("pillow_heif")
    Image.new("RGB", (40, 20), (0, 128, 255)).save(tmp_path / "phone.heic", format="HEIF")
    image = ds.load_rgb(tmp_path / "phone.heic")
    assert image.size == (40, 20) and image.mode == "RGB"


def test_a_photo_that_will_not_decode_is_refused_by_line_not_skipped(tmp_path):
    good = _photo(tmp_path, "good.jpg", (1, 2, 3))
    (tmp_path / "broken.jpg").write_bytes(b"not a jpeg at all")
    _write_manifest(tmp_path, [[good, "s1", "Stew", "", ""], ["broken.jpg", "s1", "Stew", "", ""]])
    manifest = ds.read_manifest(tmp_path)
    with pytest.raises(ds.ManifestError, match="line 3: broken.jpg could not be decoded"):
        ds.build_cache(manifest.photos, tmp_path / "cache")


def test_the_input_contract_squashes_rather_than_crops():
    image = Image.new("RGB", (400, 100), (0, 0, 0))
    image.paste((255, 255, 255), (390, 0, 400, 100))  # something at the very edge of the plate
    pixels = ds.to_input(image)
    assert pixels.shape == (224, 224, 3) and pixels.dtype == np.uint8
    assert pixels[:, -1].mean() > 200  # still in frame


# ── metrics ─────────────────────────────────────────────────────────────────

def test_average_precision_matches_scikit_learn():
    sk_metrics = pytest.importorskip("sklearn.metrics")
    rng = np.random.default_rng(1)
    checked = 0
    for _ in range(40):
        truth = rng.integers(0, 2, 50)
        scores = np.round(rng.random(50), 1)  # rounding forces ties
        if 0 < truth.sum() < 50:
            assert fm.average_precision(truth.astype(bool), scores) == pytest.approx(
                sk_metrics.average_precision_score(truth, scores))
            checked += 1
    assert checked > 30


def test_naming_every_food_in_every_photo_is_caught_by_precision():
    truth = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0]], dtype=np.float32)
    everything = np.full(truth.shape, 0.9)
    result = fm.multi_label(everything, truth, np.ones(4), ["rice", "chicken", "plantain"], 0.5)
    assert result["micro_recall"] == 1.0
    assert result["micro_precision"] == pytest.approx(4 / 12)
    assert result["beats_baseline"] is False  # a constant score is exactly the base rate


def test_mean_average_precision_says_how_many_classes_it_covers():
    truth = np.array([[1, 1, 0], [1, 1, 1], [1, 1, 0]], dtype=np.float32)  # rice, chicken in every photo
    probs = np.array([[0.9, 0.8, 0.1], [0.9, 0.8, 0.9], [0.9, 0.8, 0.2]])
    result = fm.multi_label(probs, truth, np.ones(3), ["rice", "chicken", "plantain"], 0.5)
    assert result["scored_classes"] == 1
    assert result["always_present"] == ["rice", "chicken"]
    assert "over 1/3 classes" in fm.headline({"components": result})


def test_matching_the_most_common_dish_is_not_beating_it():
    probs = np.array([[0.9, 0.1], [0.8, 0.2], [0.7, 0.3]])
    result = fm.single_label(probs, np.array([0, 0, 1]), ["jollof rice", "egusi soup"], train_support=[10, 2])
    assert result["top1"] == pytest.approx(2 / 3)
    assert result["baseline_top1"] == pytest.approx(2 / 3)
    assert result["beats_baseline"] is False
    assert result["confusions"] == [{"true": "egusi soup", "predicted": "jollof rice", "count": 1}]


def test_a_head_nobody_labelled_in_validation_blocks_adoption():
    metrics = {
        "dish": {"support": 12, "top1": 0.9, "baseline_top1": 0.4, "beats_baseline": True, "baseline": "x"},
        "stage": {"support": 0},
    }
    adoptable, reasons = fm.adoptability(metrics)
    assert adoptable is False
    assert reasons == ["stage: no labelled validation photos — unmeasured is not proven"]


def test_parity_fails_on_a_flipped_decision_however_small_the_difference():
    kinds = {"components": "multi", "dish": "single"}
    reference = {"components": np.array([[0.501, 0.2]]), "dish": np.array([[0.6, 0.4]])}
    flipped = parity.compare(reference, {"components": np.array([[0.499, 0.2]]), "dish": np.array([[0.6, 0.4]])},
                             kinds, threshold=0.5)
    assert flipped["decisions_agree"] is False
    assert flipped["heads"]["components"]["decision_flips"] == 1
    shifted = parity.compare(reference, {"components": np.array([[0.52, 0.25]]), "dish": np.array([[0.55, 0.45]])},
                             kinds, threshold=0.5)
    assert shifted["decisions_agree"] is True


# ── training and conversion (need torch; conversion needs the export image) ──

COLOURS = {"Jollof rice": (200, 60, 30), "Egusi soup": (90, 140, 40)}
RECIPES = (["rice", "chicken"], ["plantain", "rice"], ["chicken", "plantain", "rice"])


def _draw(path: Path, dish: str, components: list[str], stage: str, seed: int) -> None:
    rng = random.Random(seed)
    image = Image.new("RGB", (96, 96), COLOURS[dish])
    pen = ImageDraw.Draw(image)
    fill = (250, 250, 250) if stage == "plated" else None
    for name in components:
        x, y = rng.randint(4, 60), rng.randint(4, 60)
        if name == "rice":
            pen.ellipse([x, y, x + 30, y + 30], fill=fill, outline=(0, 0, 0), width=3)
        elif name == "chicken":
            pen.rectangle([x, y, x + 30, y + 30], fill=fill, outline=(0, 0, 0), width=3)
        else:
            pen.polygon([(x, y + 30), (x + 15, y), (x + 30, y + 30)], fill=fill, outline=(0, 0, 0), width=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=95)


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    pytest.importorskip("torch")
    pytest.importorskip("onnxruntime")
    from food_vision.train import train

    # The split is a hash of the session name; choose names so both sides are
    # populated. This test is about training, not about luck.
    val_sessions, train_sessions, i = [], [], 0
    while len(val_sessions) < 3 or len(train_sessions) < 7:
        name = f"session-{i}"
        i += 1
        if ds.split_of(name, 0.3) == "val":
            if len(val_sessions) < 3:
                val_sessions.append(name)
        elif len(train_sessions) < 7:
            train_sessions.append(name)

    root = tmp_path_factory.mktemp("photos")
    rows = []
    for k, session in enumerate(val_sessions + train_sessions):
        dish = list(COLOURS)[k % 2]
        components = RECIPES[k % 3]
        for s, stage in enumerate(("raw", "plated")):
            for shot in range(2):
                file = f"{session}/{stage}-{shot}.jpg"
                _draw(root / file, dish, components, stage, seed=k * 100 + s * 10 + shot)
                rows.append([file, session, dish, stage, ";".join(components)])
    _write_manifest(root, rows)

    return train(
        root, out_dir=tmp_path_factory.mktemp("models"), cache_dir=tmp_path_factory.mktemp("cache"),
        epochs=2, freeze_epochs=1, batch_size=8, min_support=2, val_fraction=0.3, pretrained=False,
        log=lambda *_: None,
    )


def test_training_writes_a_model_whose_onnx_export_agrees_with_it(trained):
    import onnxruntime as ort

    for name in ("model.pt", "food_vision.onnx", "food_vision.json", "metrics.json", "reference.npz", "report.txt"):
        assert (trained / name).is_file(), name
    assert not list(trained.glob("*.onnx.data"))  # one self-contained file

    meta = json.loads((trained / "food_vision.json").read_text())
    assert [o["name"] for o in meta["outputs"]] == ["dish", "components", "stage"]
    assert meta["outputs"][0]["classes"] == ["Egusi soup", "Jollof rice"]
    assert meta["outputs"][1]["classes"] == ["chicken", "plantain", "rice"]
    assert meta["outputs"][2]["classes"] == ["plated", "raw"]
    assert meta["dataset"]["train"]["sessions"] == 7 and meta["dataset"]["validation"]["sessions"] == 3
    assert isinstance(meta["evaluation"]["adoptable"], bool)
    assert meta["exports"]["onnx"]["decisions_agree"] is True

    reference = np.load(trained / "reference.npz")
    assert reference["images"].dtype == np.uint8
    assert reference["images"].shape[1:] == (224, 224, 3)

    session = ort.InferenceSession(str(trained / "food_vision.onnx"), providers=["CPUExecutionProvider"])
    assert [o.name for o in session.get_outputs()] == ["dish", "components", "stage"]
    assert session.get_inputs()[0].shape == [1, 3, 224, 224]
    assert "Validation:" in (trained / "report.txt").read_text()


def test_an_unproven_model_is_not_converted_without_saying_so(tmp_path):
    from food_vision import export

    (tmp_path / "food_vision.json").write_text(json.dumps(
        {"evaluation": {"adoptable": False, "reasons": ["dish: does not beat the baseline"]}}))
    with pytest.raises(export.NotAdoptable, match="dish: does not beat the baseline"):
        export.export_mobile(tmp_path)


def test_tflite_and_coreml_conversions(trained):
    pytest.importorskip("onnx2tf")
    pytest.importorskip("coremltools")
    from food_vision import export

    exports = export.export_mobile(trained, allow_unproven=True, log=lambda *_: None)

    tflite = exports["tflite"]
    assert tflite["precision"] in ("float16", "float32")
    assert tflite["parity"][tflite["precision"]]["decisions_agree"] is True
    assert (trained / "food_vision.tflite").is_file()
    preference = ["float16", "float32"]
    for passed_over in preference[: preference.index(tflite["precision"])]:
        record = tflite["parity"][passed_over]
        assert record.get("error") or record["decisions_agree"] is False  # never dropped without a reason

    coreml = exports["coreml"]
    assert coreml["verified"] is False  # Linux converts; only macOS can execute
    for package in coreml["packages"]:
        assert (trained / package).is_dir()

    meta = json.loads((trained / "food_vision.json").read_text())
    assert meta["exports"]["converted_unproven"] == (not meta["evaluation"]["adoptable"])
    assert meta["exports"]["tflite"]["precision"] == tflite["precision"]
    assert "tflite:" in (trained / "report.txt").read_text()
