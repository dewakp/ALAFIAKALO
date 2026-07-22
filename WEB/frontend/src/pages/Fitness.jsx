import { localToday } from '../utils/datetime';
import { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus } from 'lucide-react';
import BackButton from '../components/BackButton';
import { usePromptPrefill } from '../hooks/usePromptPrefill';

export default function Fitness() {
  const [logs, setLogs] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    log_date: localToday(),
    activity_type: '',
    duration_minutes: '',
    calories_burned: '',
    steps: '',
    intensity: 'moderate',
    notes: '',
  });

  // Prompt Hub hand-off: open the add-activity form pre-filled.
  usePromptPrefill((prefill) => {
    setForm((f) => ({
      ...f,
      activity_type: prefill.activity || prefill.activity_type || f.activity_type,
      duration_minutes: prefill.duration_minutes || prefill.duration || f.duration_minutes,
      notes: prefill.notes || prefill.text || f.notes,
    }));
    setShowForm(true);
  });

  useEffect(() => { loadLogs(); }, []);

  async function loadLogs() {
    const { data } = await api.get('/fitness/');
    setLogs(data);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const payload = { ...form };
    ['duration_minutes', 'calories_burned', 'steps'].forEach((k) => {
      payload[k] = payload[k] ? parseFloat(payload[k]) : null;
    });
    await api.post('/fitness/', payload);
    setShowForm(false);
    loadLogs();
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Fitness</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={18} /> Add Workout
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Date</label>
                <input className="form-input" type="date" value={form.log_date}
                  onChange={(e) => setForm({ ...form, log_date: e.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">Activity</label>
                <input className="form-input" value={form.activity_type}
                  onChange={(e) => setForm({ ...form, activity_type: e.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">Duration (min)</label>
                <input className="form-input" type="number" value={form.duration_minutes}
                  onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Calories Burned</label>
                <input className="form-input" type="number" value={form.calories_burned}
                  onChange={(e) => setForm({ ...form, calories_burned: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Steps</label>
                <input className="form-input" type="number" value={form.steps}
                  onChange={(e) => setForm({ ...form, steps: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Intensity</label>
                <select className="form-input" value={form.intensity}
                  onChange={(e) => setForm({ ...form, intensity: e.target.value })}>
                  <option value="low">Low</option>
                  <option value="moderate">Moderate</option>
                  <option value="high">High</option>
                </select>
              </div>
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
              <th>Activity</th>
              <th>Duration</th>
              <th>Calories</th>
              <th>Steps</th>
              <th>Intensity</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td>{log.log_date}</td>
                <td>{log.activity_type}</td>
                <td>{log.duration_minutes ? `${log.duration_minutes} min` : '-'}</td>
                <td>{log.calories_burned ?? '-'}</td>
                <td>{log.steps ?? '-'}</td>
                <td>{log.intensity ?? '-'}</td>
                <td></td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>No workouts yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
