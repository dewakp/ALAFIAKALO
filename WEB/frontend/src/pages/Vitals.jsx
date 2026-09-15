import { localToday } from '../utils/datetime';
import { useState, useEffect, useCallback, useMemo } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Plus, Trash2, HeartPulse } from 'lucide-react';
import BackButton from '../components/BackButton';
import { usePromptPrefill } from '../hooks/usePromptPrefill';
import { useTempUnit } from '../hooks/useTempUnit';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid,
} from 'recharts';
import { t } from '../i18n';

const today = () => localToday();

const EMPTY = {
  log_date: today(), log_time: '',
  weight_kg: '', height_cm: '',
  blood_pressure_systolic: '', blood_pressure_diastolic: '',
  heart_rate_bpm: '', temp_val: '',   // entered in the chosen unit; stored as °C
  blood_oxygen_pct: '', blood_glucose_mg_dl: '', glucose_timing: '',
  notes: '',
};

// Trend metrics the chart can plot. BP draws two lines.
const METRICS = [
  { key: 'blood_pressure', get label() { return t('Vitals.blood_pressure'); }, lines: [
      { dataKey: 'blood_pressure_systolic', name: 'Systolic', color: '#ef4444' },
      { dataKey: 'blood_pressure_diastolic', name: 'Diastolic', color: '#3b82f6' },
    ], unit: 'mmHg' },
  { key: 'weight_kg', get label() { return t('Vitals.weight'); }, lines: [{ dataKey: 'weight_kg', name: 'Weight', color: '#22c55e' }], unit: 'kg' },
  { key: 'heart_rate_bpm', get label() { return t('Vitals.heart_rate'); }, lines: [{ dataKey: 'heart_rate_bpm', name: 'Heart rate', color: '#f59e0b' }], unit: 'bpm' },
  { key: 'blood_glucose_mg_dl', get label() { return t('Vitals.blood_glucose'); }, lines: [{ dataKey: 'blood_glucose_mg_dl', name: 'Glucose', color: '#a855f7' }], unit: 'mg/dL' },
  { key: 'blood_oxygen_pct', get label() { return t('Vitals.blood_oxygen'); }, lines: [{ dataKey: 'blood_oxygen_pct', name: 'SpO₂', color: '#06b6d4' }], unit: '%' },
  { key: 'body_temperature_c', get label() { return t('Vitals.temperature'); }, lines: [{ dataKey: 'body_temperature_c', name: 'Temp', color: '#ec4899' }], unit: '°C' },
];

const num = (v) => (v !== '' && v != null ? Number(v) : null);

export default function Vitals() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY });
  const [saving, setSaving] = useState(false);
  const [metricKey, setMetricKey] = useState('blood_pressure');
  const temp = useTempUnit();

  function handleTempToggle() {
    setForm((f) => (f.temp_val ? { ...f, temp_val: temp.convertInPlace(f.temp_val) } : f));
    temp.toggle();
  }

  usePromptPrefill((prefill) => {
    setForm((f) => ({ ...f, notes: prefill.text || prefill.notes || f.notes }));
    setShowForm(true);
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/vitals/');
      setLogs(data);
    } catch { setLogs([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  function update(field, value) { setForm((f) => ({ ...f, [field]: value })); }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        log_date: form.log_date,
        log_time: form.log_time || null,
        glucose_timing: form.glucose_timing || null,
        notes: form.notes || null,
        weight_kg: num(form.weight_kg), height_cm: num(form.height_cm),
        blood_pressure_systolic: num(form.blood_pressure_systolic),
        blood_pressure_diastolic: num(form.blood_pressure_diastolic),
        heart_rate_bpm: num(form.heart_rate_bpm),
        // Always store Celsius; convert if the user entered Fahrenheit.
        body_temperature_c: temp.toCelsius(form.temp_val),
        blood_oxygen_pct: num(form.blood_oxygen_pct),
        blood_glucose_mg_dl: num(form.blood_glucose_mg_dl),
      };
      await api.post('/vitals/', payload);
      setForm({ ...EMPTY });
      setShowForm(false);
      load();
    } catch (err) {
      alert(apiErrorMessage(err, t('Vitals.could_not_save_vitals')));
    } finally { setSaving(false); }
  }

  async function handleDelete(id) {
    if (!confirm(t('Vitals.delete_this_vitals_entry'))) return;
    try { await api.delete(`/vitals/${id}`); load(); }
    catch (err) { alert(apiErrorMessage(err, t('Vitals.could_not_delete'))); }
  }

  const metric = METRICS.find((m) => m.key === metricKey) || METRICS[0];

  // Build ascending-by-date series for the selected metric (only points that have a value).
  const isTemp = metric.key === 'body_temperature_c';
  const chartData = useMemo(() => {
    const keys = metric.lines.map((l) => l.dataKey);
    return [...logs]
      .filter((r) => keys.some((k) => r[k] != null))
      .sort((a, b) => (a.log_date < b.log_date ? -1 : 1))
      .map((r) => {
        const row = { date: r.log_date };
        // Temperature is stored in °C; show it in the chosen unit.
        keys.forEach((k) => { row[k] = isTemp ? temp.fromCelsius(r[k]) : r[k]; });
        return row;
      });
  }, [logs, metric, isTemp, temp]);

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">{t('Vitals.vitals')}</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm((v) => !v)}>
          <Plus size={18} /> {t('Vitals.log_vitals')}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Vitals.date')}</label>
                <input className="form-input" type="date" value={form.log_date} onChange={(e) => update('log_date', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Vitals.time')}</label>
                <input className="form-input" type="time" value={form.log_time} onChange={(e) => update('log_time', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Vitals.weight_kg')}</label>
                <input className="form-input" type="number" step="0.1" value={form.weight_kg} onChange={(e) => update('weight_kg', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Vitals.bp_systolic')}</label>
                <input className="form-input" type="number" value={form.blood_pressure_systolic} onChange={(e) => update('blood_pressure_systolic', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Vitals.bp_diastolic')}</label>
                <input className="form-input" type="number" value={form.blood_pressure_diastolic} onChange={(e) => update('blood_pressure_diastolic', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Vitals.heart_rate_bpm')}</label>
                <input className="form-input" type="number" value={form.heart_rate_bpm} onChange={(e) => update('heart_rate_bpm', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{t('Vitals.temp', { label: temp.label })}</span>
                  <button type="button" onClick={handleTempToggle}
                    style={{ fontSize: '.7rem', padding: '1px 8px', borderRadius: 10, border: '1px solid var(--primary)', background: 'transparent', color: 'var(--primary)', cursor: 'pointer' }}
                    title={t('Vitals.toggle_f_c_stored_in_c')}>
                    {(temp.unit === 'F') ? t('Vitals.switch_to_c') : t('Vitals.switch_to_f')}
                  </button>
                </label>
                <input className="form-input" type="number" step="0.1"
                  placeholder={temp.unit === 'F' ? '98.6' : '37.0'}
                  value={form.temp_val} onChange={(e) => update('temp_val', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Vitals.spo')}</label>
                <input className="form-input" type="number" step="0.1" value={form.blood_oxygen_pct} onChange={(e) => update('blood_oxygen_pct', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Vitals.glucose_mg_dl')}</label>
                <input className="form-input" type="number" step="0.1" value={form.blood_glucose_mg_dl} onChange={(e) => update('blood_glucose_mg_dl', e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">{t('Vitals.notes')}</label>
              <textarea className="form-input" rows={2} value={form.notes} onChange={(e) => update('notes', e.target.value)} />
            </div>
            <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save Vitals'}</button>
          </form>
        </div>
      )}

      {/* ── Trends ── */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10, flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0 }}>{t('Vitals.trends')}</h3>
          <select className="form-input" style={{ maxWidth: 220 }} value={metricKey} onChange={(e) => setMetricKey(e.target.value)}>
            {METRICS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
          <span style={{ fontSize: '.8rem', color: 'var(--text-secondary)' }}>{isTemp ? temp.label : metric.unit}</span>
        </div>
        {chartData.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)' }}>{t('Vitals.no_readings_yet', { label: metric.label.toLowerCase() })}</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData} margin={{ top: 8, right: 20, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" fontSize={11} />
              <YAxis fontSize={11} domain={['auto', 'auto']} />
              <Tooltip />
              <Legend />
              {metric.lines.map((l) => (
                <Line key={l.dataKey} type="monotone" dataKey={l.dataKey} name={l.name}
                  stroke={l.color} strokeWidth={2} dot={{ r: 2 }} connectNulls />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── Running log ── */}
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{t('Vitals.vitals_log')}{logs.length > 0 && <span style={{ fontSize: '.8rem', color: 'var(--text-secondary)', fontWeight: 400, marginLeft: 8 }}>({logs.length})</span>}</h3>
        {loading ? <p>{t('Vitals.loading')}</p> : logs.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
            <HeartPulse size={28} style={{ opacity: 0.5 }} /><p>{t('Vitals.no_vitals_logged_yet')}</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr><th>{t('Vitals.date')}</th><th>BP</th><th>HR</th><th>{t('Vitals.weight')}</th><th>{t('Vitals.temp_2')}</th><th>{t('Vitals.spo_2')}</th><th>{t('Vitals.glucose')}</th><th></th></tr>
            </thead>
            <tbody>
              {logs.map((v) => (
                <tr key={v.id}>
                  <td>{v.log_date}{v.log_time ? ` ${String(v.log_time).slice(0,5)}` : ''}</td>
                  <td>{v.blood_pressure_systolic != null ? `${v.blood_pressure_systolic}/${v.blood_pressure_diastolic ?? '-'}` : '-'}</td>
                  <td>{v.heart_rate_bpm ?? '-'}</td>
                  <td>{v.weight_kg != null ? `${v.weight_kg} kg` : '-'}</td>
                  <td>{v.body_temperature_c != null ? temp.fmt(v.body_temperature_c) : '-'}</td>
                  <td>{v.blood_oxygen_pct != null ? `${v.blood_oxygen_pct}%` : '-'}</td>
                  <td>{v.blood_glucose_mg_dl != null ? v.blood_glucose_mg_dl : '-'}</td>
                  <td><button className="btn btn-danger btn-sm" onClick={() => handleDelete(v.id)} title={t('Vitals.delete')}><Trash2 size={15} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
