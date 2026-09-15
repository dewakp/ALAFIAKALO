import { useState } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Camera, Pill, ShieldCheck, Upload, AlertTriangle, CheckCircle } from 'lucide-react';
import BackButton from '../components/BackButton';
import { t } from '../i18n';

/* Read a File as a data-URL. Uploads go as JSON {image_base64} rather than
   multipart — Safari's multipart encoding has proven flaky through the proxy,
   and base64 JSON behaves identically in every browser. */
function fileToDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Could not read the selected file'));
    reader.readAsDataURL(file);
  });
}

/* Local vision models on CPU can take a while — give analysis a long leash. */
const ANALYZE_TIMEOUT_MS = 180000;

const tabs = [
  { key: 'nutrition', get label() { return t('ImageAI.nutrition_from_image'); }, icon: Camera },
  { key: 'medication', get label() { return t('ImageAI.medication_from_image'); }, icon: Pill },
  { key: 'dosage', get label() { return t('ImageAI.dosage_verification'); }, icon: ShieldCheck },
];

export default function ImageAI() {
  const [activeTab, setActiveTab] = useState('nutrition');

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">{t('ImageAI.image_ai_tools')}</h1>
        </div>
      </div>
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            className={`btn ${activeTab === key ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab(key)}
          >
            <Icon size={16} /> {label}
          </button>
        ))}
      </div>
      {activeTab === 'nutrition' && <NutritionFromImage />}
      {activeTab === 'medication' && <MedicationFromImage />}
      {activeTab === 'dosage' && <DosageVerification />}
    </div>
  );
}

function NutritionFromImage() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [correction, setCorrection] = useState('');
  const [teaching, setTeaching] = useState(false);

  function handleFile(e) {
    const f = e.target.files[0];
    if (f) {
      setFile(f);
      setPreview(URL.createObjectURL(f));
      setResult(null);
      setCorrection('');
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    try {
      const image_base64 = await fileToDataURL(file);
      const { data } = await api.post('/image-ai/nutrition-from-image', { image_base64 },
        { timeout: ANALYZE_TIMEOUT_MS });
      setResult(data);
      setCorrection((data.food_items || []).map((i) => i.name).join('; '));
    } catch (err) {
      alert(apiErrorMessage(err, t('ImageAI.error_analyzing_image')));
    } finally {
      setLoading(false);
    }
  }

  /* Teach ALAFIA: store the ground-truth foods for this photo (visual memory)
     — the same photo (or a re-shot of the same meal) is recognized instantly
     next time, before any AI model runs. */
  async function handleTeach() {
    if (!file || !correction.trim()) return;
    setTeaching(true);
    try {
      const image_base64 = await fileToDataURL(file);
      const { data } = await api.post('/image-ai/label',
        { image_base64, foods: correction.trim() }, { timeout: ANALYZE_TIMEOUT_MS });
      setResult(data);
    } catch (err) {
      alert(apiErrorMessage(err, t('ImageAI.could_not_save_the_correction')));
    } finally {
      setTeaching(false);
    }
  }

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <h3 style={{ marginBottom: '1rem' }}>{t('ImageAI.identify_food_from_photo')}</h3>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">{t('ImageAI.upload_food_image')}</label>
          <input type="file" accept="image/*" onChange={handleFile} className="form-input" />
        </div>
        {preview && (
          <img src={preview} alt={t('ImageAI.preview')} style={{ maxWidth: 300, borderRadius: 8, marginBottom: '1rem' }} />
        )}
        <button className="btn btn-primary" disabled={!file || loading}>
          <Upload size={16} /> {(loading) ? t('ImageAI.analyzing') : t('ImageAI.analyze')}
        </button>
      </form>

      {result && (
        <div style={{ marginTop: '1.5rem' }}>
          <h4>{t('ImageAI.results')}</h4>
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '0.5rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                <th style={thStyle}>{t('ImageAI.food')}</th>
                <th style={thStyle}>{t('ImageAI.serving')}</th>
                <th style={thStyle}>{t('ImageAI.calories')}</th>
                <th style={thStyle}>{t('ImageAI.protein')}</th>
                <th style={thStyle}>{t('ImageAI.carbs')}</th>
                <th style={thStyle}>{t('ImageAI.fat')}</th>
              </tr>
            </thead>
            <tbody>
              {result.food_items?.map((item, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
                  <td style={tdStyle}>{item.name}</td>
                  <td style={tdStyle}>{item.serving_size}</td>
                  <td style={tdStyle}>{item.calories}</td>
                  <td style={tdStyle}>{item.protein_g}g</td>
                  <td style={tdStyle}>{item.carbs_g}g</td>
                  <td style={tdStyle}>{item.fat_g}g</td>
                </tr>
              ))}
              <tr style={{ fontWeight: 700, borderTop: '2px solid var(--color-primary)' }}>
                <td style={tdStyle} colSpan={2}>{t('ImageAI.total')}</td>
                <td style={tdStyle}>{result.total_calories}</td>
                <td style={tdStyle}>{result.total_protein_g}g</td>
                <td style={tdStyle}>{result.total_carbs_g}g</td>
                <td style={tdStyle}>{result.total_fat_g}g</td>
              </tr>
            </tbody>
          </table>
          {result.confidence_note && (
            <p style={{ marginTop: '0.75rem', color: 'var(--color-text-secondary)', fontSize: '0.85rem' }}>
              {result.confidence_note}
            </p>
          )}
          {result.notes && (
            <p style={{ marginTop: '0.75rem', color: 'var(--color-text-secondary)', fontSize: '0.85rem' }}>
              {result.notes}
            </p>
          )}

          {/* Teach ALAFIA: correct the food list → learned for future photos */}
          <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
            <label className="form-label">{t('ImageAI.not_right_teach_alafia_what_this')}</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input className="form-input" style={{ flex: 1 }} value={correction}
                onChange={(e) => setCorrection(e.target.value)}
                placeholder={t('ImageAI.e_g_beans_in_palm_oil_grilled_chicken')} />
              <button type="button" className="btn btn-secondary" onClick={handleTeach}
                disabled={teaching || !correction.trim()}>
                {teaching ? 'Saving…' : 'Teach'}
              </button>
            </div>
            <p style={{ marginTop: 6, fontSize: '0.78rem', color: 'var(--color-text-secondary)' }}>
              {t('ImageAI.separate_foods_with_semicolons_alafia')}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function MedicationFromImage() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  function handleFile(e) {
    const f = e.target.files[0];
    if (f) { setFile(f); setPreview(URL.createObjectURL(f)); setResult(null); }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    try {
      const image_base64 = await fileToDataURL(file);
      const { data } = await api.post('/image-ai/medication-from-image', { image_base64 },
        { timeout: ANALYZE_TIMEOUT_MS });
      setResult(data);
    } catch (err) {
      alert(apiErrorMessage(err, t('ImageAI.error_analyzing_image')));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <h3 style={{ marginBottom: '1rem' }}>{t('ImageAI.identify_medication_from_photo')}</h3>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">{t('ImageAI.upload_medication_image')}</label>
          <input type="file" accept="image/*" onChange={handleFile} className="form-input" />
        </div>
        {preview && <img src={preview} alt={t('ImageAI.preview')} style={{ maxWidth: 300, borderRadius: 8, marginBottom: '1rem' }} />}
        <button className="btn btn-primary" disabled={!file || loading}>
          <Upload size={16} /> {(loading) ? t('ImageAI.analyzing') : t('ImageAI.analyze')}
        </button>
      </form>

      {result && (
        <div style={{ marginTop: '1.5rem' }}>
          <div className="card" style={{ padding: '1rem', background: 'var(--color-bg)' }}>
            <h4>{result.medication_name}</h4>
            {result.generic_name && <p style={{ color: 'var(--color-text-secondary)' }}>{t('ImageAI.generic', { generic_name: result.generic_name })}</p>}
            {result.drug_class && <p><strong>{t('ImageAI.class')}</strong> {result.drug_class}</p>}
            {result.common_dosages && <p><strong>{t('ImageAI.common_dosages')}</strong> {result.common_dosages}</p>}
            {result.side_effects?.length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong>{t('ImageAI.side_effects')}</strong>
                <ul style={{ marginLeft: '1.5rem', marginTop: '0.25rem' }}>
                  {result.side_effects.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
            {result.interactions?.length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong>{t('ImageAI.interactions')}</strong>
                <ul style={{ marginLeft: '1.5rem', marginTop: '0.25rem' }}>
                  {result.interactions.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
            {result.warnings?.length > 0 && (
              <div style={{ marginTop: '0.5rem', color: 'var(--color-danger)' }}>
                <strong>{t('ImageAI.warnings')}</strong>
                <ul style={{ marginLeft: '1.5rem', marginTop: '0.25rem' }}>
                  {result.warnings.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
          </div>
          {result.confidence_note && (
            <p style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>{result.confidence_note}</p>
          )}
        </div>
      )}
    </div>
  );
}

function DosageVerification() {
  const [form, setForm] = useState({ medication_name: '', prescribed_dosage: '', patient_weight_kg: '', patient_age: '' });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = { ...form };
      if (payload.patient_weight_kg) payload.patient_weight_kg = parseFloat(payload.patient_weight_kg);
      else delete payload.patient_weight_kg;
      if (payload.patient_age) payload.patient_age = parseInt(payload.patient_age);
      else delete payload.patient_age;
      const { data } = await api.post('/image-ai/verify-dosage', payload);
      setResult(data);
    } catch (err) {
      alert(apiErrorMessage(err, t('ImageAI.error_verifying_dosage')));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <h3 style={{ marginBottom: '1rem' }}>{t('ImageAI.verify_medication_dosage')}</h3>
      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="form-group">
            <label className="form-label">{t('ImageAI.medication_name')}</label>
            <input className="form-input" required value={form.medication_name}
              onChange={e => setForm(p => ({ ...p, medication_name: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">{t('ImageAI.prescribed_dosage')}</label>
            <input className="form-input" required value={form.prescribed_dosage}
              placeholder={t('ImageAI.e_g_500mg_twice_daily')}
              onChange={e => setForm(p => ({ ...p, prescribed_dosage: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">{t('ImageAI.patient_weight_kg')}</label>
            <input className="form-input" type="number" value={form.patient_weight_kg}
              onChange={e => setForm(p => ({ ...p, patient_weight_kg: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">{t('ImageAI.patient_age')}</label>
            <input className="form-input" type="number" value={form.patient_age}
              onChange={e => setForm(p => ({ ...p, patient_age: e.target.value }))} />
          </div>
        </div>
        <button className="btn btn-primary" disabled={!form.medication_name || !form.prescribed_dosage || loading}>
          <ShieldCheck size={16} /> {(loading) ? t('ImageAI.verifying') : t('ImageAI.verify_dosage')}
        </button>
      </form>

      {result && (
        <div style={{
          marginTop: '1.5rem', padding: '1rem', borderRadius: 8,
          background: result.is_within_range ? '#d1fae5' : '#fee2e2',
          border: `1px solid ${result.is_within_range ? '#10b981' : '#ef4444'}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            {result.is_within_range ? <CheckCircle color="#10b981" /> : <AlertTriangle color="#ef4444" />}
            <strong>{result.is_within_range ? 'Within Normal Range' : 'Outside Normal Range'}</strong>
          </div>
          <p><strong>{t('ImageAI.medication')}</strong> {result.medication_name}</p>
          <p><strong>{t('ImageAI.prescribed')}</strong> {result.prescribed_dosage}</p>
          <p><strong>{t('ImageAI.standard_range')}</strong> {result.standard_range}</p>
          <p><strong>{t('ImageAI.recommendation')}</strong> {result.recommendation}</p>
          {result.warnings?.length > 0 && (
            <div style={{ marginTop: '0.5rem', color: 'var(--color-danger)' }}>
              <strong>{t('ImageAI.warnings')}</strong>
              <ul style={{ marginLeft: '1.5rem' }}>
                {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const thStyle = { textAlign: 'left', padding: '0.5rem', fontSize: '0.85rem', color: 'var(--color-text-secondary)' };
const tdStyle = { padding: '0.5rem' };
