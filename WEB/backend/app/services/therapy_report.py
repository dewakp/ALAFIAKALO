"""Render a hemodialysis session as printable HTML.

ONE renderer, printed by all three clients. Web has its own React view for the
on-screen report, but iOS and Android print THIS — and the clinician and the
patient print the same document, because a report that differs by who opened it
is not a record.

Three templates would drift, and the one that drifted would be the one nobody
looked at until a clinician was reading it.

Why HTML rather than a generated PDF: every platform already has a print
pipeline that turns HTML into paginated PDF — `UIMarkupTextPrintFormatter` on
iOS, `WebView.createPrintDocumentAdapter` on Android, `window.print()` on the
web — and each gives the user AirPrint, "Save to Files" and "Save as PDF" for
free. A server-side PDF library would add a dependency to the image and take
those affordances away.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

#: Printed wherever a field holds no value. Stated in the footer too, because
#: on paper a blank reads as a normal finding and a clinician cannot ask.
NOT_RECORDED = "—"


def _v(value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return NOT_RECORDED
    # Floats print as "250.0 mL" otherwise, which reads as spurious precision
    # on a figure somebody wrote down as 250. Trailing zeros are dropped; a
    # genuine decimal (72.4 kg) keeps them.
    if isinstance(value, float):
        value = int(value) if value.is_integer() else round(value, 2)
    return f"{escape(str(value))}{escape(suffix)}"


def _yn(value: Any) -> str:
    # A nullable boolean has three meanings and "No" is not one of them when
    # the value is absent.
    if value is None:
        return NOT_RECORDED
    return "Yes" if value else "No"


def _thrill(value: Any) -> str:
    """Words, never a tick.

    On paper a tick is indistinguishable from a stray mark, and ABSENT — the
    urgent finding — must never be the thing that looks like an empty box.
    """
    if value is None:
        return "Not assessed"
    return "Present (normal)" if value else "ABSENT — urgent"


def _dt(value: Any) -> str:
    if not value:
        return NOT_RECORDED
    if isinstance(value, datetime):
        return escape(value.strftime("%Y-%m-%d %H:%M"))
    return escape(str(value))


def _day(value: Any) -> str:
    if not value:
        return NOT_RECORDED
    return escape(str(value)[:10])


def _row(label: str, value: str) -> str:
    return (f'<div class="row"><span class="lbl">{escape(label)}</span>'
            f'<span class="val">{value}</span></div>')


def _section(title: str, rows: list[str]) -> str:
    return (f'<section><h2>{escape(title)}</h2>'
            f'<div class="grid">{"".join(rows)}</div></section>')


def render_session_report(session, *, patient_name: str | None = None) -> str:
    """The printable document for one session."""
    s = session

    # Clock time and machine time are different numbers and neither is
    # derivable from the other: the clock is end - start; the machine reports
    # time actually dialysing and excludes alarms and pauses. Kt/V follows the
    # machine figure, so conflating them overstates the dose delivered.
    clock = NOT_RECORDED
    if s.actual_start_time and s.actual_end_time:
        delta = (s.actual_end_time - s.actual_start_time).total_seconds() / 60
        if delta > 0:
            clock = f"{round(delta)} min"

    # `fluid_removed_ml` is (pre - post) x 1000 — weight-derived, and the
    # patient was weighed AFTER the saline went in, so it is already net. The
    # saline deduction belongs on the machine's gross UF; taking it off the
    # scale figure would count the same volume twice.
    net_machine = NOT_RECORDED
    if s.total_uf_liters is not None:
        given = s.saline_added_ml or 0
        net_machine = f"{round(s.total_uf_liters * 1000 - given)} mL"

    # The patient's name is the IDENTIFIER on a clinical document, not a
    # detail. It goes on its own line, first — and when it is absent that is
    # STATED, because a gap where a name should be is a gap a reader fills in
    # themselves, and a report that could be confused between two people is
    # worse than no report.
    patient_line = (
        f'<p class="patient">{escape(patient_name)}</p>' if patient_name
        else '<p class="patient missing">Patient name not recorded</p>'
    )

    body = "".join([
        _section("Session", [
            _row("Date", _day(s.scheduled_date)),
            _row("Facility", _v(s.facility_name)),
            _row("Attending physician", _v(s.attending_physician)),
            _row("Attending nurse", _v(s.attending_nurse)),
            _row("Start", _dt(s.actual_start_time)),
            _row("End", _dt(s.actual_end_time)),
            _row("Clock time (end − start)", clock),
            _row("Machine total time", _v(s.machine_total_time_minutes, " min")),
        ]),
        _section("Access (pre-treatment)", [
            _row("Access type", _v(s.dialysis_access_type)),
            _row("Needle gauge", _v(s.needle_gauge)),
            _row("Needle length", _v(s.needle_length, " mm")),
            _row("Buttonhole", _yn(s.buttonhole_technique)),
            _row("Thrill / bruit", _thrill(s.access_thrill_bruit)),
            _row("Redness / drainage", _yn(s.access_redness_drainage)),
            _row("Alarm test complete", _yn(s.alarm_test_completed)),
        ]),
        _section("Weights & fluid", [
            _row("Dry weight", _v(s.dry_weight_kg, " kg")),
            _row("Previous post weight", _v(s.previous_post_weight_kg, " kg")),
            _row("Pre weight", _v(s.pre_dialysis_weight_kg, " kg")),
            _row("Post weight", _v(s.post_dialysis_weight_kg, " kg")),
            _row("Fluid to remove", _v(s.fluid_to_remove_kg, " kg")),
            _row("Fluid removed (scale)", _v(s.fluid_removed_ml, " mL")),
            _row("Saline added", _v(s.saline_added_ml, " mL")),
            _row("Total UF (machine)", _v(s.total_uf_liters, " L")),
            _row("Net from machine (UF − saline)", net_machine),
        ]),
        _section("Vitals", [
            _row("Pre BP (sitting)",
                 f"{_v(s.pre_systolic_bp)}/{_v(s.pre_diastolic_bp)} mmHg"
                 if s.pre_systolic_bp or s.pre_diastolic_bp else NOT_RECORDED),
            _row("Pre heart rate", _v(s.pre_heart_rate, " bpm")),
            _row("Post BP (sitting)",
                 f"{_v(s.post_systolic_bp)}/{_v(s.post_diastolic_bp)} mmHg"
                 if s.post_systolic_bp or s.post_diastolic_bp else NOT_RECORDED),
            _row("Post heart rate", _v(s.post_heart_rate, " bpm")),
        ]),
        _section("Treatment totals", [
            _row("Blood flow rate", _v(s.blood_flow_rate, " mL/min")),
            _row("Dialysate flow rate", _v(s.dialysate_flow_rate, " mL/min")),
            _row("Total dialysate", _v(s.total_dialysate_liters, " L")),
            _row("Blood volume processed", _v(s.total_blood_volume_processed, " L")),
            _row("Dialyzer appearance", _v(s.dialyzer_appearance)),
        ]),
        _section("Post-treatment assessment", [
            _row("Thrill / bruit", _thrill(s.post_access_thrill_bruit)),
            _row("Bleeding stop time", _v(s.post_bleeding_stop_time)),
            _row("Bruising", _yn(s.post_bruising)),
            _row("Infiltration", _yn(s.post_infiltration)),
            _row("Shortness of breath", _yn(s.post_shortness_of_breath)),
            _row("Swelling", _yn(s.post_swelling)),
        ]),
    ])

    if s.drugs_administered:
        body += (f'<section><h2>Drugs given this session</h2>'
                 f'<p class="free">{escape(s.drugs_administered)}</p></section>')

    notes = []
    if s.complications:
        notes.append(f"<p class='free'><strong>Complications:</strong> {escape(s.complications)}</p>")
    if s.side_effects:
        notes.append(f"<p class='free'><strong>Side effects:</strong> {escape(s.side_effects)}</p>")
    if s.patient_notes:
        notes.append(f"<p class='free'>{escape(s.patient_notes)}</p>")
    if notes:
        body += f'<section><h2>Notes</h2>{"".join(notes)}</section>'

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Hemodialysis Treatment Report</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color: #0f172a;
          margin: 0; padding: 16px; }}
  header {{ display: flex; justify-content: space-between; align-items: flex-start;
            border-bottom: 2px solid #000; padding-bottom: 8px; margin-bottom: 14px; }}
  h1 {{ font-size: 16pt; margin: 0 0 3px; }}
  .patient {{ font-size: 12pt; font-weight: 700; margin: 2px 0; }}
  .patient.missing {{ font-weight: 400; color: #b91c1c; }}
  .sub {{ font-size: 9pt; color: #475569; margin: 0; }}
  .brand {{ font-weight: 800; letter-spacing: .5px; }}
  /* Never split a section across a page break: half a table on page two
     invites reading a truncated list as a complete one. */
  section {{ margin-bottom: 14px; break-inside: avoid; page-break-inside: avoid; }}
  h2 {{ font-size: 9pt; text-transform: uppercase; letter-spacing: .6px;
        border-bottom: 1px solid #cbd5e1; padding-bottom: 3px; margin: 0 0 6px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1px 20px; }}
  .row {{ display: flex; justify-content: space-between; gap: 10px; padding: 2px 0;
          border-bottom: 1px dotted #e2e8f0; font-size: 9.5pt; }}
  .lbl {{ color: #475569; }}
  .val {{ font-weight: 600; text-align: right; }}
  .free {{ font-size: 9.5pt; white-space: pre-wrap; margin: 0 0 5px; }}
  footer {{ display: flex; justify-content: space-between; gap: 10px; font-size: 7.5pt;
            color: #64748b; border-top: 1px solid #cbd5e1; padding-top: 6px; margin-top: 16px; }}
  @page {{ margin: 14mm; }}
</style></head>
<body>
<header>
  <div>
    <h1>Hemodialysis Treatment Report</h1>
    {patient_line}
    <p class="sub">Session {escape(str(s.session_number or s.id))} · {_day(s.scheduled_date)}</p>
  </div>
  <div class="brand">ALAFIA</div>
</header>
{body}
<footer>
  <span>Generated {escape(generated)}</span>
  <span>“{NOT_RECORDED}” means not recorded, not normal.</span>
</footer>
</body></html>"""
