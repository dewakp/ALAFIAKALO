import { localToday } from '../utils/datetime';
import { detachFile } from '../utils/fileInput';
import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Plus, Trash2, Activity, Camera, Loader2 } from 'lucide-react';
import BackButton from '../components/BackButton';
import { usePromptPrefill } from '../hooks/usePromptPrefill';
import { t } from '../i18n';

const today = () => localToday();

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
  const [analyzing, setAnalyzing] = useState(false);
  const [aiNote, setAiNote] = useState('');

  /* Photo → AI: describe a visible symptom (rash, swelling, wound…) and
     prefill the form. The photo itself is not stored. */
  async function analyzePhoto(e) {
    // Detach BEFORE clearing: the reset below strips the data off the
    // original File in WebKit, and FileReader would then read nothing.
    const file = await detachFile(e.target.files);
    e.target.value = '';
    if (!file) return;
    setAnalyzing(true); setAiNote('');
    try {
      const image_base64 = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.onerror = () => reject(new Error('Could not read the photo'));
        r.readAsDataURL(file);
      });
      const { data } = await api.post('/image-ai/symptom-from-image',
        { image_base64 }, { timeout: 180000 });
      const s = data.suggested || {};
      setForm((f) => ({
        ...f,
        symptom_name: s.symptom_name || f.symptom_name,
        body_part: s.body_part || f.body_part,
        symptom_type: s.symptom_type || f.symptom_type,
        notes: data.description ? `AI photo description: ${data.description}` : f.notes,
      }));
      setAiNote(data.disclaimer || '');
      setShowForm(true);
    } catch (err) {
      alert(apiErrorMessage(err, t('Symptoms.could_not_analyze_the_photo')));
    } finally { setAnalyzing(false); }
  }

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
      alert(apiErrorMessage(err, t('Symptoms.could_not_save_symptom')));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    if (!confirm(t('Symptoms.delete_this_symptom_log'))) return;
    try {
      await api.delete(`/symptoms/${id}`);
      load();
    } catch (err) {
      alert(apiErrorMessage(err, t('Symptoms.could_not_delete')));
    }
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">{t('Symptoms.symptoms')}</h1>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <label className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', margin: 0 }}>
            {analyzing
              ? <Loader2 size={16} style={{ animation: 'spin-anim 1s linear infinite' }} />
              : <Camera size={16} />}
            {analyzing ? 'Analyzing…' : 'From Photo'}
            <input type="file" accept="image/*" capture="environment" onChange={analyzePhoto}
              style={{ display: 'none' }} disabled={analyzing} />
          </label>
          <button className="btn btn-primary" onClick={() => setShowForm((v) => !v)}>
            <Plus size={18} /> {t('Symptoms.log_symptom')}
          </button>
        </div>
      </div>

      {aiNote && (
        <div style={{ marginBottom: '1rem', padding: '8px 12px', borderRadius: 8,
          background: 'rgba(245,158,11,.12)', fontSize: '.85rem' }}>
          {aiNote}
        </div>
      )}

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Symptoms.date')}</label>
                <input className="form-input" type="date" value={form.log_date}
                  onChange={(e) => update('log_date', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Symptoms.symptom')}</label>
                <input className="form-input" required value={form.symptom_name}
                  placeholder={t('Symptoms.e_g_headache_knee_pain')}
                  onChange={(e) => update('symptom_name', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Symptoms.body_part')}</label>
                <input className="form-input" value={form.body_part}
                  placeholder={t('Symptoms.e_g_head_left_knee')}
                  onChange={(e) => update('body_part', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Symptoms.severity_1_10')}</label>
                <input className="form-input" type="number" min="1" max="10" value={form.severity}
                  onChange={(e) => update('severity', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Symptoms.type')}</label>
                <input className="form-input" value={form.symptom_type}
                  placeholder={t('Symptoms.pain_nausea_fatigue')}
                  onChange={(e) => update('symptom_type', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Symptoms.duration_hours')}</label>
                <input className="form-input" type="number" step="0.5" min="0" value={form.duration_hours}
                  onChange={(e) => update('duration_hours', e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">{t('Symptoms.triggers')}</label>
              <input className="form-input" value={form.triggers}
                placeholder={t('Symptoms.what_makes_it_worse')}
                onChange={(e) => update('triggers', e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">{t('Symptoms.notes')}</label>
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
        <div className="card">{t('Symptoms.loading')}</div>
      ) : logs.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
          <Activity size={28} style={{ opacity: 0.5 }} />
          <p>{t('Symptoms.no_symptoms_logged_yet')}</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {logs.map((s) => (
            <div className="card" key={s.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <strong>{s.symptom_name}</strong>
                {s.severity != null && (
                  <span style={{ marginLeft: 8, fontSize: '.75rem', padding: '1px 8px', borderRadius: 10, background: 'var(--primary)', color: '#fff' }}>
                    {t('Symptoms.severity_10', { severity: s.severity })}
                  </span>
                )}
                <div style={{ fontSize: '.8rem', color: 'var(--text-secondary)', marginTop: 2 }}>
                  {s.log_date}{s.body_part ? ` · ${s.body_part}` : ''}{s.symptom_type ? ` · ${s.symptom_type}` : ''}
                </div>
                {s.notes && <div style={{ fontSize: '.85rem', marginTop: 4 }}>{s.notes}</div>}
              </div>
              <button className="btn btn-danger btn-sm" onClick={() => handleDelete(s.id)} title={t('Symptoms.delete')}>
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
