import { localToday } from '../utils/datetime';
import { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus } from 'lucide-react';
import BackButton from '../components/BackButton';
import { t } from '../i18n';

export default function Mood() {
  const [entries, setEntries] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    entry_date: localToday(),
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
          <h1 className="page-title">{t('Mood.mood_mental_health')}</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          <Plus size={18} /> {t('Mood.check_in')}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Mood.date')}</label>
                <input className="form-input" type="date" value={form.entry_date}
                  onChange={(e) => setForm({ ...form, entry_date: e.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Mood.mood_1_10', { mood_score: form.mood_score })}</label>
                <input className="form-input" type="range" min="1" max="10" value={form.mood_score}
                  onChange={(e) => setForm({ ...form, mood_score: parseInt(e.target.value) })} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Mood.energy_1_10', { energy_level: form.energy_level })}</label>
                <input className="form-input" type="range" min="1" max="10" value={form.energy_level}
                  onChange={(e) => setForm({ ...form, energy_level: parseInt(e.target.value) })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Mood.stress_1_10', { stress_level: form.stress_level })}</label>
                <input className="form-input" type="range" min="1" max="10" value={form.stress_level}
                  onChange={(e) => setForm({ ...form, stress_level: parseInt(e.target.value) })} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Mood.anxiety_1_10', { anxiety_level: form.anxiety_level })}</label>
                <input className="form-input" type="range" min="1" max="10" value={form.anxiety_level}
                  onChange={(e) => setForm({ ...form, anxiety_level: parseInt(e.target.value) })} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Mood.sleep_quality_1_10', { sleep_quality: form.sleep_quality })}</label>
                <input className="form-input" type="range" min="1" max="10" value={form.sleep_quality}
                  onChange={(e) => setForm({ ...form, sleep_quality: parseInt(e.target.value) })} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Mood.sleep_hours')}</label>
                <input className="form-input" type="number" step="0.5" value={form.sleep_hours}
                  onChange={(e) => setForm({ ...form, sleep_hours: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Mood.gratitude')}</label>
                <input className="form-input" value={form.gratitude}
                  onChange={(e) => setForm({ ...form, gratitude: e.target.value })} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">{t('Mood.journal_entry')}</label>
              <textarea className="form-input" rows={3} value={form.journal_entry}
                onChange={(e) => setForm({ ...form, journal_entry: e.target.value })} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Mood.emotions')}</label>
                <input className="form-input" placeholder={t('Mood.e_g_anxious_happy_frustrated')}
                  value={form.emotions}
                  onChange={(e) => setForm({ ...form, emotions: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Mood.triggers')}</label>
                <input className="form-input" placeholder={t('Mood.what_triggered_these_emotions')}
                  value={form.triggers}
                  onChange={(e) => setForm({ ...form, triggers: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Mood.coping_strategies')}</label>
                <input className="form-input" placeholder={t('Mood.e_g_meditation_exercise_talking')}
                  value={form.coping_strategies}
                  onChange={(e) => setForm({ ...form, coping_strategies: e.target.value })} />
              </div>
            </div>
            <button className="btn btn-primary" type="submit">{t('Mood.save')}</button>
          </form>
        </div>
      )}

      <div className="card">
        <div style={{ marginBottom: '.75rem', color: 'var(--color-text-secondary)', fontSize: '.8rem' }}>
          {t('Mood.entries_are_editable_but_cannot_be')}
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>{t('Mood.date')}</th>
              <th>{t('Mood.mood')}</th>
              <th>{t('Mood.energy')}</th>
              <th>{t('Mood.stress')}</th>
              <th>{t('Mood.sleep')}</th>
              <th>{t('Mood.journal')}</th>
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
              <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--color-text-secondary)' }}>{t('Mood.no_mood_entries_yet')}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
