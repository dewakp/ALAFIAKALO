"""Validation metrics for the food classifier — every figure beside a baseline.

Two rules from elsewhere in this codebase shape this module:

- PRECISION is reported beside recall. A harness that scores only what was
  found passes a model that names every food in every photo (CLAUDE.md §3ab:
  the corpus harness measured recall, and boilerplate shipped as lab results).
- A model is only ADOPTABLE if it beats the trivial answer on held-out data
  (§3ac: coefficients are adopted only when they beat predict-the-previous-
  value). Here the trivial answers are "always the most common training dish"
  and "every component scored at its base rate". A head with no labelled
  validation photos is unmeasured, and unmeasured is not proven.

numpy only — no scikit-learn in the conversion image, and average precision is
short enough to own (the tests check it against scikit-learn where it exists).
"""

from __future__ import annotations

from collections import Counter

import numpy as np


def average_precision(y_true: np.ndarray, scores: np.ndarray) -> float:
    """Area under the precision-recall step curve, ties treated as one threshold
    (the same definition as sklearn.metrics.average_precision_score)."""
    order = np.argsort(-scores, kind="mergesort")
    ranked_scores = scores[order]
    ranked_truth = np.asarray(y_true, dtype=np.float64)[order]
    last_of_each_score = np.r_[np.flatnonzero(np.diff(ranked_scores)), len(ranked_scores) - 1]
    true_pos = np.cumsum(ranked_truth)[last_of_each_score]
    precision = true_pos / (last_of_each_score + 1)
    recall = true_pos / true_pos[-1]
    return float(np.sum((recall - np.r_[0.0, recall[:-1]]) * precision))


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def single_label(probs: np.ndarray, targets: np.ndarray, labels: list[str], train_support: list[int]) -> dict:
    targets = np.asarray(targets).astype(int)
    labelled = targets >= 0
    result: dict = {"support": int(labelled.sum())}
    if not labelled.any():
        result["untested_classes"] = list(labels)
        return result

    p, truth = probs[labelled], targets[labelled]
    predicted = p.argmax(axis=1)
    majority = int(np.argmax(train_support))
    top1 = float((predicted == truth).mean())
    baseline = float((truth == majority).mean())

    per_class = []
    for i, label in enumerate(labels):
        support = int((truth == i).sum())
        chosen = int((predicted == i).sum())
        hits = int(((predicted == i) & (truth == i)).sum())
        per_class.append({
            "class": label, "support": support, "predicted": chosen,
            "precision": _ratio(hits, chosen), "recall": _ratio(hits, support),
        })
    confusions = Counter((labels[t], labels[q]) for t, q in zip(truth, predicted) if t != q)

    result.update(
        top1=top1,
        top3=(float((np.argsort(-p, axis=1)[:, :3] == truth[:, None]).any(axis=1).mean())
              if len(labels) > 3 else None),
        baseline_top1=baseline,
        baseline=f"always the most common training class ({labels[majority]})",
        beats_baseline=bool(top1 > baseline),
        per_class=per_class,
        confusions=[{"true": t, "predicted": q, "count": n} for (t, q), n in confusions.most_common(10)],
        untested_classes=[c["class"] for c in per_class if c["support"] == 0],
    )
    return result


def multi_label(probs: np.ndarray, targets: np.ndarray, mask: np.ndarray, labels: list[str], threshold: float) -> dict:
    rows = np.asarray(mask) > 0
    result: dict = {"support": int(rows.sum()), "threshold": threshold}
    if not rows.any():
        result["untested_classes"] = list(labels)
        return result

    p, truth = probs[rows], np.asarray(targets)[rows] > 0.5
    decided = p >= threshold
    per_class, aps, base_rates = [], [], []
    for i, label in enumerate(labels):
        positives = int(truth[:, i].sum())
        true_pos = int((decided[:, i] & truth[:, i]).sum())
        false_pos = int((decided[:, i] & ~truth[:, i]).sum())
        # AP needs the class both present and absent; otherwise any ranking is perfect.
        ap = average_precision(truth[:, i], p[:, i]) if 0 < positives < len(truth) else None
        if ap is not None:
            aps.append(ap)
            base_rates.append(positives / len(truth))
        per_class.append({
            "class": label, "support": positives, "average_precision": ap,
            "precision": _ratio(true_pos, true_pos + false_pos), "recall": _ratio(true_pos, positives),
        })

    true_pos = int((decided & truth).sum())
    false_pos = int((decided & ~truth).sum())
    false_neg = int((~decided & truth).sum())
    precision = _ratio(true_pos, true_pos + false_pos)
    recall = _ratio(true_pos, true_pos + false_neg)
    if precision is None or recall is None:
        f1 = None
    else:
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    macro_ap = float(np.mean(aps)) if aps else None
    baseline = float(np.mean(base_rates)) if base_rates else None

    result.update(
        macro_average_precision=macro_ap,
        scored_classes=len(aps),
        baseline_macro_average_precision=baseline,
        baseline="every component scored at its base rate",
        beats_baseline=bool(macro_ap is not None and macro_ap > baseline),
        micro_precision=precision,
        micro_recall=recall,
        micro_f1=f1,
        per_class=per_class,
        untested_classes=[c["class"] for c in per_class if c["support"] == 0],
        always_present=[c["class"] for c in per_class if c["support"] == len(truth)],
    )
    return result


def selection_score(metrics: dict) -> float | None:
    """The number checkpoint selection maximises: mean of each head's headline."""
    scores = [m.get("top1", m.get("macro_average_precision")) for m in metrics.values()]
    scores = [s for s in scores if s is not None]
    return float(np.mean(scores)) if scores else None


def adoptability(metrics: dict) -> tuple[bool, list[str]]:
    reasons = []
    for head, m in metrics.items():
        if not m.get("support"):
            reasons.append(f"{head}: no labelled validation photos — unmeasured is not proven")
        elif "macro_average_precision" in m and m["macro_average_precision"] is None:
            reasons.append(f"{head}: no component is both present and absent in validation, so nothing could be scored")
        elif not m.get("beats_baseline"):
            reasons.append(f"{head}: does not beat the baseline ({m['baseline']})")
    return not reasons, reasons


def headline(metrics: dict) -> str:
    parts = []
    for head, m in metrics.items():
        if "top1" in m:
            parts.append(f"{head} top-1 {m['top1']:.2f} (baseline {m['baseline_top1']:.2f})")
        elif m.get("macro_average_precision") is not None:
            # Say how many classes the mean covers. An mAP over 1 of 3 components
            # is not the head's score, and printed bare it reads as one.
            parts.append(f"{head} mAP {m['macro_average_precision']:.2f} over {m['scored_classes']}/"
                         f"{len(m['per_class'])} classes (baseline {m['baseline_macro_average_precision']:.2f})")
        else:
            parts.append(f"{head} unmeasured")
    return " · ".join(parts)


def _f(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _export_line(name: str, export: dict) -> str:
    if name == "onnx":
        return f"onnx: decisions agree {export.get('decisions_agree')} on {export.get('images')} photos ({export.get('runtime')})"
    if name == "tflite":
        chosen = export.get("parity", {}).get(export.get("precision"), {})
        return (f"tflite: {export.get('precision')}, decisions agree {chosen.get('decisions_agree')} "
                f"on {chosen.get('images')} photos ({export.get('runtime')})")
    if name == "coreml":
        if export.get("verified"):
            return f"coreml: {export.get('precision')}, verified on {export.get('runtime')}"
        return "coreml: converted, NOT yet executed — run scripts/verify_food_vision_coreml.py on macOS"
    return f"{name}: {export}"


def render_report(meta: dict, metrics: dict) -> str:
    dataset = meta["dataset"]
    lines = [f"ALAFIA food classifier {meta['version']}  ({meta['created_at']})", ""]
    add = lines.append
    add(f"Photos: {dataset['photos']} in {dataset['sessions']} sessions — "
        f"training {dataset['train']['photos']} ({dataset['train']['sessions']} sessions), "
        f"validation {dataset['validation']['photos']} ({dataset['validation']['sessions']} sessions)")
    for warning in dataset["warnings"]:
        add(f"  ! {warning}")
    for note in dataset["notes"]:
        add(f"  - {note}")
    for head, excluded in dataset["excluded"].items():
        if excluded:
            add(f"  - {head}: fewer than {dataset['min_support']} training photos, so no output: "
                + ", ".join(f"{k} ({v})" for k, v in excluded.items()))
    for head, names in dataset["validation_only"].items():
        if names:
            add(f"  - {head}: in validation but never in training, so cannot be recognised: {', '.join(names)}")

    evaluation = meta["evaluation"]
    add("")
    add(f"Validation: {'ADOPTABLE' if evaluation['adoptable'] else 'NOT ADOPTABLE'} — {evaluation['headline']}")
    for reason in evaluation["reasons"]:
        add(f"  - {reason}")

    for head, m in metrics.items():
        add("")
        add(f"[{head}]")
        if not m.get("support"):
            add("  no labelled validation photos")
            continue
        if "top1" in m:
            top3 = f"  top-3 {m['top3']:.3f}" if m.get("top3") is not None else ""
            add(f"  top-1 {m['top1']:.3f} vs baseline {m['baseline_top1']:.3f} — {m['baseline']}{top3}")
            for c in m["confusions"][:5]:
                add(f"  confused: {c['true']} -> {c['predicted']} x{c['count']}")
        else:
            add(f"  mAP {_f(m.get('macro_average_precision'))} vs baseline "
                f"{_f(m.get('baseline_macro_average_precision'))} · precision {_f(m['micro_precision'])} "
                f"· recall {_f(m['micro_recall'])} at threshold {m['threshold']}")
        for c in m["per_class"]:
            ap = f"  AP {_f(c['average_precision'])}" if "average_precision" in c else ""
            add(f"  {c['class'][:30]:<30} support {c['support']:>4}  precision {_f(c['precision'])}  "
                f"recall {_f(c['recall'])}{ap}")
        if m.get("untested_classes"):
            add(f"  UNTESTED (no validation photo): {', '.join(m['untested_classes'])}")
        if m.get("always_present"):
            add(f"  NOT SCORED (in every validation photo, so no ranking of it can be wrong): "
                f"{', '.join(m['always_present'])}")

    exports = {k: v for k, v in meta.get("exports", {}).items() if isinstance(v, dict)}
    if exports:
        add("")
        add("Exports:")
        for name, export in exports.items():
            add(f"  {_export_line(name, export)}")
    return "\n".join(lines) + "\n"
