import { useState, useEffect, useCallback, useMemo } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Plus, Trash2, Layers, ChevronLeft, ChevronRight } from 'lucide-react';
import BackButton from '../components/BackButton';
import { usePromptPrefill } from '../hooks/usePromptPrefill';

// Unified Elimination Log (Basis + ALAFIA.app reference): one form with an
// Event Type selector, a calendar with entry-dots, and a per-date timeline.
// The event type (poop / urine / vomit) is captured AND shown on every entry.

const EVENT_OPTIONS = [
  { value: 'poop', label: 'Poop' },
  { value: 'urine', label: 'Urination' },
  { value: 'vomit', label: 'Vomiting' },
];
const EVENT_LABEL = { poop: 'Poop', urine: 'Urination', vomit: 'Vomiting' };

const todayStr = () => new Date().toISOString().split('T')[0];
const nowTime = () => new Date().toTimeString().slice(0, 5);
const fmtLong = (d) => new Date(d + 'T12:00:00').toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
const num = (v) => (v !== '' && v != null ? Number(v) : null);
const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

const EMPTY = {
  event_type: 'poop', log_date: todayStr(), log_time: nowTime(),
  pre_event_weight_kg: '', post_event_weight_kg: '', description: '', image_uri: '',
};

export default function Elimination() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ ...EMPTY });
  const [saving, setSaving] = useState(false);
  const [selectedDate, setSelectedDate] = useState(todayStr());
  const [viewMonth, setViewMonth] = useState(() => { const d = new Date(); d.setDate(1); return d; });

  usePromptPrefill((prefill) => {
    setForm((f) => ({ ...f, description: prefill.text || prefill.description || f.description }));
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/elimination/all');
      setEntries(data);
    } catch { setEntries([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  function update(field, value) { setForm((f) => ({ ...f, [field]: value })); }

  function handleImage(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => update('image_uri', reader.result?.toString() || '');
    reader.readAsDataURL(file);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/elimination/all', {
        event_type: form.event_type,
        log_date: form.log_date,
        log_time: form.log_time || null,
        pre_event_weight_kg: num(form.pre_event_weight_kg),
        post_event_weight_kg: num(form.post_event_weight_kg),
        description: form.description || null,
        image_uri: form.image_uri || null,
      });
      setForm({ ...EMPTY, event_type: form.event_type, log_date: form.log_date });
      setSelectedDate(form.log_date);
      load();
    } catch (err) {
      alert(apiErrorMessage(err, 'Could not save entry'));
    } finally { setSaving(false); }
  }

  async function handleDelete(entry) {
    if (!confirm('Delete this entry?')) return;
    try { await api.delete(`/elimination/all/${entry.event_type}/${entry.id}`); load(); }
    catch (err) { alert(apiErrorMessage(err, 'Could not delete')); }
  }

  // Dates (YYYY-MM-DD) that have at least one entry → calendar dots.
  const datesWithEntries = useMemo(
    () => new Set(entries.map((e) => e.log_date)), [entries]);

  const dayEntries = useMemo(
    () => entries
      .filter((e) => e.log_date === selectedDate)
      .sort((a, b) => (a.log_time || '') < (b.log_time || '') ? -1 : 1),
    [entries, selectedDate]);

  // Build the month grid.
  const cells = useMemo(() => {
    const y = viewMonth.getFullYear(), m = viewMonth.getMonth();
    const first = new Date(y, m, 1).getDay();
    const days = new Date(y, m + 1, 0).getDate();
    const out = [];
    for (let i = 0; i < first; i++) out.push(null);
    for (let d = 1; d <= days; d++) {
      const ds = `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      out.push({ d, ds });
    }
    return out;
  }, [viewMonth]);

  function shiftMonth(n) { setViewMonth((v) => new Date(v.getFullYear(), v.getMonth() + n, 1)); }
  const monthLabel = viewMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Layers size={22} /> Elimination Log
          </h1>
        </div>
      </div>
      <p style={{ color: 'var(--text-secondary)', marginTop: -8, marginBottom: 16 }}>
        Track poop, urination, and vomiting events, with optional weights and images.
      </p>

      {/* ── Add New Log Entry ── */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 0 }}>
          <Plus size={18} /> Add New Log Entry
        </h3>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Date</label>
              <input className="form-input" type="date" value={form.log_date} onChange={(e) => update('log_date', e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Time</label>
              <input className="form-input" type="time" value={form.log_time} onChange={(e) => update('log_time', e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Event Type</label>
              <select className="form-input" value={form.event_type} onChange={(e) => update('event_type', e.target.value)}>
                {EVENT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Pre-Event Weight (kg, optional)</label>
              <input className="form-input" type="number" step="0.1" placeholder="e.g., 68.5"
                value={form.pre_event_weight_kg} onChange={(e) => update('pre_event_weight_kg', e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Post-Event Weight (kg, optional)</label>
              <input className="form-input" type="number" step="0.1" placeholder="e.g., 68.0"
                value={form.post_event_weight_kg} onChange={(e) => update('post_event_weight_kg', e.target.value)} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Description (optional)</label>
            <textarea className="form-input" rows={2}
              placeholder="e.g., Bristol type 4, normal color for poop; Clear, light yellow for urine…"
              value={form.description} onChange={(e) => update('description', e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Attach Image (optional)</label>
            <input className="form-input" type="file" accept="image/*" capture="environment" onChange={handleImage} />
          </div>
          <button className="btn btn-primary" type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Add Entry'}
          </button>
        </form>
      </div>

      {/* ── Calendar + per-date entries ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 360px) 1fr', gap: 16, alignItems: 'start' }}>
        {/* Calendar */}
        <div className="card">
          <h3 style={{ marginTop: 0 }}>📅 Select Date</h3>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <button type="button" className="btn btn-outline btn-sm" onClick={() => shiftMonth(-1)}><ChevronLeft size={16} /></button>
            <strong>{monthLabel}</strong>
            <button type="button" className="btn btn-outline btn-sm" onClick={() => shiftMonth(1)}><ChevronRight size={16} /></button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2, textAlign: 'center' }}>
            {WEEKDAYS.map((w) => (
              <div key={w} style={{ fontSize: '.72rem', color: 'var(--text-secondary)', padding: 4 }}>{w}</div>
            ))}
            {cells.map((c, i) => c === null ? <div key={`b${i}`} /> : (
              <button
                key={c.ds}
                type="button"
                onClick={() => setSelectedDate(c.ds)}
                style={{
                  position: 'relative', padding: '8px 0', border: 'none', borderRadius: 8, cursor: 'pointer',
                  background: c.ds === selectedDate ? 'var(--primary)' : 'transparent',
                  color: c.ds === selectedDate ? '#fff' : 'inherit', fontSize: '.85rem',
                }}
              >
                {c.d}
                {datesWithEntries.has(c.ds) && (
                  <span style={{
                    position: 'absolute', bottom: 3, left: '50%', transform: 'translateX(-50%)',
                    width: 5, height: 5, borderRadius: '50%',
                    background: c.ds === selectedDate ? '#fff' : 'var(--primary)',
                  }} />
                )}
              </button>
            ))}
          </div>
          <p style={{ fontSize: '.72rem', color: 'var(--text-secondary)', marginTop: 8, marginBottom: 0 }}>
            Dates with a <span style={{ color: 'var(--primary)' }}>●</span> have logged entries.
          </p>
        </div>

        {/* Entries for selected date */}
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Log Entries for {fmtLong(selectedDate)}</h3>
          {loading ? <p>Loading…</p> : dayEntries.length === 0 ? (
            <p style={{ color: 'var(--text-secondary)' }}>No entries for this date.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {dayEntries.map((e) => (
                <div key={`${e.event_type}-${e.id}`} className="card" style={{ margin: 0, border: '1px solid var(--border, #e5e7eb)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <strong style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Layers size={15} style={{ color: 'var(--primary)' }} />
                      {EVENT_LABEL[e.event_type] || e.event_type} At {e.log_time ? String(e.log_time).slice(0, 5) : '—'}
                    </strong>
                    <button className="btn btn-danger btn-sm" onClick={() => handleDelete(e)} title="Delete"><Trash2 size={14} /></button>
                  </div>
                  <div style={{ fontSize: '.85rem', marginTop: 6, lineHeight: 1.6 }}>
                    {e.pre_event_weight_kg != null && <div><strong>Pre-Weight:</strong> {e.pre_event_weight_kg} kg</div>}
                    {e.post_event_weight_kg != null && <div><strong>Post-Weight:</strong> {e.post_event_weight_kg} kg</div>}
                    {e.description && <div><strong>Description:</strong> {e.description}</div>}
                  </div>
                  {e.image_uri && (
                    <img src={e.image_uri} alt="attachment" style={{ maxWidth: 160, borderRadius: 8, marginTop: 8 }} />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
