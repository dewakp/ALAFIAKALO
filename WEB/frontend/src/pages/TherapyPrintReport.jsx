import { useCallback, useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import './TherapyPrintReport.css';

/**
 * A printable hemodialysis treatment report.
 *
 * Distinct from `pages/clinician/TherapyReport.jsx`, which is the clinician's
 * interactive review screen (sign-off, notes, integrity). This one is the
 * paper artefact both readers print.
 *
 * Print-to-PDF rather than a server-rendered PDF: the browser's own export is
 * what every patient and clinician already has, it needs no new dependency in
 * the image, and it cannot drift from the screen because it IS the screen. The
 * cost is that the layout has to be built for paper, which `TherapyReport.css`
 * does with an `@media print` block.
 *
 * ONE report serves both readers, from two endpoints. A patient reads their own
 * session; a clinician reads it through the authorised route that checks the
 * data-sharing grant. Two components would drift, and the one that drifted
 * would be the one a clinician relies on.
 */

const NOT_RECORDED = '—';

/** Reads a value, distinguishing "not recorded" from zero. */
const val = (v, suffix = '') =>
  v === null || v === undefined || v === '' ? NOT_RECORDED : `${v}${suffix}`;

const dt = (v) => {
  if (!v) return NOT_RECORDED;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString();
};

const day = (v) => {
  if (!v) return NOT_RECORDED;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleDateString();
};

/**
 * Thrill/bruit prints as WORDS, never a tick.
 *
 * On paper a tick is indistinguishable from a stray mark, and absent — the
 * urgent finding — must never be the thing that looks like an empty box.
 */
const thrill = (v) =>
  v === true ? 'Present (normal)' : v === false ? 'ABSENT — urgent' : 'Not assessed';

function Row({ label, children }) {
  return (
    <div className="tr-row">
      <span className="tr-label">{label}</span>
      <span className="tr-value">{children}</span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="tr-section">
      <h2>{title}</h2>
      <div className="tr-grid">{children}</div>
    </section>
  );
}

export default function TherapyPrintReport() {
  const { sessionId } = useParams();
  const [params] = useSearchParams();
  // A clinician opens the same report with ?patient=<id>; the backend still
  // decides whether they may see it.
  const patientId = params.get('patient');

  const [session, setSession] = useState(null);
  const [patient, setPatient] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const path = patientId
        ? `/clinician-dashboard/patient/${patientId}/therapy-sessions/${sessionId}`
        : `/chronic/therapy-sessions/${sessionId}`;
      const { data } = await api.get(path);
      // The clinician route wraps the session alongside the patient it belongs
      // to; the patient route returns the session alone.
      setSession(data.session || data);
      setPatient(data.patient || null);
      setError('');
    } catch (err) {
      // A failed fetch must never render as a blank report — a clinician would
      // read empty fields as findings.
      setError(apiErrorMessage(err, 'This report could not be loaded.'));
    } finally {
      setLoading(false);
    }
  }, [sessionId, patientId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="tr-page"><p>Loading report…</p></div>;

  if (error) {
    return (
      <div className="tr-page">
        <div className="tr-error" role="alert">{error}</div>
        <button className="btn btn-secondary tr-noprint" onClick={load}>Try again</button>
      </div>
    );
  }

  const s = session || {};

  // Net removal is the figure the dry weight is judged against. Shown here for
  // the same reason it is shown on the form: gross removal credits the patient
  // with tolerating ultrafiltration that was partly given back.
  // `fluid_removed_ml` is (pre − post) × 1000 — weight-derived, and the patient
  // was weighed AFTER the saline went in, so it is already net. The saline
  // deduction belongs on the MACHINE's gross UF instead; subtracting it from
  // the scale figure would count the same volume twice.
  const saline = Number(s.saline_added_ml);
  const given = Number.isFinite(saline) && s.saline_added_ml != null ? saline : 0;
  const uf = Number(s.total_uf_liters);
  const netFromMachine = Number.isFinite(uf) && s.total_uf_liters != null
    ? Math.round(uf * 1000 - given)
    : null;

  let clockMinutes = null;
  if (s.actual_start_time && s.actual_end_time) {
    const ms = new Date(s.actual_end_time) - new Date(s.actual_start_time);
    if (Number.isFinite(ms) && ms > 0) clockMinutes = Math.round(ms / 60000);
  }

  return (
    <div className="tr-page">
      <div className="tr-noprint tr-actions">
        <button className="btn btn-primary" onClick={() => window.print()}>
          Print / Save as PDF
        </button>
      </div>

      <header className="tr-header">
        <div>
          <h1>Hemodialysis Treatment Report</h1>
          <p className="tr-sub">
            {patient?.full_name ? `${patient.full_name} · ` : ''}
            Session {s.session_number ?? s.id} · {day(s.scheduled_date || s.date)}
          </p>
        </div>
        <div className="tr-brand">ALAFIA</div>
      </header>

      <Section title="Session">
        <Row label="Date">{day(s.scheduled_date || s.date)}</Row>
        <Row label="Facility">{val(s.facility_name)}</Row>
        <Row label="Attending physician">{val(s.attending_physician)}</Row>
        <Row label="Attending nurse">{val(s.attending_nurse)}</Row>
        <Row label="Start">{dt(s.actual_start_time)}</Row>
        <Row label="End">{dt(s.actual_end_time)}</Row>
        {/* Two different numbers, printed as two different numbers. The clock
            is end − start; the machine reports time actually dialysing and
            excludes alarms and pauses. Kt/V follows the machine figure. */}
        <Row label="Clock time (end − start)">
          {clockMinutes == null ? NOT_RECORDED : `${clockMinutes} min`}
        </Row>
        <Row label="Machine total time">{val(s.machine_total_time_minutes, ' min')}</Row>
      </Section>

      <Section title="Access (pre-treatment)">
        <Row label="Access type">{val(s.dialysis_access_type)}</Row>
        <Row label="Needle gauge">{val(s.needle_gauge)}</Row>
        <Row label="Needle length">{val(s.needle_length, ' mm')}</Row>
        <Row label="Buttonhole">{s.buttonhole_technique ? 'Yes' : 'No'}</Row>
        <Row label="Thrill / bruit">{thrill(s.access_thrill_bruit)}</Row>
        <Row label="Redness / drainage">{s.access_redness_drainage ? 'Yes' : 'No'}</Row>
        <Row label="Alarm test complete">{s.alarm_test_completed ? 'Yes' : 'No'}</Row>
      </Section>

      <Section title="Weights &amp; fluid">
        <Row label="Dry weight">{val(s.dry_weight_kg, ' kg')}</Row>
        <Row label="Previous post weight">{val(s.previous_post_weight_kg, ' kg')}</Row>
        <Row label="Pre weight">{val(s.pre_dialysis_weight_kg, ' kg')}</Row>
        <Row label="Post weight">{val(s.post_dialysis_weight_kg, ' kg')}</Row>
        <Row label="Fluid to remove">{val(s.fluid_to_remove_kg, ' kg')}</Row>
        <Row label="Fluid removed">{val(s.fluid_removed_ml, ' mL')}</Row>
        <Row label="Saline added">{val(s.saline_added_ml, ' mL')}</Row>
        <Row label="Total UF (machine)">{val(s.total_uf_liters, ' L')}</Row>
        <Row label="Net from machine (UF − saline)">
          {netFromMachine == null ? NOT_RECORDED : `${netFromMachine} mL`}
        </Row>
      </Section>

      <Section title="Vitals">
        <Row label="Pre BP (sitting)">
          {s.pre_systolic_bp || s.pre_diastolic_bp
            ? `${val(s.pre_systolic_bp)}/${val(s.pre_diastolic_bp)} mmHg` : NOT_RECORDED}
        </Row>
        <Row label="Pre heart rate">{val(s.pre_heart_rate, ' bpm')}</Row>
        <Row label="Post BP (sitting)">
          {s.post_systolic_bp || s.post_diastolic_bp
            ? `${val(s.post_systolic_bp)}/${val(s.post_diastolic_bp)} mmHg` : NOT_RECORDED}
        </Row>
        <Row label="Post heart rate">{val(s.post_heart_rate, ' bpm')}</Row>
      </Section>

      <Section title="Treatment totals">
        <Row label="Blood flow rate">{val(s.blood_flow_rate, ' mL/min')}</Row>
        <Row label="Dialysate flow rate">{val(s.dialysate_flow_rate, ' mL/min')}</Row>
        <Row label="Total dialysate">{val(s.total_dialysate_liters, ' L')}</Row>
        <Row label="Blood volume processed">{val(s.total_blood_volume_processed, ' L')}</Row>
        <Row label="Dialyzer appearance">{val(s.dialyzer_appearance)}</Row>
      </Section>

      <Section title="Post-treatment assessment">
        <Row label="Thrill / bruit">{thrill(s.post_access_thrill_bruit)}</Row>
        <Row label="Bleeding stop time">{val(s.post_bleeding_stop_time)}</Row>
        <Row label="Bruising">{s.post_bruising ? 'Yes' : 'No'}</Row>
        <Row label="Infiltration">{s.post_infiltration ? 'Yes' : 'No'}</Row>
        <Row label="Shortness of breath">{s.post_shortness_of_breath ? 'Yes' : 'No'}</Row>
        <Row label="Swelling">{s.post_swelling ? 'Yes' : 'No'}</Row>
      </Section>

      {s.drugs_administered && (
        <section className="tr-section">
          <h2>Drugs given this session</h2>
          <p className="tr-free">{s.drugs_administered}</p>
        </section>
      )}

      {(s.patient_notes || s.complications || s.side_effects) && (
        <section className="tr-section">
          <h2>Notes</h2>
          {s.complications && <p className="tr-free"><strong>Complications:</strong> {s.complications}</p>}
          {s.side_effects && <p className="tr-free"><strong>Side effects:</strong> {s.side_effects}</p>}
          {s.patient_notes && <p className="tr-free">{s.patient_notes}</p>}
        </section>
      )}

      <footer className="tr-footer">
        <span>Generated {new Date().toLocaleString()}</span>
        <span>
          {/* Stated on every page: a printed copy is a snapshot, and a reader
              must not take an unrecorded field for a normal one. */}
          “{NOT_RECORDED}” means not recorded, not normal.
        </span>
      </footer>
    </div>
  );
}
