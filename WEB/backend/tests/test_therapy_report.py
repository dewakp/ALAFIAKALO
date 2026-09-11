"""The printable treatment report.

Pins the things that would silently mislead a clinician holding a printout:
a recorded value rendered as "not recorded", the two time figures conflated,
saline deducted from the wrong number, and an absent thrill looking like an
empty box.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.therapy_report import render_session_report


def _session(**over):
    base = dict(
        id=42, session_number=7,
        scheduled_date=datetime(2026, 9, 1),
        facility_name="Victoria Island Dialysis",
        attending_physician="Dr. A. Balogun", attending_nurse=None,
        actual_start_time=datetime(2026, 9, 1, 8, 0),
        actual_end_time=datetime(2026, 9, 1, 12, 0),      # 240 min on the clock
        machine_total_time_minutes=228,                    # 12 min not dialysing
        dialysis_access_type="AV Fistula", needle_gauge="15G", needle_length=25.0,
        buttonhole_technique=False,
        access_thrill_bruit=True, access_redness_drainage=False,
        alarm_test_completed=True,
        dry_weight_kg=70.0, previous_post_weight_kg=70.2,
        pre_dialysis_weight_kg=72.4, post_dialysis_weight_kg=70.1,
        fluid_to_remove_kg=2.4, fluid_removed_ml=2300.0,   # scale-derived, net
        saline_added_ml=250.0, total_uf_liters=2.55,       # machine, gross
        pre_systolic_bp=140, pre_diastolic_bp=85, pre_heart_rate=78,
        post_systolic_bp=118, post_diastolic_bp=72, post_heart_rate=82,
        blood_flow_rate=400.0, dialysate_flow_rate=500.0,
        total_dialysate_liters=120.0, total_blood_volume_processed=96.0,
        dialyzer_appearance="clear",
        post_access_thrill_bruit=False,                    # ABSENT — urgent
        post_bleeding_stop_time="8 min", post_bruising=False,
        post_infiltration=False, post_shortness_of_breath=False, post_swelling=False,
        drugs_administered="Epoetin alfa 4000 units",
        complications=None, side_effects=None, patient_notes=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestTheTwoClocks:
    def test_clock_time_and_machine_time_are_both_printed(self):
        html = render_session_report(_session())
        # end - start = 240; the machine reports 228. Kt/V follows the machine
        # figure, so printing only the clock overstates the dose delivered.
        assert "240 min" in html
        assert "228 min" in html

    def test_a_missing_machine_time_does_not_borrow_the_clock(self):
        html = render_session_report(_session(machine_total_time_minutes=None))
        assert "240 min" in html            # the clock is still known
        assert "228 min" not in html
        # and the machine row says so rather than repeating the clock
        assert "Machine total time" in html


class TestSaline:
    def test_saline_is_deducted_from_the_machine_figure(self):
        html = render_session_report(_session())
        # 2.55 L gross - 250 mL = 2300 mL, which agrees with the scale.
        assert "2300 mL" in html

    def test_it_is_NOT_deducted_from_the_scale_figure(self):
        # The patient was weighed AFTER the saline went in, so fluid_removed_ml
        # is already net. Taking saline off it again would print 2050 and count
        # the same 250 mL twice.
        html = render_session_report(_session())
        assert "2050 mL" not in html

    def test_no_saline_means_gross_equals_net(self):
        html = render_session_report(_session(saline_added_ml=None))
        assert "2550 mL" in html


class TestThrill:
    def test_absent_shouts(self):
        html = render_session_report(_session())
        assert "ABSENT — urgent" in html

    def test_present_reads_as_normal(self):
        html = render_session_report(_session())
        assert "Present (normal)" in html

    def test_unassessed_is_neither(self):
        html = render_session_report(_session(access_thrill_bruit=None,
                                              post_access_thrill_bruit=None))
        assert "Not assessed" in html
        assert "Present (normal)" not in html
        assert "ABSENT" not in html


class TestNotRecorded:
    def test_an_absent_value_is_marked_and_explained(self):
        html = render_session_report(_session(attending_nurse=None))
        assert "—" in html
        # On paper a blank reads as a normal finding and the reader cannot ask.
        assert "means not recorded, not normal" in html

    def test_a_recorded_value_is_never_marked_absent(self):
        html = render_session_report(_session())
        assert "Victoria Island Dialysis" in html
        assert "Dr. A. Balogun" in html
        assert "Epoetin alfa 4000 units" in html

    def test_a_whole_number_float_does_not_print_spurious_precision(self):
        html = render_session_report(_session())
        assert "250 mL" in html
        assert "250.0 mL" not in html
        # a genuine decimal keeps its places
        assert "72.4 kg" in html


class TestEscaping:
    def test_free_text_cannot_inject_markup(self):
        html = render_session_report(
            _session(patient_notes="<script>alert('x')</script>"))
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
