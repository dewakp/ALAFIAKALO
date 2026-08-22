"""A test name longer than its header label must not lose its value.

Column boundaries come from the header labels, so a NAME wider than the words
"LAB TEST NAME" spills past the midpoint into RESULT. On a real report:

    1715 WEIGHT - PRE DAY 1   57.5 kg Final
                        ^^^ x_mid 165.5, name/value boundary 162.0

The "1" of "DAY 1" landed in the value column and won. The record was stored as
**1.0 kg** and the true **57.5** was discarded, so a clinician saw
"WEIGHT - PRE DAY  1 kg" for a 57 kg dialysis patient — and the pre/post pair
that should differ by ~1 kg both read as 1.

The geometry decides, without a list of known names: a gap inside a name is a
word space (2.0pt here), the gap to the real value is a column gap (29.0pt).
"""

from app.services.docparse.layout import _reclaim_name_overflow


class W:
    """Minimal stand-in for a positioned word."""

    def __init__(self, text, x0, x1):
        self.text, self.x0, self.x1 = text, x0, x1

    @property
    def x_mid(self):
        return (self.x0 + self.x1) / 2

    def __repr__(self):
        return f"W({self.text!r})"


def cell(words):
    return " ".join(w.text for w in words)


def test_the_production_row_is_repaired():
    """Real coordinates from 'April Akpose lab results.pdf'."""
    buckets = {
        "name": [W("WEIGHT", 67.9, 109.7), W("-", 111.8, 115.4),
                 W("PRE", 117.4, 136.7), W("DAY", 138.7, 160.4)],
        "value": [W("1", 162.4, 168.5), W("57.5", 197.5, 218.0)],
    }
    _reclaim_name_overflow(buckets)
    assert cell(buckets["name"]) == "WEIGHT - PRE DAY 1"
    assert cell(buckets["value"]) == "57.5"


def test_a_normal_row_is_left_alone():
    """The overwhelming majority of rows must be untouched."""
    buckets = {
        "name": [W("Hemoglobin", 67.9, 120.0)],
        "value": [W("13.5", 197.5, 218.0)],
    }
    _reclaim_name_overflow(buckets)
    assert cell(buckets["name"]) == "Hemoglobin"
    assert cell(buckets["value"]) == "13.5"


def test_a_multi_token_value_is_not_cannibalised():
    """"< 5.0" is a value in two tokens, not a name overflow.

    Both tokens hug each other, so there is no wide internal gap to split on.
    """
    buckets = {
        "name": [W("CRP", 67.9, 90.0)],
        "value": [W("<", 197.5, 201.0), W("5.0", 203.0, 218.0)],
    }
    _reclaim_name_overflow(buckets)
    assert cell(buckets["value"]) == "< 5.0"
    assert cell(buckets["name"]) == "CRP"


def test_value_is_never_swallowed_entirely():
    """Even under a strange layout the value must survive."""
    buckets = {
        "name": [W("X", 60.0, 62.0)],
        "value": [W("1", 62.5, 66.0)],
    }
    _reclaim_name_overflow(buckets)
    assert cell(buckets["value"]) == "1"


def test_missing_columns_are_safe():
    for buckets in ({"value": [W("1", 1, 2), W("2", 40, 42)]},
                    {"name": [W("Hb", 1, 2)]},
                    {}):
        _reclaim_name_overflow(buckets)   # must not raise
