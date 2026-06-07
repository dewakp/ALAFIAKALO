import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { Plus, Trash2, Droplets, AlertCircle } from 'lucide-react';
import BackButton from '../components/BackButton';

const today = () => new Date().toISOString().split('T')[0];
const nowTime = () => new Date().toTimeString().slice(0, 5);

/* ─── Bristol Scale descriptions ─── */
const BRISTOL = [
  { value: 1, label: 'Type 1 — Separate hard lumps' },
  { value: 2, label: 'Type 2 — Sausage-shaped, lumpy' },
  { value: 3, label: 'Type 3 — Sausage with cracks' },
  { value: 4, label: 'Type 4 — Smooth, soft sausage' },
  { value: 5, label: 'Type 5 — Soft blobs with clear edges' },
  { value: 6, label: 'Type 6 — Fluffy pieces, mushy' },
  { value: 7, label: 'Type 7 — Entirely liquid' },
];

const BOWEL_COLORS = ['Brown', 'Dark brown', 'Light brown', 'Yellow', 'Green', 'Black', 'Red', 'White/Gray'];
const URINE_COLORS = ['Pale yellow', 'Yellow', 'Dark yellow', 'Amber/Orange', 'Pink/Red', 'Brown', 'Clear', 'Blue/Green'];
const URINE_CLARITY = ['Clear', 'Slightly cloudy', 'Cloudy', 'Very cloudy'];

/* ─── Default form states ─── */
const defaultBowel = () => ({
  log_date: today(), log_time: nowTime(), bristol_scale: '', color: '',
  consistency: '', size: '', blood_present: false, mucus_present: false,
  undigested_food: false, pain_level: '', straining: false, urgency: false,
  duration_minutes: '', associated_symptoms: '', notes: '',
});

const defaultUrination = () => ({
  log_date: today(), log_time: nowTime(), color: '', clarity: '',
  volume_ml: '', stream_strength: '', pain_level: '', burning_sensation: false,
  urgency: false, frequency_increased: false, blood_present: false,
  nighttime: false, notes: '',
});

const defaultVomiting = () => ({
  log_date: today(), log_time: nowTime(), volume: '', color: '',
  consistency: '', contains_food: false, contains_bile: false, contains_blood: false,
  nausea_before: false, nausea_after: false, projectile: false, trigger: '',
  time_since_last_meal_hours: '', relief_after: false, fever: false,
  diarrhea: false, headache: false, dizziness: false, notes: '',
});

/* ─── Reusable checkbox field ─── */
function CheckField({ label, value, onChange }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
      <input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

/* ─── Number / text field ─── */
function Field({ label, type = 'text', value, onChange, placeholder, min, max }) {
  return (
    <div className="form-group">
      <label className="form-label">{label}</label>
      <input
        className="form-input"
        type={type}
        value={value}
        placeholder={placeholder}
        min={min}
        max={max}
        onChange={e => onChange(e.target.value)}
      />
    </div>
  );
}

/* ─── Select field ─── */
function SelectField({ label, value, onChange, options, placeholder }) {
  return (
    <div className="form-group">
      <label className="form-label">{label}</label>
      <select className="form-input" value={value} onChange={e => onChange(e.target.value)}>
        <option value="">{placeholder || 'Select…'}</option>
        {options.map(o => (
          <option key={typeof o === 'object' ? o.value : o} value={typeof o === 'object' ? o.value : o}>
            {typeof o === 'object' ? o.label : o}
          </option>
        ))}
      </select>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  BOWEL TAB                                                                  */
/* ═══════════════════════════════════════════════════════════════════════════ */
function BowelTab() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(defaultBowel());
  const [saving, setSaving] = useState(false);
  const [filterStart, setFilterStart] = useState('');
  const [filterEnd, setFilterEnd] = useState('');

  const f = (key) => (val) => setForm(p => ({ ...p, [key]: val }));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterStart) params.start_date = filterStart;
      if (filterEnd) params.end_date = filterEnd;
      const { data } = await api.get('/elimination/bowel', { params });
      setLogs(data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [filterStart, filterEnd]);

  useEffect(() => { load(); }, [load]);

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        log_time: form.log_time || null,
        bristol_scale: form.bristol_scale ? parseInt(form.bristol_scale) : null,
        pain_level: form.pain_level !== '' ? parseInt(form.pain_level) : null,
        duration_minutes: form.duration_minutes !== '' ? parseInt(form.duration_minutes) : null,
        color: form.color || null,
        consistency: form.consistency || null,
        size: form.size || null,
        associated_symptoms: form.associated_symptoms || null,
        notes: form.notes || null,
      };
      await api.post('/elimination/bowel', payload);
      setForm(defaultBowel());
      setShowForm(false);
      await load();
    } catch { /* ignore */ } finally { setSaving(false); }
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete this entry?')) return;
    await api.delete(`/elimination/bowel/${id}`);
    await load();
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>Bowel Movements</h2>
        <button className="btn btn-primary" onClick={() => setShowForm(s => !s)}>
          <Plus size={16} /> Log Entry
        </button>
      </div>

      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.875rem' }}>
          From&nbsp;
          <input className="form-input" type="date" value={filterStart} onChange={e => setFilterStart(e.target.value)} style={{ width: 150 }} />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.875rem' }}>
          To&nbsp;
          <input className="form-input" type="date" value={filterEnd} onChange={e => setFilterEnd(e.target.value)} style={{ width: 150 }} />
        </label>
        {(filterStart || filterEnd) && (
          <button className="btn btn-secondary" style={{ fontSize: '0.8rem', padding: '4px 10px' }}
            onClick={() => { setFilterStart(''); setFilterEnd(''); }}>
            Clear
          </button>
        )}
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <Field label="Date" type="date" value={form.log_date} onChange={f('log_date')} />
              <Field label="Time" type="time" value={form.log_time} onChange={f('log_time')} />
              <SelectField
                label="Bristol Scale (stool type)"
                value={form.bristol_scale}
                onChange={f('bristol_scale')}
                options={BRISTOL}
              />
            </div>
            <div className="form-row">
              <SelectField label="Color" value={form.color} onChange={f('color')} options={BOWEL_COLORS} />
              <Field label="Consistency" value={form.consistency} onChange={f('consistency')} placeholder="e.g., hard, soft, liquid" />
              <Field label="Size" value={form.size} onChange={f('size')} placeholder="e.g., small, medium, large" />
            </div>
            <div className="form-row">
              <Field label="Pain Level (0–10)" type="number" value={form.pain_level} onChange={f('pain_level')} min="0" max="10" />
              <Field label="Duration (minutes)" type="number" value={form.duration_minutes} onChange={f('duration_minutes')} min="0" />
              <Field label="Associated Symptoms" value={form.associated_symptoms} onChange={f('associated_symptoms')} placeholder="e.g., cramps, bloating" />
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', margin: '0.75rem 0' }}>
              <CheckField label="Blood present" value={form.blood_present} onChange={f('blood_present')} />
              <CheckField label="Mucus present" value={form.mucus_present} onChange={f('mucus_present')} />
              <CheckField label="Undigested food" value={form.undigested_food} onChange={f('undigested_food')} />
              <CheckField label="Straining" value={form.straining} onChange={f('straining')} />
              <CheckField label="Urgency" value={form.urgency} onChange={f('urgency')} />
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <textarea className="form-input" rows={2} value={form.notes} onChange={e => f('notes')(e.target.value)} />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="submit" disabled={saving}>
                {saving ? 'Saving…' : 'Save Entry'}
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <p style={{ color: 'var(--color-text-secondary)' }}>Loading…</p>
      ) : logs.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: '2rem' }}>
          No bowel movement entries yet.
        </div>
      ) : (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Time</th>
                <th>Bristol Type</th>
                <th>Color</th>
                <th>Pain</th>
                <th>Flags</th>
                <th>Notes</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {logs.map(l => (
                <tr key={l.id}>
                  <td>{l.log_date}</td>
                  <td>{l.log_time ?? '—'}</td>
                  <td>{l.bristol_scale ? `Type ${l.bristol_scale}` : '—'}</td>
                  <td>{l.color ?? '—'}</td>
                  <td>{l.pain_level != null ? l.pain_level : '—'}</td>
                  <td style={{ fontSize: '0.8rem' }}>
                    {l.blood_present ? '🔴 Blood ' : ''}
                    {l.mucus_present ? '🟡 Mucus ' : ''}
                    {l.urgency ? '⚡ Urgent ' : ''}
                    {!l.blood_present && !l.mucus_present && !l.urgency ? '—' : ''}
                  </td>
                  <td style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {l.notes ?? '—'}
                  </td>
                  <td>
                    <button className="btn btn-danger btn-sm" onClick={() => handleDelete(l.id)}>
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  URINATION TAB                                                              */
/* ═══════════════════════════════════════════════════════════════════════════ */
function UrinationTab() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(defaultUrination());
  const [saving, setSaving] = useState(false);
  const [filterStart, setFilterStart] = useState('');
  const [filterEnd, setFilterEnd] = useState('');

  const f = (key) => (val) => setForm(p => ({ ...p, [key]: val }));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterStart) params.start_date = filterStart;
      if (filterEnd) params.end_date = filterEnd;
      const { data } = await api.get('/elimination/urination', { params });
      setLogs(data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [filterStart, filterEnd]);

  useEffect(() => { load(); }, [load]);

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        log_time: form.log_time || null,
        pain_level: form.pain_level !== '' ? parseInt(form.pain_level) : null,
        volume_ml: form.volume_ml !== '' ? parseInt(form.volume_ml) : null,
        color: form.color || null,
        clarity: form.clarity || null,
        stream_strength: form.stream_strength || null,
        notes: form.notes || null,
      };
      await api.post('/elimination/urination', payload);
      setForm(defaultUrination());
      setShowForm(false);
      await load();
    } catch { /* ignore */ } finally { setSaving(false); }
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete this entry?')) return;
    await api.delete(`/elimination/urination/${id}`);
    await load();
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Droplets size={20} /> Urination
        </h2>
        <button className="btn btn-primary" onClick={() => setShowForm(s => !s)}>
          <Plus size={16} /> Log Entry
        </button>
      </div>

      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.875rem' }}>
          From&nbsp;
          <input className="form-input" type="date" value={filterStart} onChange={e => setFilterStart(e.target.value)} style={{ width: 150 }} />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.875rem' }}>
          To&nbsp;
          <input className="form-input" type="date" value={filterEnd} onChange={e => setFilterEnd(e.target.value)} style={{ width: 150 }} />
        </label>
        {(filterStart || filterEnd) && (
          <button className="btn btn-secondary" style={{ fontSize: '0.8rem', padding: '4px 10px' }}
            onClick={() => { setFilterStart(''); setFilterEnd(''); }}>
            Clear
          </button>
        )}
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <Field label="Date" type="date" value={form.log_date} onChange={f('log_date')} />
              <Field label="Time" type="time" value={form.log_time} onChange={f('log_time')} />
              <Field label="Volume (ml)" type="number" value={form.volume_ml} onChange={f('volume_ml')} min="0" />
            </div>
            <div className="form-row">
              <SelectField label="Color" value={form.color} onChange={f('color')} options={URINE_COLORS} />
              <SelectField label="Clarity" value={form.clarity} onChange={f('clarity')} options={URINE_CLARITY} />
              <Field label="Stream Strength" value={form.stream_strength} onChange={f('stream_strength')} placeholder="e.g., weak, normal, strong" />
            </div>
            <div className="form-row">
              <Field label="Pain Level (0–10)" type="number" value={form.pain_level} onChange={f('pain_level')} min="0" max="10" />
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', margin: '0.75rem 0' }}>
              <CheckField label="Burning sensation" value={form.burning_sensation} onChange={f('burning_sensation')} />
              <CheckField label="Urgency" value={form.urgency} onChange={f('urgency')} />
              <CheckField label="Frequency increased" value={form.frequency_increased} onChange={f('frequency_increased')} />
              <CheckField label="Blood present" value={form.blood_present} onChange={f('blood_present')} />
              <CheckField label="Nighttime urination" value={form.nighttime} onChange={f('nighttime')} />
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <textarea className="form-input" rows={2} value={form.notes} onChange={e => f('notes')(e.target.value)} />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="submit" disabled={saving}>
                {saving ? 'Saving…' : 'Save Entry'}
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <p style={{ color: 'var(--color-text-secondary)' }}>Loading…</p>
      ) : logs.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: '2rem' }}>
          No urination entries yet.
        </div>
      ) : (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Time</th>
                <th>Color</th>
                <th>Clarity</th>
                <th>Volume (ml)</th>
                <th>Pain</th>
                <th>Flags</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {logs.map(l => (
                <tr key={l.id}>
                  <td>{l.log_date}</td>
                  <td>{l.log_time ?? '—'}</td>
                  <td>{l.color ?? '—'}</td>
                  <td>{l.clarity ?? '—'}</td>
                  <td>{l.volume_ml ?? '—'}</td>
                  <td>{l.pain_level != null ? l.pain_level : '—'}</td>
                  <td style={{ fontSize: '0.8rem' }}>
                    {l.blood_present ? '🔴 Blood ' : ''}
                    {l.burning_sensation ? '🔥 Burning ' : ''}
                    {l.urgency ? '⚡ Urgent ' : ''}
                    {!l.blood_present && !l.burning_sensation && !l.urgency ? '—' : ''}
                  </td>
                  <td>
                    <button className="btn btn-danger btn-sm" onClick={() => handleDelete(l.id)}>
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  VOMITING TAB                                                               */
/* ═══════════════════════════════════════════════════════════════════════════ */
function VomitingTab() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(defaultVomiting());
  const [saving, setSaving] = useState(false);
  const [filterStart, setFilterStart] = useState('');
  const [filterEnd, setFilterEnd] = useState('');

  const f = (key) => (val) => setForm(p => ({ ...p, [key]: val }));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterStart) params.start_date = filterStart;
      if (filterEnd) params.end_date = filterEnd;
      const { data } = await api.get('/elimination/vomiting', { params });
      setLogs(data);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, [filterStart, filterEnd]);

  useEffect(() => { load(); }, [load]);

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        log_time: form.log_time || null,
        time_since_last_meal_hours: form.time_since_last_meal_hours !== '' ? parseFloat(form.time_since_last_meal_hours) : null,
        volume: form.volume || null,
        color: form.color || null,
        consistency: form.consistency || null,
        trigger: form.trigger || null,
        notes: form.notes || null,
      };
      await api.post('/elimination/vomiting', payload);
      setForm(defaultVomiting());
      setShowForm(false);
      await load();
    } catch { /* ignore */ } finally { setSaving(false); }
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete this entry?')) return;
    await api.delete(`/elimination/vomiting/${id}`);
    await load();
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertCircle size={20} /> Vomiting
        </h2>
        <button className="btn btn-primary" onClick={() => setShowForm(s => !s)}>
          <Plus size={16} /> Log Entry
        </button>
      </div>

      <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.875rem' }}>
          From&nbsp;
          <input className="form-input" type="date" value={filterStart} onChange={e => setFilterStart(e.target.value)} style={{ width: 150 }} />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.875rem' }}>
          To&nbsp;
          <input className="form-input" type="date" value={filterEnd} onChange={e => setFilterEnd(e.target.value)} style={{ width: 150 }} />
        </label>
        {(filterStart || filterEnd) && (
          <button className="btn btn-secondary" style={{ fontSize: '0.8rem', padding: '4px 10px' }}
            onClick={() => { setFilterStart(''); setFilterEnd(''); }}>
            Clear
          </button>
        )}
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <Field label="Date" type="date" value={form.log_date} onChange={f('log_date')} />
              <Field label="Time" type="time" value={form.log_time} onChange={f('log_time')} />
              <Field label="Volume" value={form.volume} onChange={f('volume')} placeholder="e.g., small, large, 200ml" />
            </div>
            <div className="form-row">
              <Field label="Color" value={form.color} onChange={f('color')} placeholder="e.g., yellow, green, brown" />
              <Field label="Consistency" value={form.consistency} onChange={f('consistency')} placeholder="e.g., liquid, chunky" />
              <Field label="Trigger" value={form.trigger} onChange={f('trigger')} placeholder="e.g., food, smell, motion" />
            </div>
            <div className="form-row">
              <Field label="Hours since last meal" type="number" value={form.time_since_last_meal_hours} onChange={f('time_since_last_meal_hours')} min="0" />
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', margin: '0.75rem 0' }}>
              <CheckField label="Contains food" value={form.contains_food} onChange={f('contains_food')} />
              <CheckField label="Contains bile" value={form.contains_bile} onChange={f('contains_bile')} />
              <CheckField label="Contains blood" value={form.contains_blood} onChange={f('contains_blood')} />
              <CheckField label="Nausea before" value={form.nausea_before} onChange={f('nausea_before')} />
              <CheckField label="Nausea after" value={form.nausea_after} onChange={f('nausea_after')} />
              <CheckField label="Projectile" value={form.projectile} onChange={f('projectile')} />
              <CheckField label="Relief after" value={form.relief_after} onChange={f('relief_after')} />
              <CheckField label="Fever" value={form.fever} onChange={f('fever')} />
              <CheckField label="Diarrhea" value={form.diarrhea} onChange={f('diarrhea')} />
              <CheckField label="Headache" value={form.headache} onChange={f('headache')} />
              <CheckField label="Dizziness" value={form.dizziness} onChange={f('dizziness')} />
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <textarea className="form-input" rows={2} value={form.notes} onChange={e => f('notes')(e.target.value)} />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" type="submit" disabled={saving}>
                {saving ? 'Saving…' : 'Save Entry'}
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <p style={{ color: 'var(--color-text-secondary)' }}>Loading…</p>
      ) : logs.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: '2rem' }}>
          No vomiting entries yet.
        </div>
      ) : (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Time</th>
                <th>Volume</th>
                <th>Color</th>
                <th>Trigger</th>
                <th>Flags</th>
                <th>Notes</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {logs.map(l => (
                <tr key={l.id}>
                  <td>{l.log_date}</td>
                  <td>{l.log_time ?? '—'}</td>
                  <td>{l.volume ?? '—'}</td>
                  <td>{l.color ?? '—'}</td>
                  <td>{l.trigger ?? '—'}</td>
                  <td style={{ fontSize: '0.8rem' }}>
                    {l.contains_blood ? '🔴 Blood ' : ''}
                    {l.contains_bile ? '🟡 Bile ' : ''}
                    {l.fever ? '🌡️ Fever ' : ''}
                    {!l.contains_blood && !l.contains_bile && !l.fever ? '—' : ''}
                  </td>
                  <td style={{ maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {l.notes ?? '—'}
                  </td>
                  <td>
                    <button className="btn btn-danger btn-sm" onClick={() => handleDelete(l.id)}>
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  MAIN PAGE                                                                  */
/* ═══════════════════════════════════════════════════════════════════════════ */
const TABS = [
  { key: 'bowel', label: 'Bowel' },
  { key: 'urination', label: 'Urination' },
  { key: 'vomiting', label: 'Vomiting' },
];

export default function Elimination() {
  const [activeTab, setActiveTab] = useState('bowel');

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Elimination</h1>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{
        display: 'flex', borderBottom: '2px solid var(--color-border)',
        marginBottom: '1.5rem', gap: 4,
      }}>
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              padding: '8px 20px', border: 'none', background: 'none', cursor: 'pointer',
              fontWeight: activeTab === t.key ? 700 : 400,
              borderBottom: activeTab === t.key ? '2px solid var(--color-primary)' : '2px solid transparent',
              color: activeTab === t.key ? 'var(--color-primary)' : 'var(--color-text-secondary)',
              marginBottom: -2,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === 'bowel' && <BowelTab />}
      {activeTab === 'urination' && <UrinationTab />}
      {activeTab === 'vomiting' && <VomitingTab />}
    </div>
  );
}
