import { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus } from 'lucide-react';
import BackButton from '../components/BackButton';

export default function Mood() {
  const [entries, setEntries] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    entry_date: new Date().toISOString().split('T')[0],
    mood_score: 5,
    energy_level: 5,
    stress_level: 5,
    anxiety_level: 5,
    sleep_quality: 5,
    sleep_hours: '',
    emotions: '',
    triggers: '',
    coping_strategies: '',
    journal_entry: '',
    gratitude: '',
  });

  useEffect(() => { loadEntries(); }, []);

  async function loadEntries() {
    const { data } = await api.get('/mood/');
    setEntries(data);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const payload = { ...form };
    payload.sleep_hours = payload.sleep_hours ? parseFloat(payload.sleep_hours) : null;
    payload.emotions = payload.emotions || null;
    payload.triggers = payload.triggers || null;
    payload.coping_strategies = payload.coping_strategies || null;
    await api.post('/mood/', payload);
    setShowForm(false);
    loadEntries();
  }

  const moodEmoji = (score) => {
    if (score >= 8) return '😄';
    if (score >= 6) return '🙂';
    if (score >= 4) return '😐';
    if (score >= 2) return '😔';
    return '😢';
  };

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Mood / Mental Health</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={18} /> Check In
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
                <label className="form-label">Mood (1-10): {form.mood_score}</label>
                <input className="form-input" type="range" min="1" max="10" value={form.mood_score}
                  onChange={(e) => setForm({ ...form, mood_score: parseInt(e.target.value) })} />
              </div>
              <div className="form-group">
                <label className="form-label">Energy (1-10): {form.energy_level}</label>
                <input className="form-input" type="range" min="1" max="10" value={form.energy_level}
                  onChange={(e) => setForm({ ...form, energy_level: parseInt(e.target.value) })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Stress (1-10): {form.stress_level}</label>
                <input className="form-input" type="range" min="1" max="10" value={form.stress_level}
                  onChange={(e) => setForm({ ...form, stress_level: parseInt(e.target.value) })} />
              </div>
              <div className="form-group">
                <label className="form-label">Anxiety (1-10): {form.anxiety_level}</label>
                <input className="form-input" type="range" min="1" max="10" value={form.anxiety_level}
                  onChange={(e) => setForm({ ...form, anxiety_level: parseInt(e.target.value) })} />
              </div>
              <div className="form-group">
                <label className="form-label">Sleep Quality (1-10): {form.sleep_quality}</label>
                <input className="form-input" type="range" min="1" max="10" value={form.sleep_quality}
                  onChange={(e) => setForm({ ...form, sleep_quality: parseInt(e.target.value) })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Sleep Hours</label>
                <input className="form-input" type="number" step="0.5" value={form.sleep_hours}
                  onChange={(e) => setForm({ ...form, sleep_hours: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Gratitude</label>
                <input className="form-input" value={form.gratitude}
                  onChange={(e) => setForm({ ...form, gratitude: e.target.value })} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Journal Entry</label>
              <textarea className="form-input" rows={3} value={form.journal_entry}
                onChange={(e) => setForm({ ...form, journal_entry: e.target.value })} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Emotions</label>
                <input className="form-input" placeholder="e.g. anxious, happy, frustrated"
                  value={form.emotions}
                  onChange={(e) => setForm({ ...form, emotions: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Triggers</label>
                <input className="form-input" placeholder="What triggered these emotions?"
                  value={form.triggers}
                  onChange={(e) => setForm({ ...form, triggers: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Coping Strategies</label>
                <input className="form-input" placeholder="e.g. meditation, exercise, talking"
                  value={form.coping_strategies}
                  onChange={(e) => setForm({ ...form, coping_strategies: e.target.value })} />
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
              <th>Mood</th>
              <th>Energy</th>
              <th>Stress</th>
              <th>Sleep</th>
              <th>Journal</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id}>
                <td>{e.entry_date}</td>
                <td>{moodEmoji(e.mood_score)} {e.mood_score}/10</td>
                <td>{e.energy_level ?? '-'}/10</td>
                <td>{e.stress_level ?? '-'}/10</td>
                <td>{e.sleep_hours ? `${e.sleep_hours}h` : '-'}</td>
                <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {e.journal_entry || '-'}
                </td>
                <td></td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>No mood entries yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
