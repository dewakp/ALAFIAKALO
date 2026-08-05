"""Correction classification for the Phase 5 training corpus.

`correction_kind` is what makes the corpus queryable — "every photo where the
model named the wrong food" is the set worth retraining on. If this labelling is
wrong the corpus is still just a pile of images.
"""

import pytest

from app.services.food_vision_store import _classify_correction, sha256_of


def _item(name, grams=None):
    return {"name": name, "estimated_grams": grams}


def test_accepted_when_nothing_changed():
    pred = [_item("Jollof rice", 200)]
    assert _classify_correction(pred, [_item("Jollof rice", 200)]) == "accepted"


def test_item_when_only_the_food_changed():
    pred = [_item("Carrots", 150)]
    assert _classify_correction(pred, [_item("Jollof rice", 150)]) == "item"


def test_quantity_when_only_the_amount_changed():
    pred = [_item("Jollof rice", 150)]
    assert _classify_correction(pred, [_item("Jollof rice", 220)]) == "quantity"


def test_wholesale_replacement_is_an_item_correction_not_both():
    """Swapping the only food out is purely an identification failure.

    The grams differ too, but there is no shared food whose amount was
    corrected — calling that a quantity error as well would pollute the
    "portion estimation was wrong" training set with mis-identifications.
    """
    pred = [_item("Carrots", 150)]
    assert _classify_correction(pred, [_item("Jollof rice", 220)]) == "item"


def test_both_requires_a_rename_and_a_shared_item_reweighed():
    pred = [_item("Jollof rice", 200), _item("Carrots", 60)]
    corrected = [_item("Jollof rice", 260), _item("Efo riro", 60)]  # kept but heavier + renamed
    assert _classify_correction(pred, corrected) == "both"


def test_name_comparison_ignores_case_and_order():
    """The user retyping the same foods in a different order is not a correction."""
    pred = [_item("Jollof rice", 200), _item("Efo riro", 150)]
    same = [_item("efo riro", 150), _item("  JOLLOF RICE ", 200)]
    assert _classify_correction(pred, same) == "accepted"


def test_dropping_an_item_is_an_item_correction():
    pred = [_item("Jollof rice", 200), _item("Coleslaw", 60)]
    assert _classify_correction(pred, [_item("Jollof rice", 200)]) == "item"


def test_empty_prediction_with_a_correction_counts_as_item():
    """Model found nothing, user named the meal — a valuable training row."""
    assert _classify_correction([], [_item("Jollof rice", 200)]) == "item"


def test_none_prediction_is_handled():
    assert _classify_correction(None, [_item("Rice", 100)]) == "item"


def test_sha256_is_stable_and_content_addressed():
    assert sha256_of(b"abc") == sha256_of(b"abc")
    assert sha256_of(b"abc") != sha256_of(b"abd")
    assert len(sha256_of(b"abc")) == 64
