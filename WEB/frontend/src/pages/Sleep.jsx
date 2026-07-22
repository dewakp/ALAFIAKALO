import { localToday } from '../utils/datetime';
import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Plus, Trash2, Moon } from 'lucide-react';
import BackButton from '../components/BackButton';
import { usePromptPrefill } from '../hooks/usePromptPrefill';

const today = () => localToday();

const EMPTY = {
  sleep_date: today(),
  total_hours: '',
  quality_score: '',
  times_awakened: '',
  bedtime: '',
  wake_time: '',
  notes: '',
};

// Pull "6" out of "I slept 6 hours" if the router didn't extract it.
function hoursFromText(text) {
  if (!text) return '';
  const m = String(text).match(/(\d+(?:\.\d+)?)\s*(?:hours|hrs|hr|h)\b/i);
  return m ? m[1] : '';
}

export default function Sleep() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY });
  const [saving, setSaving] = useState(false);

  // Prompt Hub hand-off: open the add form pre-filled from the prompt.
  usePromptPrefill((prefill) => {
    setForm((f) => ({
      ...f,
      total_hours: prefill.total_hours || prefill.duration_hours || hoursFromText(prefill.text) || '',
      notes: prefill.text || prefill.notes || '',
    }));
    setShowForm(true);
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/sleep/');
      setLogs(data);
    } catch { setLogs([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        sleep_date: form.sleep_date,
        bedtime: form.bedtime || null,
        wake_time: form.wake_time || null,
        notes: form.notes || null,
        total_hours: form.total_hours !== '' ? parseFloat(form.total_hours) : null,
        quality_score: form.quality_score !== '' ? parseInt(form.quality_score) : null,
        times_awakened: form.times_awakened !== '' ? parseInt(form.times_awakened) : null,
      };
      await api.post('/sleep/', payload);
      setForm({ ...EMPTY });
      setShowForm(false);
      load();
    } catch (err) {
      alert(apiErrorMessage(err, 'Could not save sleep log'));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this sleep log?')) return;
    try {
      await api.delete(`/sleep/${id}`);
      load();
    } catch (err) {
      alert(apiErrorMessage(err, 'Could not delete'));
    }
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Sleep</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm((v) => !v)}>
          <Plus size={18} /> Log Sleep
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Date</label>
                <input className="form-input" type="date" value={form.sleep_date}
                  onChange={(e) => update('sleep_date', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Total hours</label>
                <input className="form-input" type="number" step="0.25" min="0" max="24" value={form.total_hours}
                  placeholder="e.g. 7.5"
                  onChange={(e) => update('total_hours', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Quality (1-10)</label>
                <input className="form-input" type="number" min="1" max="10" value={form.quality_score}
                  onChange={(e) => update('quality_score', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Bedtime</label>
                <input className="form-input" type="time" value={form.bedtime}
                  onChange={(e) => update('bedtime', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Wake time</label>
                <input className="form-input" type="time" value={form.wake_time}
                  onChange={(e) => update('wake_time', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Times awakened</label>
                <input className="form-input" type="number" min="0" value={form.times_awakened}
                  onChange={(e) => update('times_awakened', e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <textarea className="form-input" rows={2} value={form.notes}
                onChange={(e) => update('notes', e.target.value)} />
            </div>
            <button className="btn btn-primary" type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Save Sleep'}
            </button>
          </form>
        </div>
      )}

      {loading ? (
        <div className="card">Loading…</div>
      ) : logs.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
          <Moon size={28} style={{ opacity: 0.5 }} />
          <p>No sleep logged yet.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {logs.map((s) => (
            <div className="card" key={s.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <strong>{s.total_hours != null ? `${s.total_hours} h` : 'Sleep'}</strong>
                {s.quality_score != null && (
                  <span style={{ marginLeft: 8, fontSize: '.75rem', padding: '1px 8px', borderRadius: 10, background: 'var(--primary)', color: '#fff' }}>
                    quality {s.quality_score}/10
                  </span>
                )}
                <div style={{ fontSize: '.8rem', color: 'var(--text-secondary)', marginTop: 2 }}>
                  {s.sleep_date}
                  {s.times_awakened != null ? ` · woke ${s.times_awakened}×` : ''}
                  {s.bedtime ? ` · bed ${s.bedtime}` : ''}
                </div>
                {s.notes && <div style={{ fontSize: '.85rem', marginTop: 4 }}>{s.notes}</div>}
              </div>
              <button className="btn btn-danger btn-sm" onClick={() => handleDelete(s.id)} title="Delete">
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
