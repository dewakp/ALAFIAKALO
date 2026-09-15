import { fmtDateTime, toDateTimeInput } from '../utils/datetime';
import { useState, useEffect } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import {
  Plus, Pill, ClipboardList, CheckCircle2, XCircle, Clock,
  AlertTriangle, TrendingUp, RefreshCw, BarChart3, Calendar,
  Package, ChevronDown, Activity,
} from 'lucide-react';
import BackButton from '../components/BackButton';
import { t as translate } from '../i18n';

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
  { key: 'prescriptions', get label() { return translate('Pharmacy.prescriptions'); }, icon: ClipboardList },
  { key: 'queue', get label() { return translate('Pharmacy.pharmacy_queue'); }, icon: Package },
  { key: 'adherence', get label() { return translate('Pharmacy.adherence'); }, icon: CheckCircle2 },
  { key: 'schedules', get label() { return translate('Pharmacy.schedules'); }, icon: Calendar },
  { key: 'refills', get label() { return translate('Pharmacy.refills'); }, icon: RefreshCw },
  { key: 'impact', get label() { return translate('Pharmacy.impact_analysis'); }, icon: BarChart3 },
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
    scheduled_time: toDateTimeInput(new Date()),
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
          <h1 className="page-title"><Pill size={28} style={{ marginRight: 8 }} /> {translate('Pharmacy.pharmacy')}</h1>
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
              <Plus size={16} /> {translate('Pharmacy.new_prescription')}
            </button>
          </div>

          {showRxForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 12 }}>{translate('Pharmacy.create_prescription')}</h3>
              <form onSubmit={submitPrescription}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.patient_id')}</label>
                    <input className="form-input" type="number" value={rxForm.patient_id}
                      onChange={e => setRxForm({ ...rxForm, patient_id: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.medication_name')}</label>
                    <input className="form-input" value={rxForm.medication_name}
                      onChange={e => setRxForm({ ...rxForm, medication_name: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.dosage')}</label>
                    <input className="form-input" value={rxForm.dosage}
                      onChange={e => setRxForm({ ...rxForm, dosage: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.unit')}</label>
                    <select className="form-input" value={rxForm.dosage_unit}
                      onChange={e => setRxForm({ ...rxForm, dosage_unit: e.target.value })}>
                      <option value="mg">{translate('Pharmacy.mg')}</option><option value="ml">{translate('Pharmacy.ml')}</option>
                      <option value="g">g</option><option value="mcg">{translate('Pharmacy.mcg')}</option>
                      <option value="units">{translate('Pharmacy.units')}</option>
                    </select>
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.form')}</label>
                    <select className="form-input" value={rxForm.form}
                      onChange={e => setRxForm({ ...rxForm, form: e.target.value })}>
                      <option value="tablet">{translate('Pharmacy.tablet')}</option><option value="capsule">{translate('Pharmacy.capsule')}</option>
                      <option value="liquid">{translate('Pharmacy.liquid')}</option><option value="injection">{translate('Pharmacy.injection')}</option>
                      <option value="cream">{translate('Pharmacy.cream')}</option><option value="patch">{translate('Pharmacy.patch')}</option>
                      <option value="inhaler">{translate('Pharmacy.inhaler')}</option><option value="drops">{translate('Pharmacy.drops')}</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.route')}</label>
                    <select className="form-input" value={rxForm.route}
                      onChange={e => setRxForm({ ...rxForm, route: e.target.value })}>
                      <option value="oral">{translate('Pharmacy.oral')}</option><option value="topical">{translate('Pharmacy.topical')}</option>
                      <option value="IV">IV</option><option value="IM">IM</option>
                      <option value="SC">SC</option><option value="inhalation">{translate('Pharmacy.inhalation')}</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.frequency')}</label>
                    <input className="form-input" value={rxForm.frequency} placeholder="BID, TID, Q8H..."
                      onChange={e => setRxForm({ ...rxForm, frequency: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.duration_days')}</label>
                    <input className="form-input" type="number" value={rxForm.duration_days}
                      onChange={e => setRxForm({ ...rxForm, duration_days: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.quantity')}</label>
                    <input className="form-input" type="number" value={rxForm.quantity}
                      onChange={e => setRxForm({ ...rxForm, quantity: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.refills')}</label>
                    <input className="form-input" type="number" value={rxForm.refills_authorized}
                      onChange={e => setRxForm({ ...rxForm, refills_authorized: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group" style={{ flex: 2 }}>
                    <label className="form-label">{translate('Pharmacy.diagnosis')}</label>
                    <input className="form-input" value={rxForm.diagnosis}
                      onChange={e => setRxForm({ ...rxForm, diagnosis: e.target.value })} />
                  </div>
                  <div className="form-group" style={{ flex: 3 }}>
                    <label className="form-label">{translate('Pharmacy.patient_instructions_sig')}</label>
                    <input className="form-input" value={rxForm.instructions}
                      onChange={e => setRxForm({ ...rxForm, instructions: e.target.value })} />
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '8px 0' }}>
                  <input type="checkbox" checked={rxForm.substitution_allowed}
                    onChange={e => setRxForm({ ...rxForm, substitution_allowed: e.target.checked })} />
                  <label style={{ fontSize: 14 }}>{translate('Pharmacy.generic_substitution_allowed')}</label>
                </div>
                <button className="btn btn-primary" type="submit">{translate('Pharmacy.create_prescription')}</button>
              </form>
            </div>
          )}

          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>{translate('Pharmacy.medication')}</th><th>{translate('Pharmacy.dosage')}</th><th>{translate('Pharmacy.frequency')}</th>
                  <th>{translate('Pharmacy.prescriber')}</th><th>{translate('Pharmacy.status')}</th><th>{translate('Pharmacy.refills')}</th><th>{translate('Pharmacy.date')}</th><th></th>
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
                        <BarChart3 size={14} /> {translate('Pharmacy.impact')}
                      </button>
                    </td>
                  </tr>
                ))}
                {prescriptions.length === 0 && (
                  <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                    {translate('Pharmacy.no_prescriptions_found')}
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
              <Package size={16} /> {translate('Pharmacy.dispense_medication')}
            </button>
          </div>

          {showDispenseForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 12 }}>{translate('Pharmacy.dispense_medication')}</h3>
              <form onSubmit={submitDispense}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.prescription_id')}</label>
                    <input className="form-input" type="number" value={dispenseForm.prescription_id}
                      onChange={e => setDispenseForm({ ...dispenseForm, prescription_id: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.quantity')}</label>
                    <input className="form-input" type="number" value={dispenseForm.quantity_dispensed}
                      onChange={e => setDispenseForm({ ...dispenseForm, quantity_dispensed: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.days_supply')}</label>
                    <input className="form-input" type="number" value={dispenseForm.days_supply}
                      onChange={e => setDispenseForm({ ...dispenseForm, days_supply: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.ndc_code')}</label>
                    <input className="form-input" value={dispenseForm.ndc_code}
                      onChange={e => setDispenseForm({ ...dispenseForm, ndc_code: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.lot_number')}</label>
                    <input className="form-input" value={dispenseForm.lot_number}
                      onChange={e => setDispenseForm({ ...dispenseForm, lot_number: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.manufacturer')}</label>
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
                  <label className="form-label">{translate('Pharmacy.clinical_notes')}</label>
                  <textarea className="form-input" rows={2} value={dispenseForm.clinical_notes}
                    onChange={e => setDispenseForm({ ...dispenseForm, clinical_notes: e.target.value })} />
                </div>
                <button className="btn btn-primary" type="submit">{translate('Pharmacy.dispense')}</button>
              </form>
            </div>
          )}

          <div className="card">
            <h3 style={{ marginBottom: 12 }}>{translate('Pharmacy.active_prescriptions_queue')}</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th><th>{translate('Pharmacy.medication')}</th><th>{translate('Pharmacy.patient')}</th>
                  <th>{translate('Pharmacy.dosage')}</th><th>{translate('Pharmacy.frequency')}</th><th>{translate('Pharmacy.status')}</th><th>{translate('Pharmacy.prescribed')}</th>
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
                    {translate('Pharmacy.no_prescriptions_in_queue')}
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
                { label: translate('Pharmacy.adherence_rate'), value: `${report.adherence_rate}%`, color: report.adherence_rate >= 80 ? '#4caf50' : report.adherence_rate >= 50 ? '#ff9800' : '#f44336' },
                { label: translate('Pharmacy.taken'), value: report.total_taken, color: '#4caf50' },
                { label: translate('Pharmacy.missed'), value: report.total_missed, color: '#f44336' },
                { label: translate('Pharmacy.late'), value: report.total_late, color: '#ff9800' },
                { label: translate('Pharmacy.current_streak'), value: `${report.streak_current} days`, color: '#2196f3' },
                { label: translate('Pharmacy.longest_streak'), value: `${report.streak_longest} days`, color: '#2196f3' },
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
              <Plus size={16} /> {translate('Pharmacy.log_dose')}
            </button>
          </div>

          {showAdherenceForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 12 }}>{translate('Pharmacy.log_medication_dose')}</h3>
              <form onSubmit={submitAdherence}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.prescription_id')}</label>
                    <input className="form-input" type="number" value={adherenceForm.prescription_id}
                      onChange={e => setAdherenceForm({ ...adherenceForm, prescription_id: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.status')}</label>
                    <select className="form-input" value={adherenceForm.status}
                      onChange={e => setAdherenceForm({ ...adherenceForm, status: e.target.value })}>
                      <option value="taken">{translate('Pharmacy.taken')}</option><option value="missed">{translate('Pharmacy.missed')}</option>
                      <option value="skipped">{translate('Pharmacy.skipped')}</option><option value="late">{translate('Pharmacy.late')}</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.scheduled_time')}</label>
                    <input className="form-input" type="datetime-local" value={adherenceForm.scheduled_time}
                      onChange={e => setAdherenceForm({ ...adherenceForm, scheduled_time: e.target.value })} required />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.mood_before_1_10')}</label>
                    <input className="form-input" type="number" min={1} max={10} value={adherenceForm.mood_before}
                      onChange={e => setAdherenceForm({ ...adherenceForm, mood_before: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.mood_after_1_10')}</label>
                    <input className="form-input" type="number" min={1} max={10} value={adherenceForm.mood_after}
                      onChange={e => setAdherenceForm({ ...adherenceForm, mood_after: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.pain_before_1_10')}</label>
                    <input className="form-input" type="number" min={1} max={10} value={adherenceForm.pain_before}
                      onChange={e => setAdherenceForm({ ...adherenceForm, pain_before: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.pain_after_1_10')}</label>
                    <input className="form-input" type="number" min={1} max={10} value={adherenceForm.pain_after}
                      onChange={e => setAdherenceForm({ ...adherenceForm, pain_after: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group" style={{ flex: 2 }}>
                    <label className="form-label">{translate('Pharmacy.side_effects')}</label>
                    <input className="form-input" value={adherenceForm.side_effects_reported}
                      onChange={e => setAdherenceForm({ ...adherenceForm, side_effects_reported: e.target.value })}
                      placeholder={translate('Pharmacy.e_g_nausea_dizziness')} />
                  </div>
                  <div className="form-group" style={{ flex: 2 }}>
                    <label className="form-label">{translate('Pharmacy.notes')}</label>
                    <input className="form-input" value={adherenceForm.notes}
                      onChange={e => setAdherenceForm({ ...adherenceForm, notes: e.target.value })} />
                  </div>
                </div>
                <button className="btn btn-primary" type="submit">{translate('Pharmacy.log_dose')}</button>
              </form>
            </div>
          )}

          <div className="card">
            <h3 style={{ marginBottom: 12 }}>{translate('Pharmacy.adherence_history')}</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>{translate('Pharmacy.medication')}</th><th>{translate('Pharmacy.scheduled')}</th><th>{translate('Pharmacy.status')}</th>
                  <th>{translate('Pharmacy.mood')}</th><th>{translate('Pharmacy.pain')}</th><th>{translate('Pharmacy.side_effects')}</th>
                </tr>
              </thead>
              <tbody>
                {adherenceLogs.map(log => {
                  const Icon = STATUS_ICONS[log.status] || Clock;
                  return (
                    <tr key={log.id}>
                      <td style={{ fontWeight: 600 }}>{log.medication_name || `Rx #${log.prescription_id}`}</td>
                      <td>{fmtDateTime(log.scheduled_time)}</td>
                      <td><Badge status={log.status} /></td>
                      <td>{log.mood_before != null ? `${log.mood_before}→${log.mood_after ?? '?'}` : '-'}</td>
                      <td>{log.pain_before != null ? `${log.pain_before}→${log.pain_after ?? '?'}` : '-'}</td>
                      <td style={{ fontSize: 13 }}>{log.side_effects_reported || '-'}</td>
                    </tr>
                  );
                })}
                {adherenceLogs.length === 0 && (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                    {translate('Pharmacy.no_adherence_logs_yet')}
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
              <Plus size={16} /> {translate('Pharmacy.add_schedule')}
            </button>
          </div>

          {showScheduleForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 12 }}>{translate('Pharmacy.create_medication_schedule')}</h3>
              <form onSubmit={submitSchedule}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.prescription_id')}</label>
                    <input className="form-input" type="number" value={scheduleForm.prescription_id}
                      onChange={e => setScheduleForm({ ...scheduleForm, prescription_id: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.time_of_day')}</label>
                    <input className="form-input" type="time" value={scheduleForm.time_of_day}
                      onChange={e => setScheduleForm({ ...scheduleForm, time_of_day: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.dose_label')}</label>
                    <input className="form-input" value={scheduleForm.dose_label} placeholder={translate('Pharmacy.morning_dose')}
                      onChange={e => setScheduleForm({ ...scheduleForm, dose_label: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.days_leave_blank_for_daily')}</label>
                    <input className="form-input" value={scheduleForm.days_of_week} placeholder={translate('Pharmacy.mon_tue_wed')}
                      onChange={e => setScheduleForm({ ...scheduleForm, days_of_week: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.reminder_min_before')}</label>
                    <input className="form-input" type="number" value={scheduleForm.reminder_minutes_before}
                      onChange={e => setScheduleForm({ ...scheduleForm, reminder_minutes_before: e.target.value })} />
                  </div>
                </div>
                <button className="btn btn-primary" type="submit">{translate('Pharmacy.create_schedule')}</button>
              </form>
            </div>
          )}

          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>{translate('Pharmacy.medication')}</th><th>{translate('Pharmacy.time')}</th><th>{translate('Pharmacy.label')}</th>
                  <th>{translate('Pharmacy.days')}</th><th>{translate('Pharmacy.reminder')}</th><th>{translate('Pharmacy.active')}</th>
                </tr>
              </thead>
              <tbody>
                {schedules.map(s => (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 600 }}>{s.medication_name || `Rx #${s.prescription_id}`}</td>
                    <td>{s.time_of_day}</td>
                    <td>{s.dose_label || '-'}</td>
                    <td>{s.days_of_week || 'Daily'}</td>
                    <td>{translate('Pharmacy.min', { reminder_minutes_before: s.reminder_minutes_before })}</td>
                    <td>{s.is_active ? '🟢' : '⚪'}</td>
                  </tr>
                ))}
                {schedules.length === 0 && (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                    {translate('Pharmacy.no_schedules_set_up')}
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
              <RefreshCw size={16} /> {translate('Pharmacy.request_refill')}
            </button>
          </div>

          {showRefillForm && (
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 style={{ marginBottom: 12 }}>{translate('Pharmacy.request_refill')}</h3>
              <form onSubmit={submitRefill}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.prescription_id')}</label>
                    <input className="form-input" type="number" value={refillForm.prescription_id}
                      onChange={e => setRefillForm({ ...refillForm, prescription_id: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.quantity_requested')}</label>
                    <input className="form-input" type="number" value={refillForm.quantity_requested}
                      onChange={e => setRefillForm({ ...refillForm, quantity_requested: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">{translate('Pharmacy.notes')}</label>
                    <input className="form-input" value={refillForm.notes}
                      onChange={e => setRefillForm({ ...refillForm, notes: e.target.value })} />
                  </div>
                </div>
                <button className="btn btn-primary" type="submit">{translate('Pharmacy.submit_request')}</button>
              </form>
            </div>
          )}

          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>{translate('Pharmacy.medication')}</th><th>{translate('Pharmacy.requested')}</th><th>{translate('Pharmacy.status')}</th>
                  <th>{translate('Pharmacy.quantity')}</th><th>{translate('Pharmacy.notes')}</th>
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
                    {translate('Pharmacy.no_refill_requests')}
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
                {translate('Pharmacy.select_a_prescription_from_the')}
              </p>
            </div>
          )}
          {loading && <div className="card" style={{ textAlign: 'center', padding: 40 }}>{translate('Pharmacy.loading_impact_analysis')}</div>}
          {impact && !loading && (
            <div>
              <h2 style={{ marginBottom: 16 }}>
                <Pill size={22} style={{ marginRight: 8 }} />
                {translate('Pharmacy.impact_report', { medication_name: impact.medication_name })}
              </h2>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 20 }}>
                {[
                  { label: translate('Pharmacy.adherence_rate'), value: `${impact.adherence_rate}%`, color: impact.adherence_rate >= 80 ? '#4caf50' : '#f44336' },
                  { label: translate('Pharmacy.doses_taken'), value: impact.doses_taken, color: '#4caf50' },
                  { label: translate('Pharmacy.doses_missed'), value: impact.doses_missed, color: '#f44336' },
                  { label: translate('Pharmacy.analysis_period'), value: `${impact.analysis_period_days} days`, color: '#2196f3' },
                ].map(c => (
                  <div key={c.label} className="card" style={{ textAlign: 'center', padding: 16 }}>
                    <div style={{ fontSize: 32, fontWeight: 700, color: c.color }}>{c.value}</div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4 }}>{c.label}</div>
                  </div>
                ))}
              </div>

              {(impact.avg_mood_before != null || impact.avg_mood_after != null) && (
                <div className="card" style={{ marginBottom: 12 }}>
                  <h3 style={{ marginBottom: 8 }}><TrendingUp size={18} style={{ marginRight: 6 }} /> {translate('Pharmacy.mood_impact')}</h3>
                  <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
                    <div>{translate('Pharmacy.before')} <strong>{impact.avg_mood_before ?? 'N/A'}</strong>/10</div>
                    <div style={{ fontSize: 20 }}>→</div>
                    <div>{translate('Pharmacy.after')} <strong>{impact.avg_mood_after ?? 'N/A'}</strong>/10</div>
                    {impact.mood_trend && <Badge status={impact.mood_trend === 'improving' ? 'taken' : impact.mood_trend === 'declining' ? 'missed' : 'skipped'} />}
                  </div>
                </div>
              )}

              {impact.reported_side_effects?.length > 0 && (
                <div className="card" style={{ marginBottom: 12 }}>
                  <h3 style={{ marginBottom: 8 }}><AlertTriangle size={18} style={{ marginRight: 6 }} /> {translate('Pharmacy.side_effects')}</h3>
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
                  <h3 style={{ marginBottom: 8, color: '#2e7d32' }}>{translate('Pharmacy.ai_summary')}</h3>
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
