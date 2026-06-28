import React, { useState, useEffect, useMemo } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import api from '../services/api';
import BackButton from '../components/BackButton';

/* ───────── constants ───────── */
const ROUTES = ['IV Push', 'IV Drip', 'IV Infusion', 'Oral', 'Subcutaneous', 'Intramuscular', 'Intrathecal', 'Intraperitoneal', 'Topical'];
const STATUS_OPTIONS = ['scheduled', 'in_progress', 'completed', 'cancelled', 'missed'];
const TOLERANCE_OPTIONS = ['Well Tolerated', 'Moderate', 'Poor', 'Severe Reaction'];
const COMMON_SIDE_EFFECTS = [
  'Nausea', 'Vomiting', 'Fatigue', 'Hair Loss', 'Mouth Sores', 'Neuropathy',
  'Low WBC', 'Low Platelets', 'Anemia', 'Diarrhea', 'Constipation',
  'Loss of Appetite', 'Skin Changes', 'Fever', 'Chills', 'Allergic Reaction',
];

const emptyForm = () => ({
  condition_id: '',
  therapy_type: 'CHEMOTHERAPY',
  therapy_name: '',
  session_number: '',
  total_sessions_planned: '',
  scheduled_date: new Date().toISOString().split('T')[0],
  actual_start_time: '',
  actual_end_time: '',
  duration_minutes: '',
  status: 'completed',
  facility_name: '',
  attending_physician: '',
  attending_nurse: '',
  drugs_administered: '',
  dosage: '',
  route_of_administration: 'IV Infusion',
  // Vitals
  pre_systolic_bp: '', pre_diastolic_bp: '', pre_heart_rate: '', pre_temperature: '',
  post_systolic_bp: '', post_diastolic_bp: '', post_heart_rate: '', post_temperature: '',
  oxygen_saturation: '',
  // Outcomes
  side_effects: '',
  adverse_reactions: '',
  complications: '',
  patient_tolerance: '',
  clinical_notes: '',
  patient_notes: '',
});

/* ───────── helpers ───────── */
const fmtDate = (d) => d ? new Date(d).toLocaleDateString() : '—';
const fmtBP = (s, d) => s && d ? `${s}/${d}` : '—';
const fmtTime = (t) => {
  if (!t) return '—';
  if (typeof t === 'string' && t.includes(':')) return t.substring(0, 5);
  return t;
};
const statusColor = (s) => {
  switch (s) {
    case 'completed': return '#4caf50';
    case 'in_progress': return '#2196f3';
    case 'scheduled': return '#ff9800';
    case 'cancelled': return '#f44336';
    case 'missed': return '#9e9e9e';
    default: return '#666';
  }
};

/* ───────── styles ───────── */
const card = { background: '#fff', border: '1px solid #e0e0e0', borderRadius: 8, padding: 20, marginBottom: 16, boxShadow: '0 1px 3px rgba(0,0,0,.08)' };
const sectionHead = { margin: '24px 0 12px', fontSize: 15, fontWeight: 700, color: '#7b1fa2', textTransform: 'uppercase', letterSpacing: 1, borderBottom: '2px solid #7b1fa2', paddingBottom: 4 };
const grid2 = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 };
const grid3 = { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 };
const grid4 = { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 };
const inputStyle = { width: '100%', padding: '8px 10px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14 };
const labelStyle = { display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4, color: '#444' };
const btnPrimary = { padding: '10px 28px', background: '#7b1fa2', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 };
const btnSecondary = { padding: '10px 28px', background: '#eee', color: '#333', border: '1px solid #ccc', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 };
const btnDanger = { padding: '6px 16px', background: '#f44336', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12, fontWeight: 600 };
const tag = (color) => ({ display: 'inline-block', padding: '2px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600, color: '#fff', background: color });

/* ───────── Main Component ───────── */
export default function Chemotherapy() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('list');
  const [formData, setFormData] = useState(emptyForm());
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [selectedSideEffects, setSelectedSideEffects] = useState([]);
  const [conditions, setConditions] = useState([]);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/chronic/therapy-sessions', { params: { therapy_type: 'chemotherapy' } });
      setSessions(data);
    } catch (err) {
      console.error('Failed to load chemotherapy sessions', err);
    }
    setLoading(false);
  };

  const loadConditions = async () => {
    try {
      const { data } = await api.get('/chronic/conditions');
      setConditions(data);
    } catch (_) {}
  };

  useEffect(() => { loadSessions(); loadConditions(); }, []);

  const startEdit = (session) => {
    setFormData({
      ...emptyForm(),
      condition_id: session.condition_id || '',
      therapy_name: session.therapy_name || '',
      session_number: session.session_number || '',
      total_sessions_planned: session.total_sessions_planned || '',
      scheduled_date: session.scheduled_date?.split('T')[0] || '',
      actual_start_time: session.actual_start_time || '',
      actual_end_time: session.actual_end_time || '',
      duration_minutes: session.duration_minutes || '',
      status: session.status || 'completed',
      facility_name: session.facility_name || '',
      attending_physician: session.attending_physician || '',
      attending_nurse: session.attending_nurse || '',
      drugs_administered: session.drugs_administered || '',
      dosage: session.dosage || '',
      route_of_administration: session.route_of_administration || 'IV Infusion',
      pre_systolic_bp: session.pre_systolic_bp || '',
      pre_diastolic_bp: session.pre_diastolic_bp || '',
      pre_heart_rate: session.pre_heart_rate || '',
      pre_temperature: session.pre_temperature || '',
      post_systolic_bp: session.post_systolic_bp || '',
      post_diastolic_bp: session.post_diastolic_bp || '',
      post_heart_rate: session.post_heart_rate || '',
      post_temperature: session.post_temperature || '',
      oxygen_saturation: session.oxygen_saturation || '',
      side_effects: session.side_effects || '',
      adverse_reactions: session.adverse_reactions || '',
      complications: session.complications || '',
      patient_tolerance: session.patient_tolerance || '',
      clinical_notes: session.clinical_notes || '',
      patient_notes: session.patient_notes || '',
    });
    const effects = (session.side_effects || '').split(',').map(s => s.trim()).filter(Boolean);
    setSelectedSideEffects(effects);
    setEditing(session.id);
    setTab('form');
  };

  const submitForm = async () => {
    setSaving(true);
    const payload = {
      ...formData,
      therapy_type: 'CHEMOTHERAPY',
      side_effects: selectedSideEffects.join(', '),
      condition_id: formData.condition_id ? Number(formData.condition_id) : null,
      session_number: formData.session_number ? Number(formData.session_number) : null,
      total_sessions_planned: formData.total_sessions_planned ? Number(formData.total_sessions_planned) : null,
      duration_minutes: formData.duration_minutes ? Number(formData.duration_minutes) : null,
      pre_systolic_bp: formData.pre_systolic_bp ? Number(formData.pre_systolic_bp) : null,
      pre_diastolic_bp: formData.pre_diastolic_bp ? Number(formData.pre_diastolic_bp) : null,
      pre_heart_rate: formData.pre_heart_rate ? Number(formData.pre_heart_rate) : null,
      pre_temperature: formData.pre_temperature ? Number(formData.pre_temperature) : null,
      post_systolic_bp: formData.post_systolic_bp ? Number(formData.post_systolic_bp) : null,
      post_diastolic_bp: formData.post_diastolic_bp ? Number(formData.post_diastolic_bp) : null,
      post_heart_rate: formData.post_heart_rate ? Number(formData.post_heart_rate) : null,
      post_temperature: formData.post_temperature ? Number(formData.post_temperature) : null,
      oxygen_saturation: formData.oxygen_saturation ? Number(formData.oxygen_saturation) : null,
    };
    // Remove empty strings
    Object.keys(payload).forEach(k => { if (payload[k] === '') payload[k] = null; });
    try {
      if (editing) {
        await api.put(`/chronic/therapy-sessions/${editing}`, payload);
      } else {
        await api.post('/chronic/therapy-sessions', payload);
      }
      setFormData(emptyForm());
      setSelectedSideEffects([]);
      setEditing(null);
      setTab('list');
      loadSessions();
    } catch (err) {
      alert('Failed to save: ' + apiErrorMessage(err));
    }
    setSaving(false);
  };

  const deleteSession = async (id) => {
    if (!window.confirm('Delete this chemotherapy session?')) return;
    try {
      await api.delete(`/chronic/therapy-sessions/${id}`);
      loadSessions();
    } catch (err) {
      alert('Delete failed: ' + apiErrorMessage(err));
    }
  };

  const toggleSideEffect = (effect) => {
    setSelectedSideEffects(prev =>
      prev.includes(effect) ? prev.filter(e => e !== effect) : [...prev, effect]
    );
  };

  /* ───────── Summary Stats ───────── */
  const stats = useMemo(() => {
    const completed = sessions.filter(s => s.status === 'completed');
    return {
      total: sessions.length,
      completed: completed.length,
      scheduled: sessions.filter(s => s.status === 'scheduled').length,
      currentCycle: completed.length > 0 ? Math.max(...completed.map(s => s.session_number || 0)) : 0,
      totalPlanned: sessions.length > 0 ? (sessions[0].total_sessions_planned || '—') : '—',
    };
  }, [sessions]);

  /* ───────── field helper ───────── */
  const Field = ({ label, children, span }) => (
    <div style={span ? { gridColumn: `span ${span}` } : {}}>
      <label style={labelStyle}>{label}</label>
      {children}
    </div>
  );

  const Input = ({ name, type = 'text', placeholder, ...rest }) => (
    <input
      type={type}
      value={formData[name]}
      onChange={(e) => setFormData({ ...formData, [name]: e.target.value })}
      placeholder={placeholder}
      style={inputStyle}
      {...rest}
    />
  );

  const Select = ({ name, options, ...rest }) => (
    <select
      value={formData[name]}
      onChange={(e) => setFormData({ ...formData, [name]: e.target.value })}
      style={inputStyle}
      {...rest}
    >
      {options.map(o => typeof o === 'string'
        ? <option key={o} value={o}>{o}</option>
        : <option key={o.value} value={o.value}>{o.label}</option>
      )}
    </select>
  );

  /* ───────── RENDER ───────── */
  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div className="page-header">
          <div className="page-header-left">
            <BackButton />
            <h1 style={{ margin: 0, color: '#7b1fa2' }}>Chemotherapy</h1>
          </div>
        </div>
        <button
          style={btnPrimary}
          onClick={() => { setFormData(emptyForm()); setSelectedSideEffects([]); setEditing(null); setTab('form'); }}
        >
          + New Session
        </button>
      </div>

      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Total Sessions', value: stats.total, color: '#7b1fa2' },
          { label: 'Completed', value: stats.completed, color: '#4caf50' },
          { label: 'Scheduled', value: stats.scheduled, color: '#ff9800' },
          { label: 'Current / Planned', value: `${stats.currentCycle} / ${stats.totalPlanned}`, color: '#2196f3' },
        ].map(s => (
          <div key={s.label} style={{ ...card, textAlign: 'center', borderTop: `3px solid ${s.color}` }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {['list', 'form'].map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '8px 20px', borderRadius: 6, border: 'none', cursor: 'pointer', fontWeight: 600,
              background: tab === t ? '#7b1fa2' : '#f5f5f5',
              color: tab === t ? '#fff' : '#555',
            }}
          >
            {t === 'list' ? 'Session Reports' : editing ? 'Edit Session' : 'New Session'}
          </button>
        ))}
      </div>

      {/* ───── SESSION LIST ───── */}
      {tab === 'list' && (
        loading ? <p>Loading…</p> : sessions.length === 0 ? (
          <div style={{ ...card, textAlign: 'center', padding: 60 }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>💉</div>
            <h3>No Chemotherapy Sessions</h3>
            <p style={{ color: '#666' }}>Click "+ New Session" to log your first chemotherapy session.</p>
          </div>
        ) : (
          sessions.map(s => (
            <div key={s.id} style={card}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 16 }}>
                    {s.therapy_name || 'Chemotherapy'} — Session #{s.session_number || '—'}
                    {s.total_sessions_planned && <span style={{ color: '#888', fontWeight: 400 }}> / {s.total_sessions_planned}</span>}
                  </div>
                  <div style={{ color: '#666', fontSize: 13, marginTop: 4 }}>
                    {fmtDate(s.scheduled_date)} · {fmtTime(s.actual_start_time)} – {fmtTime(s.actual_end_time)}
                    {s.duration_minutes && ` (${s.duration_minutes} min)`}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={tag(statusColor(s.status))}>{s.status?.replace('_', ' ')}</span>
                  <button style={{ ...btnSecondary, padding: '4px 12px', fontSize: 12 }} onClick={() => startEdit(s)}>Edit</button>
                  <button style={{ ...btnDanger }} onClick={() => deleteSession(s.id)}>✕</button>
                </div>
              </div>

              <div style={{ ...grid3, marginTop: 16 }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12, color: '#888' }}>Drugs</div>
                  <div>{s.drugs_administered || '—'}</div>
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12, color: '#888' }}>Dosage</div>
                  <div>{s.dosage || '—'}</div>
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12, color: '#888' }}>Route</div>
                  <div>{s.route_of_administration || '—'}</div>
                </div>
              </div>

              {(s.pre_systolic_bp || s.post_systolic_bp) && (
                <div style={{ ...grid4, marginTop: 12, padding: '8px 12px', background: '#fafafa', borderRadius: 6 }}>
                  <div><span style={{ fontSize: 12, color: '#888' }}>Pre BP:</span> {fmtBP(s.pre_systolic_bp, s.pre_diastolic_bp)}</div>
                  <div><span style={{ fontSize: 12, color: '#888' }}>Post BP:</span> {fmtBP(s.post_systolic_bp, s.post_diastolic_bp)}</div>
                  <div><span style={{ fontSize: 12, color: '#888' }}>Pre HR:</span> {s.pre_heart_rate || '—'}</div>
                  <div><span style={{ fontSize: 12, color: '#888' }}>SpO₂:</span> {s.oxygen_saturation ? `${s.oxygen_saturation}%` : '—'}</div>
                </div>
              )}

              {(s.side_effects || s.adverse_reactions || s.patient_tolerance) && (
                <div style={{ marginTop: 12, padding: '8px 12px', background: '#fff3e0', borderRadius: 6 }}>
                  {s.patient_tolerance && <div><strong>Tolerance:</strong> {s.patient_tolerance}</div>}
                  {s.side_effects && <div style={{ marginTop: 4 }}><strong>Side Effects:</strong> {s.side_effects}</div>}
                  {s.adverse_reactions && <div style={{ marginTop: 4, color: '#d32f2f' }}><strong>Adverse Reactions:</strong> {s.adverse_reactions}</div>}
                </div>
              )}

              {(s.clinical_notes || s.patient_notes) && (
                <div style={{ marginTop: 8, fontSize: 13, color: '#555' }}>
                  {s.clinical_notes && <div><em>Clinical: {s.clinical_notes}</em></div>}
                  {s.patient_notes && <div><em>Patient: {s.patient_notes}</em></div>}
                </div>
              )}

              <div style={{ marginTop: 8, fontSize: 12, color: '#999' }}>
                {s.facility_name && <span>📍 {s.facility_name}</span>}
                {s.attending_physician && <span style={{ marginLeft: 16 }}>👨‍⚕️ {s.attending_physician}</span>}
              </div>
            </div>
          ))
        )
      )}

      {/* ───── SESSION FORM ───── */}
      {tab === 'form' && (
        <div style={card}>
          <h2 style={{ marginTop: 0, color: '#7b1fa2' }}>{editing ? 'Edit Session' : 'Log Chemotherapy Session'}</h2>

          {/* Regimen & Scheduling */}
          <div style={sectionHead}>Regimen & Scheduling</div>
          <div style={grid3}>
            <Field label="Protocol / Regimen Name">
              <Input name="therapy_name" placeholder="e.g., FOLFOX, R-CHOP, AC-T" />
            </Field>
            <Field label="Condition">
              <select value={formData.condition_id} onChange={e => setFormData({...formData, condition_id: e.target.value})} style={inputStyle}>
                <option value="">Select condition</option>
                {conditions.map(c => <option key={c.id} value={c.id}>{c.condition_name}</option>)}
              </select>
            </Field>
            <Field label="Status">
              <Select name="status" options={STATUS_OPTIONS.map(s => ({ value: s, label: s.replace('_', ' ') }))} />
            </Field>
          </div>
          <div style={{ ...grid4, marginTop: 12 }}>
            <Field label="Session #">
              <Input name="session_number" type="number" placeholder="1" />
            </Field>
            <Field label="Total Planned">
              <Input name="total_sessions_planned" type="number" placeholder="6" />
            </Field>
            <Field label="Date">
              <Input name="scheduled_date" type="date" />
            </Field>
            <Field label="Duration (min)">
              <Input name="duration_minutes" type="number" placeholder="120" />
            </Field>
          </div>
          <div style={{ ...grid2, marginTop: 12 }}>
            <Field label="Start Time">
              <Input name="actual_start_time" type="time" />
            </Field>
            <Field label="End Time">
              <Input name="actual_end_time" type="time" />
            </Field>
          </div>

          {/* Drugs & Administration */}
          <div style={sectionHead}>Drugs & Administration</div>
          <div style={grid2}>
            <Field label="Drugs Administered" span={2}>
              <Input name="drugs_administered" placeholder="e.g., Cisplatin 75mg/m², Etoposide 100mg/m²" />
            </Field>
          </div>
          <div style={{ ...grid2, marginTop: 12 }}>
            <Field label="Dosage">
              <Input name="dosage" placeholder="e.g., 75mg/m², 500mg" />
            </Field>
            <Field label="Route of Administration">
              <Select name="route_of_administration" options={ROUTES} />
            </Field>
          </div>

          {/* Vitals */}
          <div style={sectionHead}>Vital Signs</div>
          <div style={grid4}>
            <Field label="Pre Systolic">
              <Input name="pre_systolic_bp" type="number" placeholder="120" />
            </Field>
            <Field label="Pre Diastolic">
              <Input name="pre_diastolic_bp" type="number" placeholder="80" />
            </Field>
            <Field label="Pre Heart Rate">
              <Input name="pre_heart_rate" type="number" placeholder="72" />
            </Field>
            <Field label="Pre Temp (°F)">
              <Input name="pre_temperature" type="number" step="0.1" placeholder="98.6" />
            </Field>
          </div>
          <div style={{ ...grid4, marginTop: 12 }}>
            <Field label="Post Systolic">
              <Input name="post_systolic_bp" type="number" placeholder="120" />
            </Field>
            <Field label="Post Diastolic">
              <Input name="post_diastolic_bp" type="number" placeholder="80" />
            </Field>
            <Field label="Post Heart Rate">
              <Input name="post_heart_rate" type="number" placeholder="72" />
            </Field>
            <Field label="Post Temp (°F)">
              <Input name="post_temperature" type="number" step="0.1" placeholder="98.6" />
            </Field>
          </div>
          <div style={{ marginTop: 12 }}>
            <Field label="SpO₂ (%)">
              <Input name="oxygen_saturation" type="number" placeholder="98" style={{ ...inputStyle, maxWidth: 200 }} />
            </Field>
          </div>

          {/* Side Effects */}
          <div style={sectionHead}>Side Effects & Tolerance</div>
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Common Side Effects (click to toggle)</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {COMMON_SIDE_EFFECTS.map(effect => (
                <button
                  key={effect}
                  type="button"
                  onClick={() => toggleSideEffect(effect)}
                  style={{
                    padding: '4px 12px', borderRadius: 16, border: '1px solid #ccc', cursor: 'pointer', fontSize: 13,
                    background: selectedSideEffects.includes(effect) ? '#7b1fa2' : '#fff',
                    color: selectedSideEffects.includes(effect) ? '#fff' : '#555',
                  }}
                >
                  {effect}
                </button>
              ))}
            </div>
          </div>
          <div style={grid2}>
            <Field label="Patient Tolerance">
              <Select name="patient_tolerance" options={[{ value: '', label: 'Select...' }, ...TOLERANCE_OPTIONS.map(t => ({ value: t, label: t }))]} />
            </Field>
            <Field label="Adverse Reactions">
              <Input name="adverse_reactions" placeholder="Any severe / unexpected reactions" />
            </Field>
          </div>
          <div style={{ marginTop: 12 }}>
            <Field label="Complications">
              <Input name="complications" placeholder="e.g., Extravasation, infusion reaction" />
            </Field>
          </div>

          {/* Facility & Staff */}
          <div style={sectionHead}>Facility & Staff</div>
          <div style={grid3}>
            <Field label="Facility">
              <Input name="facility_name" placeholder="Infusion center / hospital" />
            </Field>
            <Field label="Physician">
              <Input name="attending_physician" placeholder="Dr. name" />
            </Field>
            <Field label="Nurse">
              <Input name="attending_nurse" placeholder="Nurse name" />
            </Field>
          </div>

          {/* Notes */}
          <div style={sectionHead}>Notes</div>
          <div style={grid2}>
            <Field label="Clinical Notes">
              <textarea
                value={formData.clinical_notes}
                onChange={e => setFormData({ ...formData, clinical_notes: e.target.value })}
                style={{ ...inputStyle, minHeight: 80 }}
                placeholder="Clinical observations, lab values, pre-medication given..."
              />
            </Field>
            <Field label="Patient Notes">
              <textarea
                value={formData.patient_notes}
                onChange={e => setFormData({ ...formData, patient_notes: e.target.value })}
                style={{ ...inputStyle, minHeight: 80 }}
                placeholder="How you felt, symptoms, concerns..."
              />
            </Field>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 24 }}>
            <button style={btnSecondary} onClick={() => { setTab('list'); setEditing(null); setFormData(emptyForm()); setSelectedSideEffects([]); }}>
              Cancel
            </button>
            <button style={btnPrimary} onClick={submitForm} disabled={saving}>
              {saving ? 'Saving…' : editing ? 'Update Session' : 'Save Session'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
