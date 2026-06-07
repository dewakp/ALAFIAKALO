import { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus } from 'lucide-react';
import BackButton from '../components/BackButton';

export default function Lifestyle() {
  const [entries, setEntries] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    entry_date: new Date().toISOString().split('T')[0],
    weight_kg: '',
    blood_pressure_systolic: '',
    blood_pressure_diastolic: '',
    resting_heart_rate: '',
    body_temperature_c: '',
    blood_oxygen_pct: '',
    screen_time_minutes: '',
    outdoor_time_minutes: '',
    notes: '',
  });

  useEffect(() => { loadEntries(); }, []);

  async function loadEntries() {
    const { data } = await api.get('/lifestyle/');
    setEntries(data);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const payload = { ...form };
    Object.keys(payload).forEach((k) => {
      if (k !== 'entry_date' && k !== 'notes' && payload[k] === '') {
        payload[k] = null;
      } else if (k !== 'entry_date' && k !== 'notes' && payload[k]) {
        payload[k] = parseFloat(payload[k]);
      }
    });
    await api.post('/lifestyle/', payload);
    setShowForm(false);
    loadEntries();
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Lifestyle</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={18} /> Add Entry
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Date</label>
                <input className="form-input" type="date" value={form.entry_date}
                  onChange={(e) => setForm({ ...form, entry_date: e.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">Weight (kg)</label>
                <input className="form-input" type="number" step="0.1" value={form.weight_kg}
                  onChange={(e) => setForm({ ...form, weight_kg: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Resting HR (bpm)</label>
                <input className="form-input" type="number" value={form.resting_heart_rate}
                  onChange={(e) => setForm({ ...form, resting_heart_rate: e.target.value })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">BP Systolic</label>
                <input className="form-input" type="number" value={form.blood_pressure_systolic}
                  onChange={(e) => setForm({ ...form, blood_pressure_systolic: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">BP Diastolic</label>
                <input className="form-input" type="number" value={form.blood_pressure_diastolic}
                  onChange={(e) => setForm({ ...form, blood_pressure_diastolic: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Temp (°C)</label>
                <input className="form-input" type="number" step="0.1" value={form.body_temperature_c}
                  onChange={(e) => setForm({ ...form, body_temperature_c: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">SpO₂ (%)</label>
                <input className="form-input" type="number" step="0.1" value={form.blood_oxygen_pct}
                  onChange={(e) => setForm({ ...form, blood_oxygen_pct: e.target.value })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Screen Time (min)</label>
                <input className="form-input" type="number" value={form.screen_time_minutes}
                  onChange={(e) => setForm({ ...form, screen_time_minutes: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Outdoor Time (min)</label>
                <input className="form-input" type="number" value={form.outdoor_time_minutes}
                  onChange={(e) => setForm({ ...form, outdoor_time_minutes: e.target.value })} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <input className="form-input" value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
            <button className="btn btn-primary" type="submit">Save</button>
          </form>
        </div>
      )}

      <div className="card">
        <div style={{ marginBottom: '.75rem', color: 'var(--color-text-secondary)', fontSize: '.8rem' }}>
          Entries are editable but cannot be deleted.
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Weight</th>
              <th>BP</th>
              <th>HR</th>
              <th>SpO₂</th>
              <th>Screen</th>
              <th>Outdoor</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td>{e.entry_date}</td>
                <td>{e.weight_kg ? `${e.weight_kg} kg` : '-'}</td>
                <td>{e.blood_pressure_systolic ? `${e.blood_pressure_systolic}/${e.blood_pressure_diastolic}` : '-'}</td>
                <td>{e.resting_heart_rate ?? '-'}</td>
                <td>{e.blood_oxygen_pct ? `${e.blood_oxygen_pct}%` : '-'}</td>
                <td>{e.screen_time_minutes ? `${e.screen_time_minutes}m` : '-'}</td>
                <td>{e.outdoor_time_minutes ? `${e.outdoor_time_minutes}m` : '-'}</td>
                <td></td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>No entries yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
