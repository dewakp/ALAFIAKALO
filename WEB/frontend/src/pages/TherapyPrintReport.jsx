import { useCallback, useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { apiErrorMessage } from '../utils/apiError';
import './TherapyPrintReport.css';
import { t } from '../i18n';

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

/**
 * These timestamps are WALL CLOCKS, not instants.
 *
 * `scheduled_date`, `actual_start_time` and `actual_end_time` are
 * `timestamp WITHOUT time zone` — "13:41 on 2026-09-13" as written on the
 * flowsheet, with no offset attached. The API puts a `Z` on the wire anyway,
 * so `new Date(v)` reads them as UTC and shifts them into the viewer's zone:
 * a session stored as 2026-09-13 00:00 came out as **9/12** in EDT, and a
 * 13:41 start displayed as 9:41 AM.
 *
 * So they are read by their COMPONENTS and never converted. A time recorded at
 * the chair is that time wherever the record is later opened — converting it
 * would make the same session read differently in two places, which is worse
 * than being four hours out in one.
 */
const parts = (v) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(String(v || ''));
  return m ? { y: m[1], mo: m[2], d: m[3], hh: m[4], mm: m[5] } : null;
};

const dt = (v) => {
  if (!v) return NOT_RECORDED;
  const p = parts(v);
  if (!p) return String(v);
  return p.hh ? `${p.mo}/${p.d}/${p.y}, ${p.hh}:${p.mm}` : `${p.mo}/${p.d}/${p.y}`;
};

const day = (v) => {
  if (!v) return NOT_RECORDED;
  const p = parts(v);
  return p ? `${p.mo}/${p.d}/${p.y}` : String(v);
};

/** Clock only — the session's date is stated once at the top. */
const clockOf = (v) => {
  const p = parts(v);
  return p && p.hh ? `${p.hh}:${p.mm}` : NOT_RECORDED;
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

  // A patient printing their OWN session gets no `patient` object back — the
  // route returns the session alone — so the name came out blank. The signed-in
  // user IS the patient on that path, and their name is already in hand.
  const { user } = useAuth();
  const [session, setSession] = useState(null);
  const [patient, setPatient] = useState(null);
  const [error, setError] = useState('');
  const [printError, setPrintError] = useState('');
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
      // Clinician route wraps the patient; patient route does not — on that
      // path the signed-in user is the subject.
      setPatient(data.patient || (patientId ? null : user) || null);
      setError('');
    } catch (err) {
      // A failed fetch must never render as a blank report — a clinician would
      // read empty fields as findings.
      setError(apiErrorMessage(err, t('TherapyPrintReport.this_report_could_not_be_loaded')));
    } finally {
      setLoading(false);
    }
  }, [sessionId, patientId, user]);

  useEffect(() => { load(); }, [load]);

  /**
   * Print the SERVER-RENDERED report, not this page.
   *
   * `window.print()` on this component printed a preview that looked right and
   * then saved a blank PDF — the document that comes out of the browser is the
   * app's whole DOM with print rules layered over it, and anything the layout
   * does (a scroll container, a re-render while the dialog is open) lands in
   * the file rather than on the screen where it would be noticed.
   *
   * `services/therapy_report.py` already renders this session as a standalone
   * document, and iOS and Android print exactly that. Fetching it through the
   * authenticated client and printing it in a blank window removes the app
   * from the picture entirely — and makes the paper copy identical on all
   * three platforms, which is the point of having one renderer.
   */
  const printReport = useCallback(async () => {
    setPrintError('');
    const path = patientId
      ? `/clinician-dashboard/patient/${patientId}/therapy-sessions/${sessionId}/report.html`
      : `/chronic/therapy-sessions/${sessionId}/report.html`;
    let html;
    try {
      const res = await api.get(path, { responseType: 'text' });
      html = res.data;
    } catch (err) {
      // A print that silently does nothing is indistinguishable from a button
      // that was never wired.
      setPrintError(apiErrorMessage(err, t('TherapyPrintReport.this_report_could_not_be_prepared_for')));
      return;
    }

    const w = window.open('', '_blank');
    if (!w) {
      setPrintError(t('TherapyPrintReport.your_browser_blocked_the_print_window'));
      return;
    }
    w.document.open();
    w.document.write(html);
    w.document.close();
    // Wait for layout before printing, or the dialog can open on an empty
    // document — which is precisely the blank page this replaces.
    w.onload = () => { w.focus(); w.print(); };
  }, [sessionId, patientId]);



  if (loading) return <div className="tr-page"><p>{t('TherapyPrintReport.loading_report')}</p></div>;

  if (error) {
    return (
      <div className="tr-page">
        <div className="tr-error" role="alert">{error}</div>
        <button className="btn btn-secondary tr-noprint" onClick={load}>{t('TherapyPrintReport.try_again')}</button>
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

  // Minutes between two wall clocks, computed from their components. Both
  // carry the same spurious Z, so Date arithmetic happens to cancel — but only
  // while both are present and on the same day, which is exactly the case that
  // was wrong here.
  // Ordered by time: a table out of order reads as a different session.
  const readings = [...(s.intradialytic_readings || [])]
    .sort((a, b) => String(a.reading_time || '').localeCompare(String(b.reading_time || '')));
  const lowReadings = readings.filter(
    (r) => r.systolic_bp != null && r.systolic_bp < 90).length;

  let clockMinutes = null;
  {
    const a = parts(s.actual_start_time);
    const b = parts(s.actual_end_time);
    if (a?.hh && b?.hh) {
      const mins = (d) => Number(d.hh) * 60 + Number(d.mm);
      const sameDay = `${a.y}${a.mo}${a.d}` === `${b.y}${b.mo}${b.d}`;
      const delta = mins(b) - mins(a) + (sameDay ? 0 : 24 * 60);
      if (delta > 0) clockMinutes = delta;
    }
  }

  return (
    <div className="tr-page">
      <div className="tr-noprint tr-actions">
        <button className="btn btn-primary" onClick={printReport}>
          {t('TherapyPrintReport.print_save_as_pdf')}
        </button>
        {printError && (
          <span style={{ color: '#b91c1c', fontSize: '.85rem', marginLeft: '.6rem' }}>
            {printError}
          </span>
        )}
      </div>

      <header className="tr-header">
        <div>
          <h1>{t('TherapyPrintReport.hemodialysis_treatment_report')}</h1>
          {/* The patient's name is the IDENTIFIER on a clinical document, not
              a detail — a printed report that could be confused between two
              people is worse than no report. It is stated first and on its own
              line, and its absence is stated too rather than leaving a gap a
              reader would fill in themselves. */}
          <p className="tr-patient">
            {patient?.full_name || <span className="tr-missing">{t('TherapyPrintReport.patient_name_not_recorded')}</span>}
          </p>
          <p className="tr-sub">
            {t('TherapyPrintReport.session', { session_number: s.session_number ?? s.id, scheduled_date: day(s.scheduled_date || s.date) })}
          </p>
        </div>
        <div className="tr-brand">ALAFIA</div>
      </header>

      <Section title={t('TherapyPrintReport.session_2')}>
        <Row label={t('TherapyPrintReport.date')}>{day(s.scheduled_date || s.date)}</Row>
        <Row label={t('TherapyPrintReport.facility')}>{val(s.facility_name)}</Row>
        <Row label={t('TherapyPrintReport.attending_physician')}>{val(s.attending_physician)}</Row>
        <Row label={t('TherapyPrintReport.attending_nurse')}>{val(s.attending_nurse)}</Row>
        {/* Clock times — the date is on the line above. Where a time falls on
            a different day the full stamp is shown, so the mismatch is not
            hidden by only ever printing the clock. */}
        <Row label={t('TherapyPrintReport.start')}>
          {parts(s.actual_start_time) && day(s.actual_start_time) !== day(s.scheduled_date || s.date)
            ? `${dt(s.actual_start_time)} — not the session date`
            : clockOf(s.actual_start_time)}
        </Row>
        <Row label={t('TherapyPrintReport.end')}>
          {parts(s.actual_end_time) && day(s.actual_end_time) !== day(s.scheduled_date || s.date)
            ? `${dt(s.actual_end_time)} — not the session date`
            : clockOf(s.actual_end_time)}
        </Row>
        {/* Two different numbers, printed as two different numbers. The clock
            is end − start; the machine reports time actually dialysing and
            excludes alarms and pauses. Kt/V follows the machine figure. */}
        <Row label={t('TherapyPrintReport.clock_time_end_start')}>
          {clockMinutes == null ? NOT_RECORDED : `${clockMinutes} min`}
        </Row>
        <Row label={t('TherapyPrintReport.machine_total_time')}>{val(s.machine_total_time_minutes, ' min')}</Row>
      </Section>

      <Section title={t('TherapyPrintReport.access_pre_treatment')}>
        <Row label={t('TherapyPrintReport.access_type')}>{val(s.dialysis_access_type)}</Row>
        <Row label={t('TherapyPrintReport.needle_gauge')}>{val(s.needle_gauge)}</Row>
        <Row label={t('TherapyPrintReport.needle_length')}>{val(s.needle_length, ' mm')}</Row>
        <Row label={t('TherapyPrintReport.buttonhole')}>{s.buttonhole_technique ? 'Yes' : 'No'}</Row>
        <Row label={t('TherapyPrintReport.thrill_bruit')}>{thrill(s.access_thrill_bruit)}</Row>
        <Row label={t('TherapyPrintReport.redness_drainage')}>{s.access_redness_drainage ? 'Yes' : 'No'}</Row>
        <Row label={t('TherapyPrintReport.alarm_test_complete')}>{s.alarm_test_completed ? 'Yes' : 'No'}</Row>
      </Section>

      <Section title={t('TherapyPrintReport.weights_fluid')}>
        <Row label={t('TherapyPrintReport.dry_weight')}>{val(s.dry_weight_kg, ' kg')}</Row>
        <Row label={t('TherapyPrintReport.previous_post_weight')}>{val(s.previous_post_weight_kg, ' kg')}</Row>
        <Row label={t('TherapyPrintReport.pre_weight')}>{val(s.pre_dialysis_weight_kg, ' kg')}</Row>
        <Row label={t('TherapyPrintReport.post_weight')}>{val(s.post_dialysis_weight_kg, ' kg')}</Row>
        <Row label={t('TherapyPrintReport.fluid_to_remove')}>{val(s.fluid_to_remove_kg, ' kg')}</Row>
        <Row label={t('TherapyPrintReport.fluid_removed')}>{val(s.fluid_removed_ml, ' mL')}</Row>
        <Row label={t('TherapyPrintReport.saline_added')}>{val(s.saline_added_ml, ' mL')}</Row>
        <Row label={t('TherapyPrintReport.total_uf_machine')}>{val(s.total_uf_liters, ' L')}</Row>
        <Row label={t('TherapyPrintReport.net_from_machine_uf_saline')}>
          {netFromMachine == null ? NOT_RECORDED : `${netFromMachine} mL`}
        </Row>
      </Section>

      <Section title={t('TherapyPrintReport.vitals')}>
        <Row label={t('TherapyPrintReport.pre_bp_sitting')}>
          {s.pre_systolic_bp || s.pre_diastolic_bp
            ? `${val(s.pre_systolic_bp)}/${val(s.pre_diastolic_bp)} mmHg` : NOT_RECORDED}
        </Row>
        <Row label={t('TherapyPrintReport.pre_heart_rate')}>{val(s.pre_heart_rate, ' bpm')}</Row>
        <Row label={t('TherapyPrintReport.post_bp_sitting')}>
          {s.post_systolic_bp || s.post_diastolic_bp
            ? `${val(s.post_systolic_bp)}/${val(s.post_diastolic_bp)} mmHg` : NOT_RECORDED}
        </Row>
        <Row label={t('TherapyPrintReport.post_heart_rate')}>{val(s.post_heart_rate, ' bpm')}</Row>
      </Section>

      <Section title={t('TherapyPrintReport.treatment_totals')}>
        <Row label={t('TherapyPrintReport.blood_flow_rate')}>{val(s.blood_flow_rate, ' mL/min')}</Row>
        <Row label={t('TherapyPrintReport.dialysate_flow_rate')}>{val(s.dialysate_flow_rate, ' mL/min')}</Row>
        <Row label={t('TherapyPrintReport.total_dialysate')}>{val(s.total_dialysate_liters, ' L')}</Row>
        <Row label={t('TherapyPrintReport.blood_volume_processed')}>{val(s.total_blood_volume_processed, ' L')}</Row>
        <Row label={t('TherapyPrintReport.dialyzer_appearance')}>{val(s.dialyzer_appearance)}</Row>
      </Section>

      <Section title={t('TherapyPrintReport.post_treatment_assessment')}>
        <Row label={t('TherapyPrintReport.thrill_bruit')}>{thrill(s.post_access_thrill_bruit)}</Row>
        <Row label={t('TherapyPrintReport.bleeding_stop_time')}>{val(s.post_bleeding_stop_time)}</Row>
        <Row label={t('TherapyPrintReport.bruising')}>{s.post_bruising ? 'Yes' : 'No'}</Row>
        <Row label={t('TherapyPrintReport.infiltration')}>{s.post_infiltration ? 'Yes' : 'No'}</Row>
        <Row label={t('TherapyPrintReport.shortness_of_breath')}>{s.post_shortness_of_breath ? 'Yes' : 'No'}</Row>
        <Row label={t('TherapyPrintReport.swelling')}>{s.post_swelling ? 'Yes' : 'No'}</Row>
      </Section>

      {/* The readings, as they were taken. A flowsheet without them is a
          summary, not a record — and a mean hides the ending, which is the
          part that matters (§3am: the nadir is the finding). */}
      <section className="tr-section tr-readings">
        <h2>{t('TherapyPrintReport.intradialytic_readings', { value: readings.length ? ` (${readings.length})` : '' })}</h2>
        {readings.length === 0 ? (
          <p className="tr-free">{t('TherapyPrintReport.none_recorded_for_this_session', { NOT_RECORDED })}</p>
        ) : (
          <>
            {lowReadings > 0 && (
              <p className="tr-free tr-low">
                <strong>{(lowReadings === 1) ? t('TherapyPrintReport.reading_below_90_mmhg_systolic', { lowReadings }) : t('TherapyPrintReport.readings_below_90_mmhg_systolic', { lowReadings })}</strong> {t('TherapyPrintReport.intradialytic_hypotension')}
              </p>
            )}
            <div style={{ overflowX: 'auto' }}>
              <table className="tr-rdg">
                <thead>
                  <tr>{['Time', 'BP', 'Pulse', 'MAP', 'BFR', 'UFR', 'UF vol', 'Art P', 'Ven P', 'Remarks']
                    .map((h) => <th key={h}>{h}</th>)}</tr>
                </thead>
                <tbody>
                  {readings.map((r, i) => {
                    const low = r.systolic_bp != null && r.systolic_bp < 90;
                    return (
                      <tr key={r.id ?? i}>
                        <td>{String(r.reading_time || NOT_RECORDED).slice(0, 5)}</td>
                        <td className={low ? 'tr-low' : undefined}>
                          {r.systolic_bp != null
                            ? `${r.systolic_bp}/${r.diastolic_bp ?? NOT_RECORDED}`
                            : NOT_RECORDED}
                        </td>
                        <td>{val(r.pulse)}</td>
                        <td>{val(r.mean_arterial_pressure)}</td>
                        <td>{val(r.blood_flow_rate)}</td>
                        <td>{val(r.uf_rate)}</td>
                        <td>{val(r.uf_volume_removed)}</td>
                        <td>{val(r.arterial_pressure)}</td>
                        <td>{val(r.venous_pressure)}</td>
                        <td>{r.remarks || ''}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      {s.drugs_administered && (
        <section className="tr-section">
          <h2>{t('TherapyPrintReport.drugs_given_this_session')}</h2>
          <p className="tr-free">{s.drugs_administered}</p>
        </section>
      )}

      {(s.patient_notes || s.complications || s.side_effects) && (
        <section className="tr-section">
          <h2>{t('TherapyPrintReport.notes')}</h2>
          {s.complications && <p className="tr-free"><strong>{t('TherapyPrintReport.complications')}</strong> {s.complications}</p>}
          {s.side_effects && <p className="tr-free"><strong>{t('TherapyPrintReport.side_effects')}</strong> {s.side_effects}</p>}
          {s.patient_notes && <p className="tr-free">{s.patient_notes}</p>}
        </section>
      )}

      <footer className="tr-footer">
        <span>{t('TherapyPrintReport.generated', { value: new Date().toLocaleString() })}</span>
        <span>
          {/* Stated on every page: a printed copy is a snapshot, and a reader
              must not take an unrecorded field for a normal one. */}
          {t('TherapyPrintReport.means_not_recorded_not_normal', { NOT_RECORDED })}
        </span>
      </footer>
    </div>
  );
}
