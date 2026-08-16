/**
 * The physician's view of a patient's dialysis history.
 *
 * The generic category renderer showed this as a flat table whose Detail and
 * Session columns were mostly em-dashes, with "No trend to plot" above it — on a
 * patient with 2005 sessions and 16k intradialytic readings. A nephrologist
 * needs the same session report the patient already has, plus the two things
 * only a clinician does: read the intradialytic curve, and sign off.
 *
 * Layout deliberately mirrors the patient's Hemodialysis "Session Reports" tab,
 * so the physician and the patient are looking at the same artifact.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { ArrowLeft, ShieldCheck, FileSignature } from 'lucide-react';
import api from '../../services/api';
import { colorAt, CHART_INK } from './chartPalette';

const num = (v, digits = 1) =>
  v === null || v === undefined || Number.isNaN(Number(v)) ? null : Number(v).toFixed(digits);

const mean = (rows, key) => {
  const vals = rows.map(r => r[key]).filter(v => v !== null && v !== undefined && !Number.isNaN(Number(v)));
  return vals.length ? vals.reduce((a, b) => a + Number(b), 0) / vals.length : null;
};

const weekday = (iso) => {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('en-US', { weekday: 'long' });
};

/* ───────── list: stat tiles + one card per session ───────── */

export default function TherapyReport({ patientId, rows, days }) {
  const [openId, setOpenId] = useState(null);       // expanded inline summary
  const [reportId, setReportId] = useState(null);   // full-page session report
  const [reviewed, setReviewed] = useState({});     // id → signoff, after sign-off

  // Only haemodialysis rows carry a session_id; PD rows have their own screen.
  const sessions = useMemo(() => (rows || []).filter(r => r.session_id), [rows]);

  if (reportId) {
    return (
      <SessionReport
        patientId={patientId}
        sessionId={reportId}
        onBack={() => setReportId(null)}
        onReviewed={(sid, signoff) => setReviewed(m => ({ ...m, [sid]: signoff }))}
      />
    );
  }

  if (!sessions.length) {
    return (
      <div className="card" style={{ padding: '1.25rem', color: 'var(--color-text-secondary)' }}>
        No therapy sessions in this period.
      </div>
    );
  }

  const tiles = [
    { label: 'Sessions', value: String(sessions.length), tone: '#2a78d6' },
    { label: 'Avg Pre Wt', value: fmtTile(mean(sessions, 'pre_weight_kg'), 1, 'kg'), tone: '#1baf7a' },
    { label: 'Avg Post Wt', value: fmtTile(mean(sessions, 'post_weight_kg'), 1, 'kg'), tone: '#1baf7a' },
    { label: 'Avg UF', value: fmtTile(mean(sessions, 'fluid_removed_ml'), 0, 'mL'), tone: '#eb6834' },
    { label: 'Avg Duration', value: fmtTile(mean(sessions, 'duration_minutes'), 0, 'min'), tone: '#7c3aed' },
  ];

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: '1rem' }}>
        {tiles.map(t => <StatTile key={t.label} {...t} />)}
      </div>

      <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginBottom: 8 }}>
        {sessions.length} session{sessions.length === 1 ? '' : 's'} in the last {days} days
      </div>

      {sessions.map((s) => {
        const signoff = reviewed[s.session_id];
        const status = signoff?.flowsheet_status ?? s.flowsheet_status;
        const isReviewed = status === 'reviewed' || Boolean(signoff?.reviewed_at ?? s.reviewed_at);
        return (
          <div key={s.session_id} className="card" style={{ padding: '0.9rem 1rem', marginBottom: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <button
                onClick={() => setReportId(s.session_id)}
                style={{
                  background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                  font: 'inherit', fontWeight: 700, color: 'var(--color-primary)',
                }}
              >
                {new Date(`${s.date}T00:00:00`).toLocaleDateString()}
              </button>
              <Chip>{s.status || 'completed'}</Chip>
              {isReviewed && <Chip tone="#1baf7a"><ShieldCheck size={12} /> reviewed</Chip>}
              <span style={{ color: 'var(--color-text-secondary)', fontSize: '0.8rem' }}>
                {weekday(s.date)}
              </span>

              <span style={{ marginLeft: 'auto', display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
                {s.pre_weight_kg != null && s.post_weight_kg != null && (
                  <strong>{num(s.pre_weight_kg)} → {num(s.post_weight_kg)} kg</strong>
                )}
                {s.fluid_removed_ml != null && (
                  <span style={{ color: '#eb6834', fontWeight: 600 }}>{num(s.fluid_removed_ml, 0)} mL</span>
                )}
                {s.duration_minutes != null && (
                  <span style={{ color: '#7c3aed', fontWeight: 600 }}>{s.duration_minutes} min</span>
                )}
                <button
                  onClick={() => setOpenId(openId === s.session_id ? null : s.session_id)}
                  className="btn btn-sm"
                  style={{ background: 'transparent', border: '1px solid var(--color-border)' }}
                  aria-expanded={openId === s.session_id}
                >
                  {s.readings} reading{s.readings === 1 ? '' : 's'}
                </button>
              </span>
            </div>

            {(s.pre_bp || s.post_bp) && (
              <div style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)', marginTop: 6 }}>
                <strong>BP:</strong> Pre {s.pre_bp || '—'} → Post {s.post_bp || '—'}
                {(s.pre_heart_rate || s.post_heart_rate) &&
                  <> {' | '}<strong>HR:</strong> {s.pre_heart_rate ?? '—'} → {s.post_heart_rate ?? '—'}</>}
              </div>
            )}

            {openId === s.session_id && (
              <div style={{ marginTop: 10 }}>
                <button className="btn btn-sm btn-primary" onClick={() => setReportId(s.session_id)}>
                  Open full session report
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function fmtTile(value, digits, unit) {
  return value === null ? '—' : `${Number(value).toFixed(digits)} ${unit}`;
}

function StatTile({ label, value, tone }) {
  return (
    <div className="card" style={{ padding: '0.85rem 1.1rem', minWidth: 132, borderTop: `3px solid ${tone}` }}>
      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: tone }}>{value}</div>
      <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>{label}</div>
    </div>
  );
}

function Chip({ children, tone }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: tone ? `${tone}1a` : 'var(--color-surface-2, #eef2ff)',
      color: tone || 'var(--color-primary)',
      borderRadius: 12, padding: '2px 9px', fontSize: 12, fontWeight: 600,
    }}>{children}</span>
  );
}

/* ───────── one session: flowsheet, intradialytic charts, sign-off ───────── */

function SessionReport({ patientId, sessionId, onBack, onReviewed }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const isDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;

  useEffect(() => {
    let cancelled = false;
    setData(null); setError(null);
    api.get(`/clinician-dashboard/patient/${patientId}/therapy-sessions/${sessionId}`)
      .then(({ data: d }) => { if (!cancelled) setData(d); })
      // An error must never fall through to the empty state: a blank session
      // report and a 403 are different facts (canon: "an error is not an
      // empty state").
      .catch(e => { if (!cancelled) setError(e?.response?.data?.detail || 'Could not load this session.'); });
    return () => { cancelled = true; };
  }, [patientId, sessionId]);

  const signOff = async () => {
    setBusy(true); setActionError(null);
    try {
      const { data: res } = await api.post(
        `/clinician-dashboard/patient/${patientId}/therapy-sessions/${sessionId}/review`);
      setData(d => ({ ...d, signoff: res.signoff }));
      onReviewed?.(sessionId, res.signoff);
    } catch (e) {
      setActionError(e?.response?.data?.detail || 'Sign-off failed.');
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <div>
        <BackBar onBack={onBack} title="Session" />
        <div className="card" style={{ padding: '1.5rem', color: 'var(--color-danger)' }}>{error}</div>
      </div>
    );
  }
  if (!data) return <div className="loading">Loading session…</div>;

  const s = data.session;
  const so = data.signoff || {};
  const reviewed = so.flowsheet_status === 'reviewed' || Boolean(so.reviewed_at);

  return (
    <div>
      <BackBar onBack={onBack} title={`${new Date(`${s.date}T00:00:00`).toLocaleDateString()} — ${data.patient.full_name}`} />

      <div className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
        <Facts items={[
          ['Therapy', s.name || (s.therapy || '').replace(/_/g, ' ')],
          ['Facility', s.facility_name],
          ['Access', s.dialysis_access_type],
          ['Attending', s.attending_physician],
          ['Nurse', s.attending_nurse],
          ['Duration', s.duration_minutes != null ? `${s.duration_minutes} min` : null],
          ['Pre weight', s.pre_dialysis_weight_kg != null ? `${num(s.pre_dialysis_weight_kg)} kg` : null],
          ['Post weight', s.post_dialysis_weight_kg != null ? `${num(s.post_dialysis_weight_kg)} kg` : null],
          ['Dry weight', s.dry_weight_kg != null ? `${num(s.dry_weight_kg)} kg` : null],
          ['Fluid removed', s.fluid_removed_ml != null ? `${num(s.fluid_removed_ml, 0)} mL` : null],
          ['Blood flow', s.blood_flow_rate != null ? `${num(s.blood_flow_rate, 0)} mL/min` : null],
          ['Pre BP', s.pre_systolic_bp ? `${s.pre_systolic_bp}/${s.pre_diastolic_bp}` : null],
          ['Post BP', s.post_systolic_bp ? `${s.post_systolic_bp}/${s.post_diastolic_bp}` : null],
          ['Pre HR', s.pre_heart_rate],
          ['Post HR', s.post_heart_rate],
          ['Tolerance', s.patient_tolerance],
        ]} />
        {(s.complications || s.adverse_reactions) && (
          <div style={{ marginTop: 10, color: 'var(--color-danger)', fontSize: '0.85rem' }}>
            {s.complications && <div><strong>Complications:</strong> {s.complications}</div>}
            {s.adverse_reactions && <div><strong>Adverse reactions:</strong> {s.adverse_reactions}</div>}
          </div>
        )}
        {s.patient_notes && (
          <div style={{ marginTop: 10, fontSize: '0.85rem' }}>
            <strong>Patient notes:</strong> {s.patient_notes}
          </div>
        )}
      </div>

      <IntradialyticCharts readings={data.readings} isDark={isDark} />

      {data.notes?.length > 0 && (
        <div className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
          <h3 style={{ margin: '0 0 8px', fontSize: '0.95rem' }}>Clinical notes</h3>
          {data.notes.map(n => (
            <div key={n.id} style={{ borderTop: '1px solid var(--color-border)', paddingTop: 8, marginTop: 8 }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
                {n.author_role || 'clinician'} · {n.note_type} · {new Date(n.created_at).toLocaleString()}
              </div>
              <div>{n.note_text}</div>
            </div>
          ))}
        </div>
      )}

      <SignOffPanel
        signoff={so} reviewed={reviewed} busy={busy}
        error={actionError} onSignOff={signOff}
      />
    </div>
  );
}

function BackBar({ onBack, title }) {
  return (
    <div className="page-header">
      <div className="page-header-left">
        <button className="btn btn-secondary btn-sm" onClick={onBack}>
          <ArrowLeft size={16} /> Back
        </button>
        <h1 className="page-title">{title}</h1>
      </div>
    </div>
  );
}

function Facts({ items }) {
  const shown = items.filter(([, v]) => v !== null && v !== undefined && v !== '');
  if (!shown.length) return <div style={{ color: 'var(--color-text-secondary)' }}>No details recorded.</div>;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 10 }}>
      {shown.map(([k, v]) => (
        <div key={k}>
          <div style={{ fontSize: '0.72rem', color: 'var(--color-text-secondary)', textTransform: 'uppercase' }}>{k}</div>
          <div style={{ fontWeight: 600 }}>{String(v)}</div>
        </div>
      ))}
    </div>
  );
}

/**
 * The intradialytic curve — what a nephrologist actually reads a session for.
 * Grouped by unit so BP, pulse and UF never share an axis; one chart each,
 * never a dual-axis plot.
 */
function IntradialyticCharts({ readings, isDark }) {
  const rows = (readings || []).filter(r => r.reading_time);
  if (rows.length < 2) {
    return (
      <div className="card" style={{ padding: '1rem', marginBottom: '1rem', color: 'var(--color-text-secondary)' }}>
        {rows.length === 0
          ? 'No intradialytic readings were recorded for this session.'
          : 'Only one intradialytic reading — not enough to plot a curve.'}
      </div>
    );
  }

  const groups = [
    { unit: 'mmHg', keys: [['systolic_bp', 'Systolic'], ['diastolic_bp', 'Diastolic'], ['mean_arterial_pressure', 'MAP']] },
    { unit: 'bpm', keys: [['pulse', 'Pulse']] },
    { unit: 'mL', keys: [['uf_volume_removed', 'UF removed']] },
    { unit: 'mL/min', keys: [['blood_flow_rate', 'Blood flow']] },
  ];

  return (
    <>
      {groups.map(g => {
        const present = g.keys.filter(([k]) => rows.some(r => r[k] !== null && r[k] !== undefined));
        if (!present.length) return null;
        return (
          <div key={g.unit} className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
            <h3 style={{ margin: '0 0 6px', fontSize: '0.95rem' }}>
              {present.map(([, l]) => l).join(' · ')} <span style={{ color: 'var(--color-text-secondary)', fontWeight: 400 }}>({g.unit})</span>
            </h3>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid stroke={CHART_INK.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="reading_time" stroke={CHART_INK.axis} fontSize={12} />
                <YAxis stroke={CHART_INK.axis} fontSize={12} width={48} />
                <Tooltip />
                <Legend />
                {present.map(([k, label], i) => (
                  <Line key={k} type="monotone" dataKey={k} name={label}
                        stroke={colorAt(i, isDark)} strokeWidth={2} dot={{ r: 3 }} connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        );
      })}
    </>
  );
}

/**
 * Sign-off. The panel always states what the PATIENT did, not just what the
 * physician is about to do — attesting to a record nobody signed is a different
 * act from countersigning a signed one, and the physician should see which.
 */
function SignOffPanel({ signoff, reviewed, busy, error, onSignOff }) {
  return (
    <div className="card" style={{ padding: '1rem' }}>
      <h3 style={{ margin: '0 0 8px', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: 6 }}>
        <FileSignature size={16} /> Sign-off
      </h3>

      <div style={{ fontSize: '0.83rem', color: 'var(--color-text-secondary)', marginBottom: 10 }}>
        <div>Patient signature: {signoff.signed_at ? new Date(signoff.signed_at).toLocaleString() : 'not signed'}</div>
        <div>Nurse countersignature: {signoff.countersigned_at ? new Date(signoff.countersigned_at).toLocaleString() : 'none'}</div>
        <div>Physician review: {signoff.reviewed_at ? new Date(signoff.reviewed_at).toLocaleString() : 'not reviewed'}</div>
        {signoff.payload_hash && (
          <div style={{ marginTop: 6, wordBreak: 'break-all' }}>
            <ShieldCheck size={12} style={{ verticalAlign: -2 }} /> Integrity hash:{' '}
            <code style={{ fontSize: '0.72rem' }}>{signoff.payload_hash.slice(0, 32)}…</code>
          </div>
        )}
      </div>

      {error && <div style={{ color: 'var(--color-danger)', marginBottom: 8 }}>{error}</div>}

      {reviewed ? (
        <Chip tone="#1baf7a"><ShieldCheck size={12} /> Reviewed and anchored</Chip>
      ) : (
        <button className="btn btn-primary" onClick={onSignOff} disabled={busy}>
          {busy ? 'Signing…' : 'Sign off on this session'}
        </button>
      )}
    </div>
  );
}
