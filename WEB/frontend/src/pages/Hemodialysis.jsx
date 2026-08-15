import { localToday } from '../utils/datetime';
import React, { useState, useEffect, useMemo } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import api from '../services/api';
import BackButton from '../components/BackButton';
import { useTempUnit } from '../hooks/useTempUnit';

/* ───────── constants ───────── */
const ACCESS_TYPES = ['AV Fistula', 'AV Graft', 'Central Catheter', 'Buttonhole'];
const NEEDLE_GAUGES = ['15G', '16G', '17G'];
const DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

const emptyReading = () => ({
  reading_time: '', systolic_bp: '', diastolic_bp: '', pulse: '',
  mean_arterial_pressure: '', dialysate_rate: '', dialysate_volume_remaining: '',
  uf_rate: '', uf_volume_removed: '', blood_flow_rate: '',
  arterial_pressure: '', venous_pressure: '', effluent_pressure: '',
  access_state: '', saline_amount: '', remarks: '',
});

const emptyForm = () => ({
  // Resolved from the patient's own chronic conditions at load — see
  // loadCondition(). It was hardcoded to 14, an id that exists for nobody, so
  // the API's ownership check rejected every save with "Chronic condition not
  // found". null is valid: the endpoint only verifies the id when one is sent.
  condition_id: null,
  therapy_type: 'HEMODIALYSIS',
  scheduled_date: localToday(),
  status: 'COMPLETED',
  facility_name: '',
  attending_physician: '',
  attending_nurse: '',
  rn_reviewer: '',
  day_of_week: DAYS_OF_WEEK[new Date().getDay() === 0 ? 6 : new Date().getDay() - 1],
  dialysis_access_type: 'AV Fistula',
  // Weights
  dry_weight_kg: '',
  previous_post_weight_kg: '',
  pre_dialysis_weight_kg: '',
  post_dialysis_weight_kg: '',
  fluid_removed_ml: '',
  fluid_to_remove_kg: '',
  // Vitals
  pre_systolic_bp: '', pre_diastolic_bp: '', pre_heart_rate: '', pre_temperature: '',
  post_systolic_bp: '', post_diastolic_bp: '', post_heart_rate: '', post_temperature: '',
  pre_standing_systolic_bp: '', pre_standing_diastolic_bp: '', pre_standing_heart_rate: '',
  post_standing_systolic_bp: '', post_standing_diastolic_bp: '', post_standing_heart_rate: '',
  // Treatment
  blood_flow_rate: '', dialysate_flow_rate: '', duration_minutes: '',
  actual_start_time: '', actual_end_time: '',
  // Dialysate
  dialysate_volume_liters: '', dialysate_lactate_meq: '', dialysate_potassium_meq: '',
  sak_number: '', needle_gauge: '15G', needle_length: '', buttonhole_technique: false,
  // Equipment
  cartridge_lot: '', sak_lot: '', cycler_number: '', warmer_serial: '', control_panel_serial: '',
  // Pre-treatment symptoms
  pre_shortness_of_breath: false, pre_swelling: false, pre_change_in_mobility: false,
  pre_digestion_problems: false, pre_hosp_er_since_last: false,
  // Access assessment
  access_thrill_bruit: true, access_redness_drainage: false,
  // Post-treatment
  total_dialysate_liters: '', total_uf_liters: '', total_blood_volume_processed: '',
  dialyzer_appearance: '', post_bleeding_stop_time: '',
  post_bruising: false, post_infiltration: false, post_shortness_of_breath: false,
  post_swelling: false, post_digestion_problems: false, post_access_thrill_bruit: true,
  // Maintenance
  purification_pak_change: false, air_filter_cleaned: false,
  waste_line_bleach_disinfection: false, sak_use_number: '',
  total_chloramine_level: '', alarm_test_completed: false,
  // Labs & Notes
  lab_tubes_drawn: '', oxygen_saturation: '',
  side_effects: '', clinical_notes: '', patient_notes: '',
});

/* ───────── helpers ───────── */
const fmtDate = (d) => d ? new Date(d).toLocaleDateString() : '—';
const fmtWeight = (w) => w != null ? `${w} kg` : '—';
const fmtBP = (s, d) => s && d ? `${s}/${d}` : '—';
const fmtTime = (t) => {
  if (!t) return '—';
  if (typeof t === 'string' && t.includes(':')) return t.substring(0, 5);
  return t;
};

/* ───────── styles ───────── */
const card = { background: '#fff', border: '1px solid #e0e0e0', borderRadius: 8, padding: 20, marginBottom: 16, boxShadow: '0 1px 3px rgba(0,0,0,.08)' };
const sectionHead = { margin: '24px 0 12px', fontSize: 15, fontWeight: 700, color: '#1565c0', textTransform: 'uppercase', letterSpacing: 1, borderBottom: '2px solid #1565c0', paddingBottom: 4 };
const grid2 = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 };
const grid3 = { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 };
const grid4 = { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 };
const label = { display: 'block', fontSize: 12, fontWeight: 600, color: '#555', marginBottom: 3 };
const input = { width: '100%', padding: '7px 10px', borderRadius: 4, border: '1px solid #ccc', fontSize: 14, boxSizing: 'border-box' };
const btnPrimary = { padding: '10px 24px', background: '#1565c0', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 15, fontWeight: 600 };
const btnSecondary = { padding: '10px 24px', background: '#757575', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 15 };
const btnDanger = { padding: '6px 14px', background: '#d32f2f', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 13 };
const tabActive = { padding: '10px 24px', background: '#1565c0', color: '#fff', border: 'none', borderRadius: '6px 6px 0 0', cursor: 'pointer', fontSize: 15, fontWeight: 600 };
const tabInactive = { padding: '10px 24px', background: '#e0e0e0', color: '#333', border: 'none', borderRadius: '6px 6px 0 0', cursor: 'pointer', fontSize: 15 };

const Checkbox = ({ checked, onChange, label: lbl }) => (
  <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 14, cursor: 'pointer' }}>
    <input type="checkbox" checked={checked || false} onChange={onChange} />
    {lbl}
  </label>
);

const Field = ({ lbl, children }) => (
  <div><label style={label}>{lbl}</label>{children}</div>
);

const Input = ({ lbl, value, onChange, type = 'text', step, placeholder, ...rest }) => (
  <Field lbl={lbl}>
    <input type={type} value={value || ''} onChange={onChange} style={input} step={step} placeholder={placeholder} {...rest} />
  </Field>
);

/* ================================================================== */
export default function Hemodialysis() {
  const [tab, setTab] = useState('reports'); // 'reports' | 'form'
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [formData, setFormData] = useState(emptyForm());
  const [readings, setReadings] = useState([]);
  const [editing, setEditing] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState({ days: 90, page: 0, perPage: 20 });
  const temp = useTempUnit();

  // Temperature inputs hold the value in the chosen unit; storage is Celsius.
  function handleTempToggle() {
    setFormData((f) => ({
      ...f,
      pre_temperature: f.pre_temperature ? temp.convertInPlace(f.pre_temperature) : f.pre_temperature,
      post_temperature: f.post_temperature ? temp.convertInPlace(f.post_temperature) : f.post_temperature,
    }));
    temp.toggle();
  }
  const [summary, setSummary] = useState(null);
  const [conditionId, setConditionId] = useState(null);
  // A failed load is NOT "no sessions". Swallowing the error into an empty list
  // is how a 500 on this endpoint rendered as "No hemodialysis sessions found
  // for this period" to a patient with 730 sessions.
  const [loadError, setLoadError] = useState(null);

  useEffect(() => { loadSessions(); loadSummary(); }, [filter.days]);
  useEffect(() => { loadCondition(); }, []);

  /* Attach sessions to THIS patient's renal condition. A hardcoded id belongs
     to no one, and the API rejects an id the user does not own. */
  const loadCondition = async () => {
    try {
      const { data } = await api.get('/chronic/conditions', { params: { is_active: true } });
      const renal = data.find(c => (c.category || '').toLowerCase() === 'renal')
                 || data.find(c => /renal|kidney|esrd|dialysis/i.test(c.condition_name || ''));
      if (renal) {
        setConditionId(renal.id);
        setFormData(prev => ({ ...prev, condition_id: renal.id }));
      }
    } catch (e) {
      // Leave it null — a session without a condition still saves.
      console.error(e);
    }
  };

  /* ── API calls ── */
  const loadSessions = async () => {
    setLoading(true);
    try {
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - filter.days);
      const res = await api.get('/chronic/therapy-sessions', {
        params: { therapy_type: 'HEMODIALYSIS', start_date: cutoff.toISOString(), limit: 500 }
      });
      setSessions(res.data);
      setLoadError(null);
    } catch (e) {
      console.error(e);
      setSessions([]);
      setLoadError(
        e.response?.data?.detail
        || 'Could not load your sessions. This is an error, not an empty record — please retry.'
      );
    }
    setLoading(false);
  };

  const loadSummary = async () => {
    try {
      const res = await api.get('/chronic/hd-summary', { params: { days: filter.days } });
      setSummary(res.data);
    } catch (e) { console.error(e); }
  };

  const set = (field) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setFormData(prev => {
      const next = { ...prev, [field]: val };
      // Auto-calc fluid to remove
      if (['pre_dialysis_weight_kg', 'dry_weight_kg'].includes(field) && next.pre_dialysis_weight_kg && next.dry_weight_kg) {
        next.fluid_to_remove_kg = (parseFloat(next.pre_dialysis_weight_kg) - parseFloat(next.dry_weight_kg)).toFixed(1);
      }
      // Auto-calc fluid removed
      if (['pre_dialysis_weight_kg', 'post_dialysis_weight_kg'].includes(field) && next.pre_dialysis_weight_kg && next.post_dialysis_weight_kg) {
        next.fluid_removed_ml = ((parseFloat(next.pre_dialysis_weight_kg) - parseFloat(next.post_dialysis_weight_kg)) * 1000).toFixed(0);
      }
      return next;
    });
  };

  const setReading = (idx, field) => (e) => {
    setReadings(prev => {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], [field]: e.target.value };
      // Auto-calc MAP
      if (['systolic_bp', 'diastolic_bp'].includes(field)) {
        const s = parseFloat(updated[idx].systolic_bp);
        const d = parseFloat(updated[idx].diastolic_bp);
        if (s && d) updated[idx].mean_arterial_pressure = Math.round(d + (s - d) / 3);
      }
      return updated;
    });
  };

  const addReading = () => setReadings(prev => [...prev, emptyReading()]);
  const removeReading = (idx) => setReadings(prev => prev.filter((_, i) => i !== idx));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...formData };
      // Build scheduled_date as datetime
      if (payload.scheduled_date && !payload.scheduled_date.includes('T')) {
        payload.scheduled_date = payload.scheduled_date + 'T00:00:00';
      }
      // Convert empties to null, numbers to numbers
      Object.keys(payload).forEach(k => {
        if (payload[k] === '') payload[k] = null;
        if (typeof payload[k] === 'string' && /^\d+\.?\d*$/.test(payload[k])) {
          if (['facility_name', 'attending_physician', 'attending_nurse', 'rn_reviewer',
               'dialysis_access_type', 'day_of_week', 'needle_gauge', 'cartridge_lot',
               'sak_lot', 'cycler_number', 'warmer_serial', 'control_panel_serial',
               'dialyzer_appearance', 'post_bleeding_stop_time', 'lab_tubes_drawn',
               'side_effects', 'clinical_notes', 'patient_notes', 'therapy_type',
               'status', 'filtration_fraction', 'scheduled_date', 'actual_start_time',
               'actual_end_time'].includes(k)) return;
          payload[k] = parseFloat(payload[k]);
        }
      });
      // Convert int fields
      ['pre_systolic_bp', 'pre_diastolic_bp', 'post_systolic_bp', 'post_diastolic_bp',
       'pre_heart_rate', 'post_heart_rate', 'pre_standing_systolic_bp', 'pre_standing_diastolic_bp',
       'pre_standing_heart_rate', 'post_standing_systolic_bp', 'post_standing_diastolic_bp',
       'post_standing_heart_rate', 'duration_minutes', 'sak_number', 'sak_use_number',
       'oxygen_saturation'].forEach(k => {
        if (payload[k] != null) payload[k] = parseInt(payload[k]);
      });
      // Temperature is entered in the chosen unit; persist canonical Celsius.
      ['pre_temperature', 'post_temperature'].forEach(k => {
        if (payload[k] != null) payload[k] = temp.toCelsius(payload[k]);
      });

      // Clinical notes are their own append-only rows, NOT a field on the
      // session — the model maps `clinical_notes` to a relationship, so sending
      // it here 500'd every submission. Pull it out and post it below.
      const clinicalNote = (payload.clinical_notes || '').trim();
      delete payload.clinical_notes;

      let sessionId;
      if (editing) {
        await api.put(`/chronic/therapy-sessions/${editing.id}`, payload);
        sessionId = editing.id;
      } else {
        const res = await api.post('/chronic/therapy-sessions', payload);
        sessionId = res.data.id;
      }

      if (clinicalNote) {
        await api.post(`/chronic/therapy-sessions/${sessionId}/notes`, {
          note_type: 'clinical',
          note_text: clinicalNote,
        });
      }

      // Save readings
      for (const r of readings) {
        if (!r.reading_time) continue;
        const readingPayload = { ...r, session_id: sessionId };
        Object.keys(readingPayload).forEach(k => {
          if (readingPayload[k] === '') readingPayload[k] = null;
          if (readingPayload[k] && typeof readingPayload[k] === 'string' && /^\d+\.?\d*$/.test(readingPayload[k])) {
            if (['reading_time', 'access_state', 'saline_amount', 'remarks'].includes(k)) return;
            readingPayload[k] = parseFloat(readingPayload[k]);
          }
        });
        ['systolic_bp', 'diastolic_bp', 'pulse', 'reading_number'].forEach(k => {
          if (readingPayload[k] != null) readingPayload[k] = parseInt(readingPayload[k]);
        });
        await api.post(`/chronic/therapy-sessions/${sessionId}/readings`, readingPayload);
      }

      setTab('reports');
      setEditing(null);
      setFormData({ ...emptyForm(), condition_id: conditionId });
      setReadings([]);
      loadSessions();
      loadSummary();
    } catch (err) {
      console.error(err);
      alert('Failed to save session: ' + apiErrorMessage(err));
    }
    setSaving(false);
  };

  const startEdit = (session) => {
    const f = emptyForm();
    Object.keys(f).forEach(k => {
      if (session[k] != null) f[k] = session[k];
    });
    if (session.scheduled_date) f.scheduled_date = session.scheduled_date.split('T')[0];
    // Stored temperatures are Celsius; show them in the chosen unit while editing.
    if (session.pre_temperature != null) f.pre_temperature = temp.fromCelsius(session.pre_temperature);
    if (session.post_temperature != null) f.post_temperature = temp.fromCelsius(session.post_temperature);
    setFormData(f);
    setReadings((session.intradialytic_readings || []).map(r => ({
      ...r,
      reading_time: fmtTime(r.reading_time),
    })));
    setEditing(session);
    setTab('form');
  };

  const startNew = () => {
    setEditing(null);
    setFormData({ ...emptyForm(), condition_id: conditionId });
    setReadings([emptyReading()]);
    setTab('form');
  };

  /* ── Pagination ── */
  const paged = useMemo(() => {
    const start = filter.page * filter.perPage;
    return sessions.slice(start, start + filter.perPage);
  }, [sessions, filter.page, filter.perPage]);
  const totalPages = Math.ceil(sessions.length / filter.perPage);

  /* ================================================================== */
  /* ── FORM TAB ── */
  const renderForm = () => (
    <form onSubmit={handleSubmit}>
      {/* ──── SESSION INFO ──── */}
      <div style={sectionHead}>Session Information</div>
      <div style={grid4}>
        <Input lbl="Date *" value={formData.scheduled_date} onChange={set('scheduled_date')} type="date" required />
        <Field lbl="Day of Week">
          <select value={formData.day_of_week || ''} onChange={set('day_of_week')} style={input}>
            <option value="">—</option>
            {DAYS_OF_WEEK.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </Field>
        <Field lbl="Status">
          <select value={formData.status} onChange={set('status')} style={input}>
            <option value="SCHEDULED">Scheduled</option>
            <option value="IN_PROGRESS">In Progress</option>
            <option value="COMPLETED">Completed</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </Field>
        <Input lbl="Duration (min)" value={formData.duration_minutes} onChange={set('duration_minutes')} type="number" />
      </div>
      <div style={{ ...grid3, marginTop: 12 }}>
        <Input lbl="Facility" value={formData.facility_name} onChange={set('facility_name')} />
        <Input lbl="Physician" value={formData.attending_physician} onChange={set('attending_physician')} />
        <Input lbl="RN / Reviewer" value={formData.rn_reviewer} onChange={set('rn_reviewer')} />
      </div>

      {/* ──── ACCESS & WEIGHTS ──── */}
      <div style={sectionHead}>Vascular Access & Weights</div>
      <div style={grid4}>
        <Field lbl="Access Type">
          <select value={formData.dialysis_access_type || ''} onChange={set('dialysis_access_type')} style={input}>
            {ACCESS_TYPES.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </Field>
        <Field lbl="Needle Gauge">
          <select value={formData.needle_gauge || ''} onChange={set('needle_gauge')} style={input}>
            {NEEDLE_GAUGES.map(g => <option key={g} value={g}>{g}</option>)}
          </select>
        </Field>
        <Input lbl="Needle Length (mm)" value={formData.needle_length} onChange={set('needle_length')} type="number" step="0.1" />
        <Checkbox checked={formData.buttonhole_technique} onChange={set('buttonhole_technique')} label="Buttonhole" />
      </div>
      <div style={{ ...grid4, marginTop: 12 }}>
        <Input lbl="Dry Weight (kg)" value={formData.dry_weight_kg} onChange={set('dry_weight_kg')} type="number" step="0.1" />
        <Input lbl="Prev Post Weight (kg)" value={formData.previous_post_weight_kg} onChange={set('previous_post_weight_kg')} type="number" step="0.1" />
        <Input lbl="Pre Weight (kg) *" value={formData.pre_dialysis_weight_kg} onChange={set('pre_dialysis_weight_kg')} type="number" step="0.1" />
        <Input lbl="Post Weight (kg)" value={formData.post_dialysis_weight_kg} onChange={set('post_dialysis_weight_kg')} type="number" step="0.1" />
      </div>
      <div style={{ ...grid2, marginTop: 12 }}>
        <Input lbl="Fluid to Remove (kg)" value={formData.fluid_to_remove_kg} onChange={set('fluid_to_remove_kg')} type="number" step="0.1" />
        <Input lbl="Fluid Removed (mL)" value={formData.fluid_removed_ml} onChange={set('fluid_removed_ml')} type="number" />
      </div>

      {/* ──── PRE-TREATMENT VITALS ──── */}
      <div style={{ ...sectionHead, display: 'flex', alignItems: 'center', gap: 10 }}>
        Pre-Treatment Vitals
        <button type="button" onClick={handleTempToggle}
          style={{ fontSize: '.7rem', padding: '1px 8px', borderRadius: 10, border: '1px solid var(--primary)', background: 'transparent', color: 'var(--primary)', cursor: 'pointer' }}
          title="Toggle temperature unit (stored in °C)">temp: {temp.label}</button>
      </div>
      <div style={grid4}>
        <Input lbl="Sitting BP Sys" value={formData.pre_systolic_bp} onChange={set('pre_systolic_bp')} type="number" placeholder="mmHg" />
        <Input lbl="Sitting BP Dia" value={formData.pre_diastolic_bp} onChange={set('pre_diastolic_bp')} type="number" placeholder="mmHg" />
        <Input lbl="Heart Rate" value={formData.pre_heart_rate} onChange={set('pre_heart_rate')} type="number" placeholder="bpm" />
        <Input lbl={`Temperature (${temp.label})`} value={formData.pre_temperature} onChange={set('pre_temperature')} type="number" step="0.1" />
      </div>
      <div style={{ ...grid3, marginTop: 12 }}>
        <Input lbl="Standing BP Sys" value={formData.pre_standing_systolic_bp} onChange={set('pre_standing_systolic_bp')} type="number" />
        <Input lbl="Standing BP Dia" value={formData.pre_standing_diastolic_bp} onChange={set('pre_standing_diastolic_bp')} type="number" />
        <Input lbl="Standing HR" value={formData.pre_standing_heart_rate} onChange={set('pre_standing_heart_rate')} type="number" />
      </div>

      {/* ──── PRE-TREATMENT SYMPTOM CHECKLIST ──── */}
      <div style={sectionHead}>Pre-Treatment Assessment</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>
        <Checkbox checked={formData.pre_shortness_of_breath} onChange={set('pre_shortness_of_breath')} label="Shortness of Breath" />
        <Checkbox checked={formData.pre_swelling} onChange={set('pre_swelling')} label="Swelling / Edema" />
        <Checkbox checked={formData.pre_change_in_mobility} onChange={set('pre_change_in_mobility')} label="Change in Mobility" />
        <Checkbox checked={formData.pre_digestion_problems} onChange={set('pre_digestion_problems')} label="Digestion Problems" />
        <Checkbox checked={formData.pre_hosp_er_since_last} onChange={set('pre_hosp_er_since_last')} label="Hospital/ER Since Last" />
        <Checkbox checked={formData.access_thrill_bruit} onChange={set('access_thrill_bruit')} label="Access Thrill/Bruit ✓" />
        <Checkbox checked={formData.access_redness_drainage} onChange={set('access_redness_drainage')} label="Access Redness/Drainage" />
      </div>

      {/* ──── DIALYSATE PRESCRIPTION ──── */}
      <div style={sectionHead}>Dialysate Prescription</div>
      <div style={grid4}>
        <Input lbl="Blood Flow (mL/min)" value={formData.blood_flow_rate} onChange={set('blood_flow_rate')} type="number" />
        <Input lbl="Dialysate Flow (mL/min)" value={formData.dialysate_flow_rate} onChange={set('dialysate_flow_rate')} type="number" />
        <Input lbl="Dialysate Volume (L)" value={formData.dialysate_volume_liters} onChange={set('dialysate_volume_liters')} type="number" step="0.1" />
        <Input lbl="SAK #" value={formData.sak_number} onChange={set('sak_number')} type="number" />
      </div>
      <div style={{ ...grid3, marginTop: 12 }}>
        <Input lbl="Lactate (mEq)" value={formData.dialysate_lactate_meq} onChange={set('dialysate_lactate_meq')} type="number" step="0.1" />
        <Input lbl="Potassium (mEq)" value={formData.dialysate_potassium_meq} onChange={set('dialysate_potassium_meq')} type="number" step="0.1" />
        <Input lbl="O₂ Saturation (%)" value={formData.oxygen_saturation} onChange={set('oxygen_saturation')} type="number" />
      </div>

      {/* ──── EQUIPMENT ──── */}
      <div style={sectionHead}>Equipment Tracking</div>
      <div style={grid4}>
        <Input lbl="Cartridge Lot" value={formData.cartridge_lot} onChange={set('cartridge_lot')} />
        <Input lbl="SAK Lot" value={formData.sak_lot} onChange={set('sak_lot')} />
        <Input lbl="Cycler #" value={formData.cycler_number} onChange={set('cycler_number')} />
        <Input lbl="Warmer Serial" value={formData.warmer_serial} onChange={set('warmer_serial')} />
      </div>

      {/* ──── INTRADIALYTIC READINGS ──── */}
      <div style={sectionHead}>
        Intradialytic Readings
        <button type="button" onClick={addReading} style={{ ...btnPrimary, fontSize: 12, padding: '4px 14px', marginLeft: 16 }}>+ Add Reading</button>
      </div>
      {readings.length === 0 && <p style={{ color: '#888', fontSize: 14 }}>No readings yet. Click "+ Add Reading" to log vitals during treatment.</p>}
      {readings.map((r, idx) => (
        <div key={idx} style={{ background: '#f9f9f9', border: '1px solid #e0e0e0', borderRadius: 6, padding: 14, marginBottom: 10, position: 'relative' }}>
          <div style={{ position: 'absolute', top: 8, right: 8 }}>
            <button type="button" onClick={() => removeReading(idx)} style={{ ...btnDanger, fontSize: 11, padding: '3px 10px' }}>✕</button>
          </div>
          <div style={{ fontWeight: 600, fontSize: 13, color: '#1565c0', marginBottom: 8 }}>Reading #{idx + 1}</div>
          <div style={grid4}>
            <Input lbl="Time (HH:MM)" value={r.reading_time} onChange={setReading(idx, 'reading_time')} placeholder="14:30" />
            <Input lbl="BP Sys" value={r.systolic_bp} onChange={setReading(idx, 'systolic_bp')} type="number" />
            <Input lbl="BP Dia" value={r.diastolic_bp} onChange={setReading(idx, 'diastolic_bp')} type="number" />
            <Input lbl="Pulse" value={r.pulse} onChange={setReading(idx, 'pulse')} type="number" />
          </div>
          <div style={{ ...grid4, marginTop: 8 }}>
            <Input lbl="MAP" value={r.mean_arterial_pressure} onChange={setReading(idx, 'mean_arterial_pressure')} type="number" />
            <Input lbl="Blood Flow" value={r.blood_flow_rate} onChange={setReading(idx, 'blood_flow_rate')} type="number" />
            <Input lbl="Dialysate Rate" value={r.dialysate_rate} onChange={setReading(idx, 'dialysate_rate')} type="number" />
            <Input lbl="UF Rate" value={r.uf_rate} onChange={setReading(idx, 'uf_rate')} type="number" />
          </div>
          <div style={{ ...grid4, marginTop: 8 }}>
            <Input lbl="UF Removed" value={r.uf_volume_removed} onChange={setReading(idx, 'uf_volume_removed')} type="number" />
            <Input lbl="Arterial P" value={r.arterial_pressure} onChange={setReading(idx, 'arterial_pressure')} type="number" />
            <Input lbl="Venous P" value={r.venous_pressure} onChange={setReading(idx, 'venous_pressure')} type="number" />
            <Input lbl="Effluent P" value={r.effluent_pressure} onChange={setReading(idx, 'effluent_pressure')} type="number" />
          </div>
          <div style={{ ...grid2, marginTop: 8 }}>
            <Input lbl="Saline" value={r.saline_amount} onChange={setReading(idx, 'saline_amount')} />
            <Input lbl="Remarks" value={r.remarks} onChange={setReading(idx, 'remarks')} />
          </div>
        </div>
      ))}

      {/* ──── POST-TREATMENT ──── */}
      <div style={sectionHead}>Post-Treatment Vitals</div>
      <div style={grid4}>
        <Input lbl="Sitting BP Sys" value={formData.post_systolic_bp} onChange={set('post_systolic_bp')} type="number" placeholder="mmHg" />
        <Input lbl="Sitting BP Dia" value={formData.post_diastolic_bp} onChange={set('post_diastolic_bp')} type="number" placeholder="mmHg" />
        <Input lbl="Heart Rate" value={formData.post_heart_rate} onChange={set('post_heart_rate')} type="number" />
        <Input lbl={`Temperature (${temp.label})`} value={formData.post_temperature} onChange={set('post_temperature')} type="number" step="0.1" />
      </div>
      <div style={{ ...grid3, marginTop: 12 }}>
        <Input lbl="Standing BP Sys" value={formData.post_standing_systolic_bp} onChange={set('post_standing_systolic_bp')} type="number" />
        <Input lbl="Standing BP Dia" value={formData.post_standing_diastolic_bp} onChange={set('post_standing_diastolic_bp')} type="number" />
        <Input lbl="Standing HR" value={formData.post_standing_heart_rate} onChange={set('post_standing_heart_rate')} type="number" />
      </div>

      <div style={sectionHead}>Post-Treatment Totals & Assessment</div>
      <div style={grid4}>
        <Input lbl="Total Dialysate (L)" value={formData.total_dialysate_liters} onChange={set('total_dialysate_liters')} type="number" step="0.1" />
        <Input lbl="Total UF (L)" value={formData.total_uf_liters} onChange={set('total_uf_liters')} type="number" step="0.1" />
        <Input lbl="Blood Vol Processed (L)" value={formData.total_blood_volume_processed} onChange={set('total_blood_volume_processed')} type="number" step="0.1" />
        <Input lbl="Dialyzer Appearance" value={formData.dialyzer_appearance} onChange={set('dialyzer_appearance')} />
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginTop: 14 }}>
        <Input lbl="Bleeding Stop Time" value={formData.post_bleeding_stop_time} onChange={set('post_bleeding_stop_time')} />
        <Checkbox checked={formData.post_bruising} onChange={set('post_bruising')} label="Bruising" />
        <Checkbox checked={formData.post_infiltration} onChange={set('post_infiltration')} label="Infiltration" />
        <Checkbox checked={formData.post_shortness_of_breath} onChange={set('post_shortness_of_breath')} label="SOB" />
        <Checkbox checked={formData.post_swelling} onChange={set('post_swelling')} label="Swelling" />
        <Checkbox checked={formData.post_digestion_problems} onChange={set('post_digestion_problems')} label="GI Issues" />
        <Checkbox checked={formData.post_access_thrill_bruit} onChange={set('post_access_thrill_bruit')} label="Access Thrill/Bruit ✓" />
      </div>

      {/* ──── MACHINE MAINTENANCE ──── */}
      <div style={sectionHead}>Machine Maintenance</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>
        <Checkbox checked={formData.purification_pak_change} onChange={set('purification_pak_change')} label="Purification Pak Change" />
        <Checkbox checked={formData.air_filter_cleaned} onChange={set('air_filter_cleaned')} label="Air Filter Cleaned" />
        <Checkbox checked={formData.waste_line_bleach_disinfection} onChange={set('waste_line_bleach_disinfection')} label="Waste Line Bleach" />
        <Checkbox checked={formData.alarm_test_completed} onChange={set('alarm_test_completed')} label="Alarm Test Complete" />
      </div>
      <div style={{ ...grid3, marginTop: 12 }}>
        <Input lbl="SAK Use #" value={formData.sak_use_number} onChange={set('sak_use_number')} type="number" />
        <Input lbl="Total Chloramine (ppm)" value={formData.total_chloramine_level} onChange={set('total_chloramine_level')} type="number" step="0.01" />
        <Input lbl="Lab Tubes Drawn" value={formData.lab_tubes_drawn} onChange={set('lab_tubes_drawn')} placeholder="e.g., EDTA, SST" />
      </div>

      {/* ──── NOTES ──── */}
      <div style={sectionHead}>Notes</div>
      <div style={grid2}>
        <Field lbl="Side Effects">
          <textarea value={formData.side_effects || ''} onChange={set('side_effects')} style={{ ...input, minHeight: 60 }} placeholder="Cramping, nausea, dizziness..." />
        </Field>
        <Field lbl="Clinical Notes">
          <textarea value={formData.clinical_notes || ''} onChange={set('clinical_notes')} style={{ ...input, minHeight: 60 }} />
        </Field>
      </div>
      <div style={{ marginTop: 12 }}>
        <Field lbl="Patient Notes">
          <textarea value={formData.patient_notes || ''} onChange={set('patient_notes')} style={{ ...input, minHeight: 60 }} placeholder="How did you feel during/after treatment?" />
        </Field>
      </div>

      {/* ──── SUBMIT ──── */}
      <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
        <button type="submit" style={btnPrimary} disabled={saving}>
          {saving ? 'Saving...' : editing ? 'Update Session' : 'Save Session'}
        </button>
        <button type="button" style={btnSecondary} onClick={() => { setTab('reports'); setEditing(null); setFormData({ ...emptyForm(), condition_id: conditionId }); setReadings([]); }}>
          Cancel
        </button>
      </div>
    </form>
  );

  /* ================================================================== */
  /* ── REPORTS TAB ── */
  const renderReports = () => (
    <div>
      {/* Summary Cards */}
      {summary && summary.total_sessions > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14, marginBottom: 24 }}>
          {[
            { label: 'Sessions', value: summary.total_sessions, color: '#1565c0' },
            { label: 'Avg Pre Wt', value: summary.avg_pre_weight_kg ? `${summary.avg_pre_weight_kg} kg` : '—', color: '#2e7d32' },
            { label: 'Avg Post Wt', value: summary.avg_post_weight_kg ? `${summary.avg_post_weight_kg} kg` : '—', color: '#2e7d32' },
            { label: 'Avg UF', value: summary.avg_fluid_removed_ml ? `${summary.avg_fluid_removed_ml} mL` : '—', color: '#e65100' },
            { label: 'Avg Duration', value: summary.avg_duration_min ? `${summary.avg_duration_min} min` : '—', color: '#6a1b9a' },
          ].map((c, i) => (
            <div key={i} style={{ ...card, textAlign: 'center', borderTop: `3px solid ${c.color}` }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: c.color }}>{c.value}</div>
              <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>{c.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filter */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
        <label style={{ fontSize: 14, fontWeight: 600 }}>Period:</label>
        {[30, 90, 180, 365, 3650].map(d => (
          <button key={d} onClick={() => setFilter(f => ({ ...f, days: d, page: 0 }))}
            style={filter.days === d ? tabActive : { ...tabInactive, borderRadius: 4 }}>
            {d <= 365 ? `${d}d` : 'All'}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 14, color: '#666' }}>{sessions.length} sessions</span>
      </div>

      {/* Session List */}
      {loading ? <p>Loading sessions...</p> : paged.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#888' }}>
          <p>{loadError || 'No hemodialysis sessions found for this period.'}</p>
        </div>
      ) : (
        <>
          {paged.map(session => {
            const expanded = expandedId === session.id;
            const rdgs = session.intradialytic_readings || [];
            return (
              <div key={session.id} style={{ ...card, cursor: 'pointer' }} onClick={() => setExpandedId(expanded ? null : session.id)}>
                {/* Header row */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    <span style={{ fontWeight: 700, fontSize: 16 }}>{fmtDate(session.scheduled_date)}</span>
                    <span style={{ fontSize: 13, padding: '2px 10px', borderRadius: 10,
                      background: session.status === 'COMPLETED' ? '#c8e6c9' : session.status === 'CANCELLED' ? '#eee' : '#bbdefb',
                      color: session.status === 'COMPLETED' ? '#2e7d32' : '#333' }}>
                      {session.status}
                    </span>
                    {session.day_of_week && <span style={{ fontSize: 13, color: '#888' }}>{session.day_of_week}</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 16, alignItems: 'center', fontSize: 14 }}>
                    {session.pre_dialysis_weight_kg && session.post_dialysis_weight_kg && (
                      <span><b>{session.pre_dialysis_weight_kg}</b> → <b>{session.post_dialysis_weight_kg}</b> kg</span>
                    )}
                    {session.fluid_removed_ml && <span style={{ color: '#e65100' }}><b>{session.fluid_removed_ml}</b> mL</span>}
                    {session.duration_minutes && <span style={{ color: '#6a1b9a' }}>{session.duration_minutes} min</span>}
                    {rdgs.length > 0 && <span style={{ fontSize: 12, color: '#1565c0' }}>{rdgs.length} readings</span>}
                    <span style={{ fontSize: 18, color: '#999' }}>{expanded ? '▲' : '▼'}</span>
                  </div>
                </div>

                {/* Vitals summary */}
                {(session.pre_systolic_bp || session.post_systolic_bp) && (
                  <div style={{ fontSize: 13, color: '#666', marginTop: 6 }}>
                    <b>BP:</b> Pre {fmtBP(session.pre_systolic_bp, session.pre_diastolic_bp)}
                    {' → Post '}{fmtBP(session.post_systolic_bp, session.post_diastolic_bp)}
                    {session.pre_heart_rate && <span> | <b>HR:</b> {session.pre_heart_rate}{session.post_heart_rate && ` → ${session.post_heart_rate}`}</span>}
                  </div>
                )}

                {/* Expanded detail */}
                {expanded && (
                  <div style={{ marginTop: 16, borderTop: '1px solid #e0e0e0', paddingTop: 16 }} onClick={e => e.stopPropagation()}>
                    <div style={grid4}>
                      <div><b style={{ fontSize: 12, color: '#888' }}>Facility</b><br />{session.facility_name || '—'}</div>
                      <div><b style={{ fontSize: 12, color: '#888' }}>Access</b><br />{session.dialysis_access_type || '—'}</div>
                      <div><b style={{ fontSize: 12, color: '#888' }}>Dry Weight</b><br />{fmtWeight(session.dry_weight_kg)}</div>
                      <div><b style={{ fontSize: 12, color: '#888' }}>Blood Flow</b><br />{session.blood_flow_rate ? `${session.blood_flow_rate} mL/min` : '—'}</div>
                    </div>

                    {/* Standing vitals */}
                    {(session.pre_standing_systolic_bp || session.post_standing_systolic_bp) && (
                      <div style={{ marginTop: 12, fontSize: 13 }}>
                        <b>Standing BP:</b> Pre {fmtBP(session.pre_standing_systolic_bp, session.pre_standing_diastolic_bp)}
                        {' → Post '}{fmtBP(session.post_standing_systolic_bp, session.post_standing_diastolic_bp)}
                      </div>
                    )}

                    {/* Intradialytic readings table */}
                    {rdgs.length > 0 && (
                      <div style={{ marginTop: 16 }}>
                        <h4 style={{ margin: '0 0 8px', color: '#1565c0', fontSize: 14 }}>Intradialytic Readings ({rdgs.length})</h4>
                        <div style={{ overflowX: 'auto' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                            <thead>
                              <tr style={{ background: '#e3f2fd' }}>
                                {['Time', 'BP', 'Pulse', 'MAP', 'BFR', 'DR', 'UFR', 'UF Vol', 'Art P', 'Ven P', 'Remarks'].map(h => (
                                  <th key={h} style={{ padding: '6px 8px', textAlign: 'left', borderBottom: '2px solid #1565c0', whiteSpace: 'nowrap' }}>{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {rdgs.map((r, i) => (
                                <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                                  <td style={{ padding: '5px 8px', fontWeight: 600 }}>{fmtTime(r.reading_time)}</td>
                                  <td style={{ padding: '5px 8px' }}>{fmtBP(r.systolic_bp, r.diastolic_bp)}</td>
                                  <td style={{ padding: '5px 8px' }}>{r.pulse || '—'}</td>
                                  <td style={{ padding: '5px 8px' }}>{r.mean_arterial_pressure || '—'}</td>
                                  <td style={{ padding: '5px 8px' }}>{r.blood_flow_rate || '—'}</td>
                                  <td style={{ padding: '5px 8px' }}>{r.dialysate_rate || '—'}</td>
                                  <td style={{ padding: '5px 8px' }}>{r.uf_rate || '—'}</td>
                                  <td style={{ padding: '5px 8px' }}>{r.uf_volume_removed || '—'}</td>
                                  <td style={{ padding: '5px 8px' }}>{r.arterial_pressure || '—'}</td>
                                  <td style={{ padding: '5px 8px' }}>{r.venous_pressure || '—'}</td>
                                  <td style={{ padding: '5px 8px', maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.remarks || ''}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* Post-treatment & notes */}
                    {(session.total_dialysate_liters || session.total_uf_liters || session.total_blood_volume_processed) && (
                      <div style={{ ...grid3, marginTop: 12, fontSize: 13 }}>
                        <div><b>Total Dialysate:</b> {session.total_dialysate_liters ? `${session.total_dialysate_liters} L` : '—'}</div>
                        <div><b>Total UF:</b> {session.total_uf_liters ? `${session.total_uf_liters} L` : '—'}</div>
                        <div><b>Blood Vol:</b> {session.total_blood_volume_processed ? `${session.total_blood_volume_processed} L` : '—'}</div>
                      </div>
                    )}
                    {session.side_effects && <p style={{ marginTop: 10, fontSize: 13, color: '#d32f2f' }}><b>Side Effects:</b> {session.side_effects}</p>}
                    {session.clinical_notes?.length > 0 && (
                      <p style={{ marginTop: 6, fontSize: 13 }}>
                        <b>Clinical Notes:</b>{' '}
                        {session.clinical_notes.map(n => n.note_text).join(' · ')}
                      </p>
                    )}
                    {session.patient_notes && <p style={{ marginTop: 6, fontSize: 13, background: '#f5f5f5', padding: 10, borderRadius: 4 }}><b>Patient Notes:</b> {session.patient_notes}</p>}

                    {/* Actions */}
                    <div style={{ marginTop: 14, display: 'flex', gap: 10 }}>
                      <button onClick={() => startEdit(session)} style={btnPrimary}>Edit Session</button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 16 }}>
              <button disabled={filter.page === 0} onClick={() => setFilter(f => ({ ...f, page: f.page - 1 }))} style={btnSecondary}>← Prev</button>
              <span style={{ padding: '10px 16px', fontSize: 14 }}>Page {filter.page + 1} of {totalPages}</span>
              <button disabled={filter.page >= totalPages - 1} onClick={() => setFilter(f => ({ ...f, page: f.page + 1 }))} style={btnSecondary}>Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  );

  /* ================================================================== */
  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div className="page-header">
          <div className="page-header-left">
            <BackButton />
            <h1 style={{ margin: 0 }}>Hemodialysis</h1>
          </div>
        </div>
        <button onClick={startNew} style={btnPrimary}>+ New Session</button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 0 }}>
        <button onClick={() => setTab('reports')} style={tab === 'reports' ? tabActive : tabInactive}>Session Reports</button>
        <button onClick={() => setTab('form')} style={tab === 'form' ? tabActive : tabInactive}>
          {editing ? 'Edit Session' : 'Session Form'}
        </button>
      </div>
      <div style={{ ...card, borderRadius: '0 6px 6px 6px', marginTop: 0 }}>
        {tab === 'reports' ? renderReports() : renderForm()}
      </div>
    </div>
  );
}
