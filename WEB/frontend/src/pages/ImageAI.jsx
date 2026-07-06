import { useState } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Camera, Pill, ShieldCheck, Upload, AlertTriangle, CheckCircle } from 'lucide-react';
import BackButton from '../components/BackButton';

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
  { key: 'nutrition', label: 'Nutrition from Image', icon: Camera },
  { key: 'medication', label: 'Medication from Image', icon: Pill },
  { key: 'dosage', label: 'Dosage Verification', icon: ShieldCheck },
];

export default function ImageAI() {
  const [activeTab, setActiveTab] = useState('nutrition');

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Image AI Tools</h1>
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
      alert(apiErrorMessage(err, 'Error analyzing image'));
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
      alert(apiErrorMessage(err, 'Could not save the correction'));
    } finally {
      setTeaching(false);
    }
  }

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <h3 style={{ marginBottom: '1rem' }}>Identify Food from Photo</h3>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">Upload Food Image</label>
          <input type="file" accept="image/*" onChange={handleFile} className="form-input" />
        </div>
        {preview && (
          <img src={preview} alt="Preview" style={{ maxWidth: 300, borderRadius: 8, marginBottom: '1rem' }} />
        )}
        <button className="btn btn-primary" disabled={!file || loading}>
          <Upload size={16} /> {loading ? 'Analyzing...' : 'Analyze'}
        </button>
      </form>

      {result && (
        <div style={{ marginTop: '1.5rem' }}>
          <h4>Results</h4>
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '0.5rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--color-border)' }}>
                <th style={thStyle}>Food</th>
                <th style={thStyle}>Serving</th>
                <th style={thStyle}>Calories</th>
                <th style={thStyle}>Protein</th>
                <th style={thStyle}>Carbs</th>
                <th style={thStyle}>Fat</th>
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
                <td style={tdStyle} colSpan={2}>Total</td>
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
            <label className="form-label">Not right? Teach ALAFIA what this actually is</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input className="form-input" style={{ flex: 1 }} value={correction}
                onChange={(e) => setCorrection(e.target.value)}
                placeholder="e.g. beans in palm oil; grilled chicken; fried plantain" />
              <button type="button" className="btn btn-secondary" onClick={handleTeach}
                disabled={teaching || !correction.trim()}>
                {teaching ? 'Saving…' : 'Teach'}
              </button>
            </div>
            <p style={{ marginTop: 6, fontSize: '0.78rem', color: 'var(--color-text-secondary)' }}>
              Separate foods with semicolons. ALAFIA will recognize this meal in future photos.
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
      alert(apiErrorMessage(err, 'Error analyzing image'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <h3 style={{ marginBottom: '1rem' }}>Identify Medication from Photo</h3>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">Upload Medication Image</label>
          <input type="file" accept="image/*" onChange={handleFile} className="form-input" />
        </div>
        {preview && <img src={preview} alt="Preview" style={{ maxWidth: 300, borderRadius: 8, marginBottom: '1rem' }} />}
        <button className="btn btn-primary" disabled={!file || loading}>
          <Upload size={16} /> {loading ? 'Analyzing...' : 'Analyze'}
        </button>
      </form>

      {result && (
        <div style={{ marginTop: '1.5rem' }}>
          <div className="card" style={{ padding: '1rem', background: 'var(--color-bg)' }}>
            <h4>{result.medication_name}</h4>
            {result.generic_name && <p style={{ color: 'var(--color-text-secondary)' }}>Generic: {result.generic_name}</p>}
            {result.drug_class && <p><strong>Class:</strong> {result.drug_class}</p>}
            {result.common_dosages && <p><strong>Common Dosages:</strong> {result.common_dosages}</p>}
            {result.side_effects?.length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong>Side Effects:</strong>
                <ul style={{ marginLeft: '1.5rem', marginTop: '0.25rem' }}>
                  {result.side_effects.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
            {result.interactions?.length > 0 && (
              <div style={{ marginTop: '0.5rem' }}>
                <strong>Interactions:</strong>
                <ul style={{ marginLeft: '1.5rem', marginTop: '0.25rem' }}>
                  {result.interactions.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
            {result.warnings?.length > 0 && (
              <div style={{ marginTop: '0.5rem', color: 'var(--color-danger)' }}>
                <strong>Warnings:</strong>
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
      alert(apiErrorMessage(err, 'Error verifying dosage'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card" style={{ padding: '1.5rem' }}>
      <h3 style={{ marginBottom: '1rem' }}>Verify Medication Dosage</h3>
      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="form-group">
            <label className="form-label">Medication Name *</label>
            <input className="form-input" required value={form.medication_name}
              onChange={e => setForm(p => ({ ...p, medication_name: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Prescribed Dosage *</label>
            <input className="form-input" required value={form.prescribed_dosage}
              placeholder="e.g. 500mg twice daily"
              onChange={e => setForm(p => ({ ...p, prescribed_dosage: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Patient Weight (kg)</label>
            <input className="form-input" type="number" value={form.patient_weight_kg}
              onChange={e => setForm(p => ({ ...p, patient_weight_kg: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Patient Age</label>
            <input className="form-input" type="number" value={form.patient_age}
              onChange={e => setForm(p => ({ ...p, patient_age: e.target.value }))} />
          </div>
        </div>
        <button className="btn btn-primary" disabled={!form.medication_name || !form.prescribed_dosage || loading}>
          <ShieldCheck size={16} /> {loading ? 'Verifying...' : 'Verify Dosage'}
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
          <p><strong>Medication:</strong> {result.medication_name}</p>
          <p><strong>Prescribed:</strong> {result.prescribed_dosage}</p>
          <p><strong>Standard Range:</strong> {result.standard_range}</p>
          <p><strong>Recommendation:</strong> {result.recommendation}</p>
          {result.warnings?.length > 0 && (
            <div style={{ marginTop: '0.5rem', color: 'var(--color-danger)' }}>
              <strong>Warnings:</strong>
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
