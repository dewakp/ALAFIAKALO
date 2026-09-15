"""Convert a trained food model for the phones, and prove each copy agrees with it.

Runs in the linux/amd64 conversion image (Dockerfile.export):

  TFLite (Android)  ONNX -> onnx2tf; EXECUTED here with LiteRT and compared.
  Core ML (iOS)     PyTorch -> coremltools; CONVERTED here. Core ML executes
                    only on macOS, so scripts/verify_food_vision_coreml.py runs
                    the comparison there and marks it verified.

Each platform prefers float16 (half the size) and ships it only if it RUNS and
every decision on the reference photos matches the trained model; otherwise
float32. For TFLite that currently means float32: onnx2tf's float16 file is an
all-float16 graph that LiteRT's CPU interpreter refuses to load.
"""

from __future__ import annotations

import platform
import shutil
import tempfile
from collections import defaultdict
from importlib.metadata import version as package_version
from pathlib import Path

import numpy as np

from food_vision import artifacts, parity
from food_vision.dataset import INPUT_SIZE

TFLITE_INPUT_SHAPE = [1, INPUT_SIZE, INPUT_SIZE, 3]


class NotAdoptable(RuntimeError):
    """The model has not been shown to beat its baseline."""


class ParityError(RuntimeError):
    """A conversion makes different decisions from the model that was evaluated."""


def export_mobile(model_dir: Path, *, allow_unproven: bool = False, log=print) -> dict:
    model_dir = Path(model_dir)
    meta = artifacts.read_meta(model_dir)
    evaluation = meta.get("evaluation") or {}
    if not evaluation.get("adoptable") and not allow_unproven:
        reasons = evaluation.get("reasons") or ["no evaluation recorded"]
        raise NotAdoptable(
            "Not converted: this model has not been shown to beat its baseline.\n  "
            + "\n  ".join(reasons)
            + "\nPass --allow-unproven to convert it anyway, e.g. to exercise an app integration."
        )

    reference = np.load(model_dir / artifacts.REFERENCE_NAME)
    outputs = meta["outputs"]
    probs = {o["name"]: reference[f"probs_{o['name']}"] for o in outputs}
    kinds = {o["name"]: o["kind"] for o in outputs}
    threshold = next((o["threshold"] for o in outputs if o["kind"] == "multi"), 0.5)

    exports = meta.setdefault("exports", {})
    exports["converted_unproven"] = not evaluation.get("adoptable")
    try:
        log("TFLite: converting and comparing ...")
        exports["tflite"] = export_tflite(model_dir, reference["images"], probs, kinds, threshold)
        log("Core ML: converting ...")
        exports["coreml"] = export_coreml(model_dir, meta)
    finally:
        artifacts.write_meta(model_dir, meta)

    if exports["tflite"]["precision"] is None:
        raise ParityError(f"no TFLite conversion matches the trained model: {exports['tflite']['parity']}")
    return exports


def _output_index(details: list[dict], head: str) -> int:
    exact = [d["index"] for d in details if d["name"] == head]
    if len(exact) == 1:
        return exact[0]
    loose = [d["index"] for d in details if head in d["name"]]
    if len(loose) == 1:
        return loose[0]
    raise ParityError(
        f"cannot identify the {head!r} output among {[d['name'] for d in details]}; "
        "refusing to guess which output is which"
    )


def _run_tflite(path: Path, images: np.ndarray, probs: dict) -> dict[str, np.ndarray]:
    """Execute a TFLite file on LiteRT's default CPU interpreter — what an app
    gets unless it adds a GPU delegate."""
    from ai_edge_litert.interpreter import Interpreter

    interpreter = Interpreter(model_path=str(path))
    interpreter.allocate_tensors()
    (image_input,) = interpreter.get_input_details()
    if list(image_input["shape"]) != TFLITE_INPUT_SHAPE:
        raise ParityError(f"{path.name} input is {list(image_input['shape'])}, expected {TFLITE_INPUT_SHAPE}")
    details = interpreter.get_output_details()
    index = {name: _output_index(details, name) for name in probs}
    got = defaultdict(list)
    for image in images:
        interpreter.set_tensor(image_input["index"], image[None].astype(np.float32))
        interpreter.invoke()
        for name, i in index.items():
            got[name].append(interpreter.get_tensor(i).copy())
    return {k: np.concatenate(v) for k, v in got.items()}


def export_tflite(model_dir: Path, images: np.ndarray, probs: dict, kinds: dict, threshold: float) -> dict:
    import onnx2tf

    shipped = model_dir / "food_vision.tflite"
    shipped.unlink(missing_ok=True)  # a previous run's file must not survive a failed one
    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as work:
        onnx2tf.convert(
            input_onnx_file_path=str(model_dir / "food_vision.onnx"),
            output_folder_path=work,
            non_verbose=True,
        )
        for precision in ("float16", "float32"):
            path = Path(work) / f"food_vision_{precision}.tflite"
            try:
                got = _run_tflite(path, images, probs)
            except ParityError:
                raise
            except Exception as exc:
                # onnx2tf 2.6.9's float16 file is float16 end to end — input,
                # weights and activations, no DEQUANTIZE — and LiteRT's CPU
                # kernels refuse it ("CONV_2D ... input_type == kTfLiteFloat32 ...
                # was not true"). A candidate the default interpreter cannot run
                # is not a smaller model, it is a crash on load. Record why.
                results[precision] = {
                    "decisions_agree": False,
                    "runs": False,
                    "error": f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
                    "bytes": path.stat().st_size,
                }
                continue
            results[precision] = parity.compare(probs, got, kinds, threshold)
            results[precision].update(runs=True, bytes=path.stat().st_size)
        chosen = next((p for p in ("float16", "float32") if results[p]["decisions_agree"]), None)
        if chosen:
            shutil.copyfile(Path(work) / f"food_vision_{chosen}.tflite", shipped)

    return {
        "file": shipped.name if chosen else None,
        "precision": chosen,
        "input_layout": "NHWC [1,224,224,3]",
        "parity": results,
        "runtime": f"ai-edge-litert {package_version('ai-edge-litert')} ({platform.machine()})",
        "converter": f"onnx2tf {package_version('onnx2tf')}",
    }


def export_coreml(model_dir: Path, meta: dict) -> dict:
    import coremltools as ct
    import torch

    from food_vision.model import FoodNet

    checkpoint = torch.load(model_dir / "model.pt", map_location="cpu", weights_only=True)
    model = FoodNet(checkpoint["head_sizes"], pretrained=False)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    traced = torch.jit.trace(model, torch.zeros(1, 3, INPUT_SIZE, INPUT_SIZE))

    packages = []
    for precision in ("float16", "float32"):
        converted = ct.convert(
            traced,
            inputs=[ct.ImageType(name="image", shape=(1, 3, INPUT_SIZE, INPUT_SIZE), scale=1.0,
                                 color_layout=ct.colorlayout.RGB)],
            outputs=[ct.TensorType(name=name) for name in model.head_names],
            convert_to="mlprogram",
            compute_precision=getattr(ct.precision, precision.upper()),
            # The app's IPHONEOS_DEPLOYMENT_TARGET is 17.0.
            minimum_deployment_target=ct.target.iOS17,
        )
        converted.short_description = f"ALAFIA food classifier {meta['version']}"
        converted.version = meta["version"]
        name = f"food_vision_{precision}.mlpackage"
        if (model_dir / name).exists():
            shutil.rmtree(model_dir / name)
        converted.save(str(model_dir / name))
        packages.append(name)

    return {
        "packages": packages,
        "verified": False,
        "converter": f"coremltools {ct.__version__}",
        "minimum_deployment_target": "iOS 17",
    }
