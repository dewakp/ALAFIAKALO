import { useState, useEffect } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Plus, Pill, ClipboardList, CheckCircle2, XCircle, Clock,
  AlertTriangle, TrendingUp, RefreshCw, BarChart3, Calendar,
  Package, ChevronDown, Activity,
} from 'lucide-react';
import BackButton from '../components/BackButton';

const STATUS_COLORS = {
  draft: '#9e9e9e', active: '#4caf50', filled: '#2196f3',
  partially_filled: '#ff9800', cancelled: '#f44336', expired: '#757575',
  on_hold: '#9c27b0', taken: '#4caf50', missed: '#f44336',
  skipped: '#ff9800', late: '#ff9800', pending: '#ff9800',
  processing: '#2196f3', ready_for_pickup: '#4caf50',
  dispensed: '#4caf50', returned: '#f44336',
  requested: '#ff9800', approved: '#4caf50', denied: '#f44336',
};

const STATUS_ICONS = {
  taken: CheckCircle2, missed: XCircle, skipped: Clock, late: AlertTriangle,
};

function Badge({ status }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 12,
      fontSize: 12, fontWeight: 600, textTransform: 'capitalize',
      background: `${STATUS_COLORS[status] || '#9e9e9e'}20`,
      color: STATUS_COLORS[status] || '#9e9e9e',
    }}>
      {(status || '').replace(/_/g, ' ')}
    </span>
  );
}

const TABS = [
  { key: 'prescriptions', label: 'Prescriptions', icon: ClipboardList },
  { key: 'queue', label: 'Pharmacy Queue', icon: Package },
  { key: 'adherence', label: 'Adherence', icon: CheckCircle2 },
  { key: 'schedules', label: 'Schedules', icon: Calendar },
  { key: 'refills', label: 'Refills', icon: RefreshCw },
  { key: 'impact', label: 'Impact Analysis', icon: BarChart3 },
];

export default function Pharmacy() {
  const { user } = useAuth();
  const [tab, setTab] = useState('prescriptions');
  const [prescriptions, setPrescriptions] = useState([]);
  const [queue, setQueue] = useState([]);
  const [adherenceLogs, setAdherenceLogs] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [refills, setRefills] = useState([]);
  const [report, setReport] = useState(null);
  const [impact, setImpact] = useState(null);
  const [showRxForm, setShowRxForm] = useState(false);
  const [showAdherenceForm, setShowAdherenceForm] = useState(false);
  const [showDispenseForm, setShowDispenseForm] = useState(false);
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [showRefillForm, setShowRefillForm] = useState(false);
  const [selectedRx, setSelectedRx] = useState(null);
  const [loading, setLoading] = useState(false);

  const [rxForm, setRxForm] = useState({
    patient_id: '', medication_name: '', dosage: '', dosage_unit: 'mg',
    strength: '', form: 'tablet', route: 'oral', frequency: '',
    duration_days: '', quantity: '', refills_authorized: 0,
    diagnosis: '', instructions: '', substitution_allowed: true,
  });
  const [adherenceForm, setAdherenceForm] = useState({
    prescription_id: '', status: 'taken', dose_taken: '',
    scheduled_time: new Date().toISOString().slice(0, 16),
    notes: '', side_effects_reported: '',
    mood_before: '', mood_after: '', pain_before: '', pain_after: '',
  });
  const [dispenseForm, setDispenseForm] = useState({
    prescription_id: '', quantity_dispensed: '', days_supply: '',
    ndc_code: '', lot_number: '', manufacturer: '', is_generic: false,
    interactions_checked: false, allergy_checked: false,
    counseling_provided: false, clinical_notes: '',
  });
  const [scheduleForm, setScheduleForm] = useState({
    prescription_id: '', time_of_day: '08:00', days_of_week: '',
    dose_label: '', reminder_minutes_before: 15,
  });
  const [refillForm, setRefillForm] = useState({
    prescription_id: '', quantity_requested: '', notes: '',
  });

  useEffect(() => {
    if (tab === 'prescriptions') loadPrescriptions();
    else if (tab === 'queue') loadQueue();
    else if (tab === 'adherence') { loadAdherence(); loadReport(); }
    else if (tab === 'schedules') loadSchedules();
    else if (tab === 'refills') loadRefills();
  }, [tab]);

  async function loadPrescriptions() {
    setLoading(true);
    try {
      const { data } = await api.get('/pharmacy/prescriptions', { params: { role: 'patient' } });
      setPrescriptions(data);
    } catch { setPrescriptions([]); }
    setLoading(false);
  }

  async function loadQueue() {
    setLoading(true);
    try {
      const { data } = await api.get('/pharmacy/queue');
      setQueue(data);
    } catch { setQueue([]); }
    setLoading(false);
  }

  async function loadAdherence() {
    try {
      const { data } = await api.get('/pharmacy/adherence', { params: { days: 30 } });
      setAdherenceLogs(data);
    } catch { setAdherenceLogs([]); }
  }

  async function loadReport() {
    try {
      const { data } = await api.get('/pharmacy/adherence/report', { params: { days: 30 } });
      setReport(data);
    } catch { setReport(null); }
  }

  async function loadSchedules() {
    try {
      const { data } = await api.get('/pharmacy/schedules');
      setSchedules(data);
    } catch { setSchedules([]); }
  }

  async function loadRefills() {
    try {
      const { data } = await api.get('/pharmacy/refills');
      setRefills(data);
    } catch { setRefills([]); }
  }

  async function loadImpact(rxId) {
    setLoading(true);
    try {
      const { data } = await api.get(`/pharmacy/impact/${rxId}`);
      setImpact(data);
    } catch { setImpact(null); }
    setLoading(false);
  }

  async function submitPrescription(e) {
    e.preventDefault();
    const payload = { ...rxForm };
    if (payload.patient_id) payload.patient_id = parseInt(payload.patient_id);
    if (payload.duration_days) payload.duration_days = parseInt(payload.duration_days);
    if (payload.quantity) payload.quantity = parseInt(payload.quantity);
    if (payload.refills_authorized) payload.refills_authorized = parseInt(payload.refills_authorized);
    await api.post('/pharmacy/prescriptions', payload);
    setShowRxForm(false);
    loadPrescriptions();
  }

  async function submitAdherence(e) {
    e.preventDefault();
    const payload = { ...adherenceForm };
    payload.prescription_id = parseInt(payload.prescription_id);
    if (payload.scheduled_time) payload.scheduled_time = new Date(payload.scheduled_time).toISOString();
    ['mood_before', 'mood_after', 'pain_before', 'pain_after'].forEach(k => {
      payload[k] = payload[k] ? parseInt(payload[k]) : null;
    });
    await api.post('/pharmacy/adherence', payload);
    setShowAdherenceForm(false);
    loadAdherence();
    loadReport();
  }

  async function submitDispense(e) {
    e.preventDefault();
    const payload = { ...dispenseForm };
    payload.prescription_id = parseInt(payload.prescription_id);
    if (payload.quantity_dispensed) payload.quantity_dispensed = parseInt(payload.quantity_dispensed);
    if (payload.days_supply) payload.days_supply = parseInt(payload.days_supply);
    await api.post('/pharmacy/dispenses', payload);
    setShowDispenseForm(false);
    loadQueue();
  }

  async function submitSchedule(e) {
    e.preventDefault();
    const payload = { ...scheduleForm };
    payload.prescription_id = parseInt(payload.prescription_id);
    payload.reminder_minutes_before = parseInt(payload.reminder_minutes_before);
    await api.post('/pharmacy/schedules', payload);
    setShowScheduleForm(false);
    loadSchedules();
  }

  async function submitRefill(e) {
    e.preventDefault();
    const payload = { ...refillForm };
    payload.prescription_id = parseInt(payload.prescription_id);
    if (payload.quantity_requested) payload.quantity_requested = parseInt(payload.quantity_requested);
    await api.post('/pharmacy/refills', payload);
    setShowRefillForm(false);
    loadRefills();
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title"><Pill size={28} style={{ marginRight: 8 }} /> Pharmacy</h1>
        </div>
      </div>

      {/* Tab Bar */}
      <div style={{
        display: 'flex', gap: 4, marginBottom: 20, overflowX: 'auto',
        borderBottom: '2px solid #e0e0e0', paddingBottom: 0,
      }}>
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '10px 16px', border: 'none', background: 'none',
                cursor: 'pointer', fontSize: 14, fontWeight: tab === t.key ? 700 : 400,
                color: tab === t.key ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                borderBottom: tab === t.key ? '3px solid var(--color-primary)' : '3px solid transparent',
                marginBottom: -2, transition: 'all 0.2s',
              }}
            >
              <Icon size={16} /> {t.label}
            </button>
          );
        })}
      </div>

      {/* ── Prescriptions Tab ─────────────────────────────── */}
      {tab === 'prescriptions' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => setShowRxForm(!showRxForm)}>
              <Plus size={16} /> New Prescription
            </button>
          </div>

          {showRxForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 12 }}>Create Prescription</h3>
              <form onSubmit={submitPrescription}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Patient ID</label>
                    <input className="form-input" type="number" value={rxForm.patient_id}
                      onChange={e => setRxForm({ ...rxForm, patient_id: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Medication Name</label>
                    <input className="form-input" value={rxForm.medication_name}
                      onChange={e => setRxForm({ ...rxForm, medication_name: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Dosage</label>
                    <input className="form-input" value={rxForm.dosage}
                      onChange={e => setRxForm({ ...rxForm, dosage: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Unit</label>
                    <select className="form-input" value={rxForm.dosage_unit}
                      onChange={e => setRxForm({ ...rxForm, dosage_unit: e.target.value })}>
                      <option value="mg">mg</option><option value="ml">ml</option>
                      <option value="g">g</option><option value="mcg">mcg</option>
                      <option value="units">units</option>
                    </select>
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Form</label>
                    <select className="form-input" value={rxForm.form}
                      onChange={e => setRxForm({ ...rxForm, form: e.target.value })}>
                      <option value="tablet">Tablet</option><option value="capsule">Capsule</option>
                      <option value="liquid">Liquid</option><option value="injection">Injection</option>
                      <option value="cream">Cream</option><option value="patch">Patch</option>
                      <option value="inhaler">Inhaler</option><option value="drops">Drops</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Route</label>
                    <select className="form-input" value={rxForm.route}
                      onChange={e => setRxForm({ ...rxForm, route: e.target.value })}>
                      <option value="oral">Oral</option><option value="topical">Topical</option>
                      <option value="IV">IV</option><option value="IM">IM</option>
                      <option value="SC">SC</option><option value="inhalation">Inhalation</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Frequency</label>
                    <input className="form-input" value={rxForm.frequency} placeholder="BID, TID, Q8H..."
                      onChange={e => setRxForm({ ...rxForm, frequency: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Duration (days)</label>
                    <input className="form-input" type="number" value={rxForm.duration_days}
                      onChange={e => setRxForm({ ...rxForm, duration_days: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Quantity</label>
                    <input className="form-input" type="number" value={rxForm.quantity}
                      onChange={e => setRxForm({ ...rxForm, quantity: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Refills</label>
                    <input className="form-input" type="number" value={rxForm.refills_authorized}
                      onChange={e => setRxForm({ ...rxForm, refills_authorized: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group" style={{ flex: 2 }}>
                    <label className="form-label">Diagnosis</label>
                    <input className="form-input" value={rxForm.diagnosis}
                      onChange={e => setRxForm({ ...rxForm, diagnosis: e.target.value })} />
                  </div>
                  <div className="form-group" style={{ flex: 3 }}>
                    <label className="form-label">Patient Instructions (Sig)</label>
                    <input className="form-input" value={rxForm.instructions}
                      onChange={e => setRxForm({ ...rxForm, instructions: e.target.value })} />
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '8px 0' }}>
                  <input type="checkbox" checked={rxForm.substitution_allowed}
                    onChange={e => setRxForm({ ...rxForm, substitution_allowed: e.target.checked })} />
                  <label style={{ fontSize: 14 }}>Generic substitution allowed</label>
                </div>
                <button className="btn btn-primary" type="submit">Create Prescription</button>
              </form>
            </div>
          )}

          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Medication</th><th>Dosage</th><th>Frequency</th>
                  <th>Prescriber</th><th>Status</th><th>Refills</th><th>Date</th><th></th>
                </tr>
              </thead>
              <tbody>
                {prescriptions.map(rx => (
                  <tr key={rx.id}>
                    <td style={{ fontWeight: 600 }}>{rx.medication_name}</td>
                    <td>{rx.dosage} {rx.dosage_unit}</td>
                    <td>{rx.frequency || '-'}</td>
                    <td>{rx.prescriber_name || `#${rx.prescriber_id}`}</td>
                    <td><Badge status={rx.status} /></td>
                    <td>{rx.refills_remaining}/{rx.refills_authorized}</td>
                    <td>{rx.prescribed_date}</td>
                    <td>
                      <button className="btn btn-sm" style={{ fontSize: 12 }}
                        onClick={() => { setSelectedRx(rx); setTab('impact'); loadImpact(rx.id); }}>
                        <BarChart3 size={14} /> Impact
                      </button>
                    </td>
                  </tr>
                ))}
                {prescriptions.length === 0 && (
                  <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                    No prescriptions found
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Pharmacy Queue Tab ────────────────────────────── */}
      {tab === 'queue' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => setShowDispenseForm(!showDispenseForm)}>
              <Package size={16} /> Dispense Medication
            </button>
          </div>

          {showDispenseForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 12 }}>Dispense Medication</h3>
              <form onSubmit={submitDispense}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Prescription ID</label>
                    <input className="form-input" type="number" value={dispenseForm.prescription_id}
                      onChange={e => setDispenseForm({ ...dispenseForm, prescription_id: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Quantity</label>
                    <input className="form-input" type="number" value={dispenseForm.quantity_dispensed}
                      onChange={e => setDispenseForm({ ...dispenseForm, quantity_dispensed: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Days Supply</label>
                    <input className="form-input" type="number" value={dispenseForm.days_supply}
                      onChange={e => setDispenseForm({ ...dispenseForm, days_supply: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">NDC Code</label>
                    <input className="form-input" value={dispenseForm.ndc_code}
                      onChange={e => setDispenseForm({ ...dispenseForm, ndc_code: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Lot Number</label>
                    <input className="form-input" value={dispenseForm.lot_number}
                      onChange={e => setDispenseForm({ ...dispenseForm, lot_number: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Manufacturer</label>
                    <input className="form-input" value={dispenseForm.manufacturer}
                      onChange={e => setDispenseForm({ ...dispenseForm, manufacturer: e.target.value })} />
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 16, margin: '8px 0' }}>
                  {[
                    ['is_generic', 'Generic'],
                    ['interactions_checked', 'Interactions Checked'],
                    ['allergy_checked', 'Allergies Checked'],
                    ['counseling_provided', 'Counseling Provided'],
                  ].map(([key, label]) => (
                    <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13 }}>
                      <input type="checkbox" checked={dispenseForm[key]}
                        onChange={e => setDispenseForm({ ...dispenseForm, [key]: e.target.checked })} />
                      {label}
                    </label>
                  ))}
                </div>
                <div className="form-group" style={{ marginTop: 8 }}>
                  <label className="form-label">Clinical Notes</label>
                  <textarea className="form-input" rows={2} value={dispenseForm.clinical_notes}
                    onChange={e => setDispenseForm({ ...dispenseForm, clinical_notes: e.target.value })} />
                </div>
                <button className="btn btn-primary" type="submit">Dispense</button>
              </form>
            </div>
          )}

          <div className="card">
            <h3 style={{ marginBottom: 12 }}>Active Prescriptions Queue</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th><th>Medication</th><th>Patient</th>
                  <th>Dosage</th><th>Frequency</th><th>Status</th><th>Prescribed</th>
                </tr>
              </thead>
              <tbody>
                {queue.map(rx => (
                  <tr key={rx.id}>
                    <td>#{rx.id}</td>
                    <td style={{ fontWeight: 600 }}>{rx.medication_name}</td>
                    <td>{rx.patient_name || `#${rx.patient_id}`}</td>
                    <td>{rx.dosage} {rx.dosage_unit}</td>
                    <td>{rx.frequency || '-'}</td>
                    <td><Badge status={rx.status} /></td>
                    <td>{rx.prescribed_date}</td>
                  </tr>
                ))}
                {queue.length === 0 && (
                  <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                    No prescriptions in queue
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Adherence Tab ─────────────────────────────────── */}
      {tab === 'adherence' && (
        <div>
          {/* Adherence Report Card */}
          {report && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 20 }}>
              {[
                { label: 'Adherence Rate', value: `${report.adherence_rate}%`, color: report.adherence_rate >= 80 ? '#4caf50' : report.adherence_rate >= 50 ? '#ff9800' : '#f44336' },
                { label: 'Taken', value: report.total_taken, color: '#4caf50' },
                { label: 'Missed', value: report.total_missed, color: '#f44336' },
                { label: 'Late', value: report.total_late, color: '#ff9800' },
                { label: 'Current Streak', value: `${report.streak_current} days`, color: '#2196f3' },
                { label: 'Longest Streak', value: `${report.streak_longest} days`, color: '#2196f3' },
              ].map(s => (
                <div key={s.label} className="card" style={{ textAlign: 'center', padding: 16 }}>
                  <div style={{ fontSize: 28, fontWeight: 700, color: s.color }}>{s.value}</div>
                  <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4 }}>{s.label}</div>
                </div>
              ))}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => setShowAdherenceForm(!showAdherenceForm)}>
              <Plus size={16} /> Log Dose
            </button>
          </div>

          {showAdherenceForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 12 }}>Log Medication Dose</h3>
              <form onSubmit={submitAdherence}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Prescription ID</label>
                    <input className="form-input" type="number" value={adherenceForm.prescription_id}
                      onChange={e => setAdherenceForm({ ...adherenceForm, prescription_id: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Status</label>
                    <select className="form-input" value={adherenceForm.status}
                      onChange={e => setAdherenceForm({ ...adherenceForm, status: e.target.value })}>
                      <option value="taken">Taken</option><option value="missed">Missed</option>
                      <option value="skipped">Skipped</option><option value="late">Late</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Scheduled Time</label>
                    <input className="form-input" type="datetime-local" value={adherenceForm.scheduled_time}
                      onChange={e => setAdherenceForm({ ...adherenceForm, scheduled_time: e.target.value })} required />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Mood Before (1-10)</label>
                    <input className="form-input" type="number" min={1} max={10} value={adherenceForm.mood_before}
                      onChange={e => setAdherenceForm({ ...adherenceForm, mood_before: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Mood After (1-10)</label>
                    <input className="form-input" type="number" min={1} max={10} value={adherenceForm.mood_after}
                      onChange={e => setAdherenceForm({ ...adherenceForm, mood_after: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Pain Before (1-10)</label>
                    <input className="form-input" type="number" min={1} max={10} value={adherenceForm.pain_before}
                      onChange={e => setAdherenceForm({ ...adherenceForm, pain_before: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Pain After (1-10)</label>
                    <input className="form-input" type="number" min={1} max={10} value={adherenceForm.pain_after}
                      onChange={e => setAdherenceForm({ ...adherenceForm, pain_after: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group" style={{ flex: 2 }}>
                    <label className="form-label">Side Effects</label>
                    <input className="form-input" value={adherenceForm.side_effects_reported}
                      onChange={e => setAdherenceForm({ ...adherenceForm, side_effects_reported: e.target.value })}
                      placeholder="e.g., nausea, dizziness" />
                  </div>
                  <div className="form-group" style={{ flex: 2 }}>
                    <label className="form-label">Notes</label>
                    <input className="form-input" value={adherenceForm.notes}
                      onChange={e => setAdherenceForm({ ...adherenceForm, notes: e.target.value })} />
                  </div>
                </div>
                <button className="btn btn-primary" type="submit">Log Dose</button>
              </form>
            </div>
          )}

          <div className="card">
            <h3 style={{ marginBottom: 12 }}>Adherence History</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>Medication</th><th>Scheduled</th><th>Status</th>
                  <th>Mood</th><th>Pain</th><th>Side Effects</th>
                </tr>
              </thead>
              <tbody>
                {adherenceLogs.map(log => {
                  const Icon = STATUS_ICONS[log.status] || Clock;
                  return (
                    <tr key={log.id}>
                      <td style={{ fontWeight: 600 }}>{log.medication_name || `Rx #${log.prescription_id}`}</td>
                      <td>{new Date(log.scheduled_time).toLocaleString()}</td>
                      <td><Badge status={log.status} /></td>
                      <td>{log.mood_before != null ? `${log.mood_before}→${log.mood_after ?? '?'}` : '-'}</td>
                      <td>{log.pain_before != null ? `${log.pain_before}→${log.pain_after ?? '?'}` : '-'}</td>
                      <td style={{ fontSize: 13 }}>{log.side_effects_reported || '-'}</td>
                    </tr>
                  );
                })}
                {adherenceLogs.length === 0 && (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                    No adherence logs yet
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Schedules Tab ─────────────────────────────────── */}
      {tab === 'schedules' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => setShowScheduleForm(!showScheduleForm)}>
              <Plus size={16} /> Add Schedule
            </button>
          </div>

          {showScheduleForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 12 }}>Create Medication Schedule</h3>
              <form onSubmit={submitSchedule}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Prescription ID</label>
                    <input className="form-input" type="number" value={scheduleForm.prescription_id}
                      onChange={e => setScheduleForm({ ...scheduleForm, prescription_id: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Time of Day</label>
                    <input className="form-input" type="time" value={scheduleForm.time_of_day}
                      onChange={e => setScheduleForm({ ...scheduleForm, time_of_day: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Dose Label</label>
                    <input className="form-input" value={scheduleForm.dose_label} placeholder="Morning dose"
                      onChange={e => setScheduleForm({ ...scheduleForm, dose_label: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Days (leave blank for daily)</label>
                    <input className="form-input" value={scheduleForm.days_of_week} placeholder="mon,tue,wed"
                      onChange={e => setScheduleForm({ ...scheduleForm, days_of_week: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Reminder (min before)</label>
                    <input className="form-input" type="number" value={scheduleForm.reminder_minutes_before}
                      onChange={e => setScheduleForm({ ...scheduleForm, reminder_minutes_before: e.target.value })} />
                  </div>
                </div>
                <button className="btn btn-primary" type="submit">Create Schedule</button>
              </form>
            </div>
          )}

          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Medication</th><th>Time</th><th>Label</th>
                  <th>Days</th><th>Reminder</th><th>Active</th>
                </tr>
              </thead>
              <tbody>
                {schedules.map(s => (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 600 }}>{s.medication_name || `Rx #${s.prescription_id}`}</td>
                    <td>{s.time_of_day}</td>
                    <td>{s.dose_label || '-'}</td>
                    <td>{s.days_of_week || 'Daily'}</td>
                    <td>{s.reminder_minutes_before} min</td>
                    <td>{s.is_active ? '🟢' : '⚪'}</td>
                  </tr>
                ))}
                {schedules.length === 0 && (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                    No schedules set up
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Refills Tab ───────────────────────────────────── */}
      {tab === 'refills' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => setShowRefillForm(!showRefillForm)}>
              <RefreshCw size={16} /> Request Refill
            </button>
          </div>

          {showRefillForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 12 }}>Request Refill</h3>
              <form onSubmit={submitRefill}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Prescription ID</label>
                    <input className="form-input" type="number" value={refillForm.prescription_id}
                      onChange={e => setRefillForm({ ...refillForm, prescription_id: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Quantity Requested</label>
                    <input className="form-input" type="number" value={refillForm.quantity_requested}
                      onChange={e => setRefillForm({ ...refillForm, quantity_requested: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Notes</label>
                    <input className="form-input" value={refillForm.notes}
                      onChange={e => setRefillForm({ ...refillForm, notes: e.target.value })} />
                  </div>
                </div>
                <button className="btn btn-primary" type="submit">Submit Request</button>
              </form>
            </div>
          )}

          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Medication</th><th>Requested</th><th>Status</th>
                  <th>Quantity</th><th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {refills.map(r => (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 600 }}>{r.medication_name || `Rx #${r.prescription_id}`}</td>
                    <td>{new Date(r.requested_at).toLocaleDateString()}</td>
                    <td><Badge status={r.status} /></td>
                    <td>{r.quantity_requested || '-'}</td>
                    <td style={{ fontSize: 13 }}>{r.notes || r.denial_reason || '-'}</td>
                  </tr>
                ))}
                {refills.length === 0 && (
                  <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                    No refill requests
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Impact Analysis Tab ───────────────────────────── */}
      {tab === 'impact' && (
        <div>
          {!impact && !loading && (
            <div className="card" style={{ textAlign: 'center', padding: 40 }}>
              <Activity size={48} style={{ color: 'var(--color-text-secondary)', marginBottom: 12 }} />
              <p style={{ color: 'var(--color-text-secondary)' }}>
                Select a prescription from the Prescriptions tab to analyze its health impact.
              </p>
            </div>
          )}
          {loading && <div className="card" style={{ textAlign: 'center', padding: 40 }}>Loading impact analysis...</div>}
          {impact && !loading && (
            <div>
              <h2 style={{ marginBottom: 16 }}>
                <Pill size={22} style={{ marginRight: 8 }} />
                {impact.medication_name} — Impact Report
              </h2>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 20 }}>
                {[
                  { label: 'Adherence Rate', value: `${impact.adherence_rate}%`, color: impact.adherence_rate >= 80 ? '#4caf50' : '#f44336' },
                  { label: 'Doses Taken', value: impact.doses_taken, color: '#4caf50' },
                  { label: 'Doses Missed', value: impact.doses_missed, color: '#f44336' },
                  { label: 'Analysis Period', value: `${impact.analysis_period_days} days`, color: '#2196f3' },
                ].map(c => (
                  <div key={c.label} className="card" style={{ textAlign: 'center', padding: 16 }}>
                    <div style={{ fontSize: 32, fontWeight: 700, color: c.color }}>{c.value}</div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4 }}>{c.label}</div>
                  </div>
                ))}
              </div>

              {(impact.avg_mood_before != null || impact.avg_mood_after != null) && (
                <div className="card" style={{ marginBottom: 12 }}>
                  <h3 style={{ marginBottom: 8 }}><TrendingUp size={18} style={{ marginRight: 6 }} /> Mood Impact</h3>
                  <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
                    <div>Before: <strong>{impact.avg_mood_before ?? 'N/A'}</strong>/10</div>
                    <div style={{ fontSize: 20 }}>→</div>
                    <div>After: <strong>{impact.avg_mood_after ?? 'N/A'}</strong>/10</div>
                    {impact.mood_trend && <Badge status={impact.mood_trend === 'improving' ? 'taken' : impact.mood_trend === 'declining' ? 'missed' : 'skipped'} />}
                  </div>
                </div>
              )}

              {impact.reported_side_effects?.length > 0 && (
                <div className="card" style={{ marginBottom: 12 }}>
                  <h3 style={{ marginBottom: 8 }}><AlertTriangle size={18} style={{ marginRight: 6 }} /> Side Effects</h3>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {impact.reported_side_effects.map(se => (
                      <span key={se} style={{
                        padding: '4px 12px', borderRadius: 16, fontSize: 13,
                        background: '#fff3e0', color: '#e65100', fontWeight: 500,
                      }}>
                        {se} {impact.side_effect_frequency?.[se] ? `(${impact.side_effect_frequency[se]}×)` : ''}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {impact.ai_summary && (
                <div className="card" style={{ background: '#e8f5e9', border: '1px solid #a5d6a7' }}>
                  <h3 style={{ marginBottom: 8, color: '#2e7d32' }}>AI Summary</h3>
                  <p style={{ margin: 0, lineHeight: 1.6 }}>{impact.ai_summary}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
