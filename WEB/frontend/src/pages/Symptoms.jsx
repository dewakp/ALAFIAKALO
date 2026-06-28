import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Plus, Trash2, Activity } from 'lucide-react';
import BackButton from '../components/BackButton';
import { usePromptPrefill } from '../hooks/usePromptPrefill';

const today = () => new Date().toISOString().split('T')[0];

const EMPTY = {
  log_date: today(),
  symptom_name: '',
  body_part: '',
  severity: '',
  symptom_type: '',
  duration_hours: '',
  triggers: '',
  notes: '',
};

export default function Symptoms() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY });
  const [saving, setSaving] = useState(false);

  // Prompt Hub hand-off: open the add form pre-filled from the prompt.
  usePromptPrefill((prefill) => {
    setForm((f) => ({
      ...f,
      symptom_name: prefill.symptom || prefill.symptom_name || '',
      body_part: prefill.body_part || '',
      notes: prefill.text || prefill.notes || '',
    }));
    setShowForm(true);
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/symptoms/');
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
        log_date: form.log_date,
        symptom_name: form.symptom_name,
        body_part: form.body_part || null,
        symptom_type: form.symptom_type || null,
        triggers: form.triggers || null,
        notes: form.notes || null,
        severity: form.severity !== '' ? parseInt(form.severity) : null,
        duration_hours: form.duration_hours !== '' ? parseFloat(form.duration_hours) : null,
      };
      await api.post('/symptoms/', payload);
      setForm({ ...EMPTY });
      setShowForm(false);
      load();
    } catch (err) {
      alert(apiErrorMessage(err, 'Could not save symptom'));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this symptom log?')) return;
    try {
      await api.delete(`/symptoms/${id}`);
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
          <h1 className="page-title">Symptoms</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowForm((v) => !v)}>
          <Plus size={18} /> Log Symptom
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Date</label>
                <input className="form-input" type="date" value={form.log_date}
                  onChange={(e) => update('log_date', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Symptom *</label>
                <input className="form-input" required value={form.symptom_name}
                  placeholder="e.g. headache, knee pain"
                  onChange={(e) => update('symptom_name', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Body part</label>
                <input className="form-input" value={form.body_part}
                  placeholder="e.g. head, left knee"
                  onChange={(e) => update('body_part', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Severity (1-10)</label>
                <input className="form-input" type="number" min="1" max="10" value={form.severity}
                  onChange={(e) => update('severity', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Type</label>
                <input className="form-input" value={form.symptom_type}
                  placeholder="pain, nausea, fatigue…"
                  onChange={(e) => update('symptom_type', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Duration (hours)</label>
                <input className="form-input" type="number" step="0.5" min="0" value={form.duration_hours}
                  onChange={(e) => update('duration_hours', e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Triggers</label>
              <input className="form-input" value={form.triggers}
                placeholder="what makes it worse?"
                onChange={(e) => update('triggers', e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <textarea className="form-input" rows={2} value={form.notes}
                onChange={(e) => update('notes', e.target.value)} />
            </div>
            <button className="btn btn-primary" type="submit" disabled={saving || !form.symptom_name}>
              {saving ? 'Saving…' : 'Save Symptom'}
            </button>
          </form>
        </div>
      )}

      {loading ? (
        <div className="card">Loading…</div>
      ) : logs.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
          <Activity size={28} style={{ opacity: 0.5 }} />
          <p>No symptoms logged yet.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {logs.map((s) => (
            <div className="card" key={s.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <strong>{s.symptom_name}</strong>
                {s.severity != null && (
                  <span style={{ marginLeft: 8, fontSize: '.75rem', padding: '1px 8px', borderRadius: 10, background: 'var(--primary)', color: '#fff' }}>
                    severity {s.severity}/10
                  </span>
                )}
                <div style={{ fontSize: '.8rem', color: 'var(--text-secondary)', marginTop: 2 }}>
                  {s.log_date}{s.body_part ? ` · ${s.body_part}` : ''}{s.symptom_type ? ` · ${s.symptom_type}` : ''}
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
