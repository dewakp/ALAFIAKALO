"""nPCR is computed, because the lab never reports it.

nPCR (normalised protein catabolic rate) is the marker of how much protein a
dialysis patient is actually eating, and it carries 40% of HEBCS's `Nutritional`
pathway. On the reference record it is **N/A on all seven dates the lab printed
it** — the row exists, with unit G/KG/D, and no value. So that pathway scored on
albumin and BUN alone, at 60% coverage, and read 100% for a patient whose
protein intake had been falling for months.

It is derivable from urea kinetics, and every input is already in `lab_results`.
Derived values are scored but never counted as measured: `coverage` keeps
meaning "what a lab reported", and each biomarker carries its own `source`.
"""

import pytest

from app.services.urea_kinetics import estimate_npcr


def test_a_normal_patient_derives_a_normal_npcr():
    """KDOQI's protein target on maintenance dialysis is 1.2 g/kg/day."""
    e = estimate_npcr(pre_dialysis_bun=98.0, spktv=1.61)
    assert e is not None
    assert 1.0 <= e.value <= 1.6
    assert e.source == "derived"


def test_the_reference_record_shows_a_falling_intake():
    """The real series, which is why this marker mattered: 1.42 -> 0.86."""
    series = [
        (98.0, 1.61), (78.0, 1.50), (84.0, 1.62),
        (80.0, 1.35), (52.0, 1.44), (70.0, 0.90),
    ]
    values = [estimate_npcr(bun, ktv).value for bun, ktv in series]
    assert all(0.3 < v < 3.0 for v in values), values
    # The last two sit below the KDOQI target — the finding the pathway missed.
    assert values[-1] < 1.0
    assert values[-2] < 1.0
    assert values[0] > 1.2


def test_provenance_travels_with_the_value():
    """A computed marker must never read as a lab result."""
    e = estimate_npcr(70.0, 0.9)
    text = e.describe()
    assert "estimated from" in text
    assert "not measured" in text
    assert "70" in text and "0.90" in text


@pytest.mark.parametrize("bun,ktv", [
    (None, 1.5), (70.0, None), (None, None),
])
def test_a_missing_input_yields_nothing_not_a_guess(bun, ktv):
    assert estimate_npcr(bun, ktv) is None


@pytest.mark.parametrize("bun,ktv", [
    (70.0, 0.0),        # the equation is undefined at Kt/V = 0
    (70.0, -1.0),
    (70.0, 9.9),        # not a real single-pool Kt/V
    (0.0, 1.4),         # not a dialysis patient's pre-dialysis draw
    (900.0, 1.4),
])
def test_out_of_range_inputs_yield_nothing(bun, ktv):
    """A fabricated nutritional marker is worse than a missing one — it would
    be scored as though it had been measured."""
    assert estimate_npcr(bun, ktv) is None


def test_an_implausible_result_is_withheld():
    """The arithmetic can succeed and still not describe a person."""
    # A very low BUN with high clearance drives nPCR under the plausible floor.
    assert estimate_npcr(5.0, 3.0) is None


def test_hebcs_scores_a_derived_npcr_without_calling_it_measured():
    from app.services.hebcs_engine import compute_hebcs

    # 17 is inside every quoted normal range, so this test isolates what
    # it is about — derived provenance — rather than BUN banding.
    measured_only = compute_hebcs({"Albumin": 4.1, "BUN": 17.0})
    with_derived = compute_hebcs(
        {"Albumin": 4.1, "BUN": 17.0},
        derived_values={"nPCR (Protein Catabolic Rate)": 0.863},
    )

    before = measured_only["pathways"]["Nutritional"]
    after = with_derived["pathways"]["Nutritional"]

    # The pathway read 100% on 60% of its evidence; now it reflects the deficit.
    assert before["score"] == 1.0
    assert after["score"] < before["score"]

    # …and `coverage` still means MEASURED, with the estimate reported apart.
    assert after["coverage"] == before["coverage"]
    assert after["coverage_with_derived"] > after["coverage"]
    assert after["derived"] == 1

    npcr = next(b for b in after["biomarkers"] if b["name"].startswith("nPCR"))
    assert npcr["source"] == "derived"
    albumin = next(b for b in after["biomarkers"] if b["name"] == "Albumin")
    assert albumin["source"] == "measured"


# ── Kt/V and URR are CALCULATED, not looked up ────────────────────────────

def test_ktv_reproduces_the_values_this_lab_reported():
    """Validated against every date holding both the inputs and a reported spKt/V.

    A formula transcribed from memory is worth nothing until it reproduces
    numbers somebody else computed independently.
    """
    from app.services.urea_kinetics import single_pool_ktv

    # (pre BUN, post BUN, minutes, UF litres, post weight kg, reported spKt/V)
    cases = [
        (84, 22, 220, 2.5, 51.6, 1.62),
        (80, 24, 177, 1.0, 52.6, 1.35),
        (52, 14, 235, 0.0, 55.5, 1.44),
        (70, 31, 140, 0.9, 56.6, 0.90),
    ]
    for pre, post, minutes, uf, weight, reported in cases:
        got = single_pool_ktv(pre, post, minutes, uf, weight)
        assert got is not None, (pre, post)
        assert abs(got.value - reported) < 0.05, (got.value, reported)


def test_urr_reproduces_the_values_this_lab_reported():
    from app.services.urea_kinetics import urea_reduction_ratio

    for pre, post, reported in [(84, 22, 74), (80, 24, 70), (52, 14, 73), (70, 31, 56)]:
        got = urea_reduction_ratio(pre, post)
        assert got is not None
        assert abs(got.value - reported) < 1.0, (got.value, reported)


def test_negative_ultrafiltration_is_a_real_session():
    """Saline goes BACK into the patient — boluses for intradialytic
    hypotension, and the rinse-back — so net fluid can be negative. It happens
    on 365 of 1775 sessions here (21%), and the 1st percentile of the whole
    distribution is -1426 ml.

    An earlier version rejected it as a data fault and silently dropped those
    sessions from adequacy scoring.
    """
    from app.services.urea_kinetics import single_pool_ktv

    got = single_pool_ktv(56, 17, 235, -1.0, 48.7)
    assert got is not None
    assert 0.5 < got.value < 2.5

    # Returning fluid LOWERS Kt/V: saline returned is clearance not delivered.
    removed = single_pool_ktv(56, 17, 235, 1.0, 48.7)
    assert removed.value > got.value


class _Reading:
    def __init__(self, uf, saline=None):
        self.uf_volume_removed, self.saline_amount = uf, saline


def test_uf_comes_from_the_machine_minus_saline_not_from_weights():
    """`uf_volume_removed` COUNTS DOWN — it is volume still to remove, despite
    the name. 6,423 reading-to-reading transitions decrease against 166 that
    rise. Taking max() of it reads the target rather than the result.
    """
    from app.services.urea_kinetics import net_ultrafiltration_litres

    readings = [_Reading(4.0), _Reading(3.6, "100 ml"), _Reading(3.1, "100 ml"),
                _Reading(2.4, "200 ml"), _Reading(0.7, "100 ml")]
    # removed 4.0 - 0.7 = 3.3 L, saline back 0.5 L -> 2.8 L net
    assert net_ultrafiltration_litres(readings) == pytest.approx(2.8, abs=0.01)


def test_more_saline_back_than_fluid_off_is_a_real_negative_session():
    from app.services.urea_kinetics import net_ultrafiltration_litres

    readings = [_Reading(1.0), _Reading(0.9, "500 ml"), _Reading(0.8, "500 ml")]
    net = net_ultrafiltration_litres(readings)          # 0.2 off, 1.0 back
    assert net is not None and net < 0


@pytest.mark.parametrize("text,expected", [
    ("100 ml", 100.0), ("100 mL", 100.0), ("20 ml", 20.0),
    ("0.5 l", 500.0), ("~", None), ("", None), (None, None),
])
def test_saline_is_free_text_and_is_parsed(text, expected):
    """The record writes "100 ml", "100 mL" and "~". A tilde means "some,
    unspecified" and must not become a zero — absent is not none-given."""
    from app.services.urea_kinetics import parse_saline_ml
    assert parse_saline_ml(text) == expected


def test_a_session_cannot_change_body_mass_by_more_than_a_tenth():
    """This data holds -59,800 ml and +60,900 ml. The bound is the patient's own
    weight rather than a fixed number of litres, and it rejects 9 of 1775."""
    from app.services.urea_kinetics import single_pool_ktv

    assert single_pool_ktv(56, 17, 235, -59.8, 48.7) is None
    assert single_pool_ktv(56, 17, 235, 60.9, 48.7) is None
    # …while an ordinary session on either side of zero is kept.
    assert single_pool_ktv(56, 17, 235, -1.4, 48.7) is not None
    assert single_pool_ktv(56, 17, 235, 2.3, 48.7) is not None


@pytest.mark.parametrize("pre,post", [(70, 70), (70, 90), (70, 0), (None, 20)])
def test_a_post_draw_that_is_not_lower_is_refused(pre, post):
    """Urea must fall across a session; anything else is a mislabelled draw."""
    from app.services.urea_kinetics import urea_reduction_ratio
    assert urea_reduction_ratio(pre, post) is None


def test_computed_figures_carry_their_inputs():
    from app.services.urea_kinetics import single_pool_ktv

    got = single_pool_ktv(84, 22, 220, 2.5, 51.6)
    text = got.describe()
    assert "computed from" in text and "not reported" in text
    assert got.source == "derived"
