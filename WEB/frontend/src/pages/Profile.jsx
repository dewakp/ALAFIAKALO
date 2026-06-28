import { useEffect, useState } from 'react';
import api from '../services/api';
import BackButton from '../components/BackButton';
import UnitToggle from '../components/UnitToggle';
import { useUnits } from '../context/UnitsContext';
import { apiErrorMessage } from '../utils/apiError';

const emptyForm = {
  full_name: '',
  date_of_birth: '',
  gender: '',
  gender_at_birth: '',
  blood_type: '',
  insurance_id: '',
  insurance_provider: '',
  insurance_country: '',
  profile_picture_url: '',
  height_cm: '',
  current_weight_kg: '',
  target_weight_kg: '',
  locale: '',
  timezone: '',
  country: '',
  preferred_units: '',
  preferred_language: '',
  allergies: '',
  food_intolerances: '',
  dietary_restrictions: '',
  dietary_preferences: '',
  family_history: '',
  activity_level: '',
  fitness_goals: '',
  preferred_activities: '',
  exercise_frequency_per_week: '',
  smoking_status: '',
  alcohol_consumption: '',
  sleep_schedule: '',
  occupation: '',
  stress_level: '',
  ai_coaching_enabled: true,
  ai_personality_preference: '',
  ai_language_complexity: '',
  data_sharing_consent: false,
  ai_training_consent: false,
};

export default function Profile() {
  const { system, isImperial, toDisplay, toMetric, unitLabel } = useUnits();
  const [form, setForm] = useState(emptyForm);
  const [email, setEmail] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('info');
  // Track which set-once fields already have values (locked)
  const [locked, setLocked] = useState({ date_of_birth: false, gender_at_birth: false, blood_type: false });
  // Physical fields are stored canonical-metric in `form`, but edited in the
  // active unit system. `phys` holds the display-system strings the user types;
  // it is re-derived from metric whenever the metric value or the system changes.
  const [phys, setPhys] = useState({ height_cm: '', current_weight_kg: '', target_weight_kg: '' });

  useEffect(() => {
    loadProfile();
  }, []);

  // Re-derive the display values when the user flips the Metric/Imperial toggle.
  // (Deliberately depends only on `system` — not on `form` — so it never clobbers
  // what the user is actively typing into a physical field.)
  useEffect(() => {
    setPhys({
      height_cm: toDisplayStr(form.height_cm, 'length'),
      current_weight_kg: toDisplayStr(form.current_weight_kg, 'mass'),
      target_weight_kg: toDisplayStr(form.target_weight_kg, 'mass'),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [system]);

  function toDisplayStr(metricVal, measurement) {
    if (metricVal === '' || metricVal === null || metricVal === undefined) return '';
    const v = toDisplay(metricVal, measurement);
    return v === '' || v === null || v === undefined ? '' : String(v);
  }

  async function loadProfile() {
    const { data } = await api.get('/users/me');
    setEmail(data.email || '');
    const loaded = {};
    for (const key of Object.keys(emptyForm)) {
      loaded[key] = data[key] ?? emptyForm[key];
    }
    setForm(loaded);
    setPhys({
      height_cm: toDisplayStr(loaded.height_cm, 'length'),
      current_weight_kg: toDisplayStr(loaded.current_weight_kg, 'mass'),
      target_weight_kg: toDisplayStr(loaded.target_weight_kg, 'mass'),
    });
    setLocked({
      date_of_birth: !!data.date_of_birth,
      gender_at_birth: !!data.gender_at_birth,
      blood_type: !!data.blood_type,
    });
  }

  // User typed into a physical field (value is in the active display system) —
  // keep the raw string in `phys` and the canonical metric in `form`.
  function updatePhysField(field, measurement, value) {
    setPhys((prev) => ({ ...prev, [field]: value }));
    const metricVal = value === '' ? '' : toMetric(value, measurement);
    setForm((prev) => ({ ...prev, [field]: metricVal }));
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setMessage('');
    try {
      // Build payload. Physical fields in `form` are already canonical metric
      // (updatePhysField converts on entry). The unit preference comes from the
      // shared UnitsContext rather than a form field.
      const payload = { ...form, preferred_units: system };
      // Numeric fields: an empty string is NOT a valid float/int — Pydantic
      // rejects "" with a 422. Coerce empty → null. (String fields accept "",
      // and set-once fields like date_of_birth must keep "" so the backend
      // treats them as unchanged rather than a null "change".)
      const toNum = (v, parse) => (v === '' || v == null ? null : (parse(v) || null));
      payload.height_cm = toNum(payload.height_cm, parseFloat);
      payload.current_weight_kg = toNum(payload.current_weight_kg, parseFloat);
      payload.target_weight_kg = toNum(payload.target_weight_kg, parseFloat);
      payload.exercise_frequency_per_week = toNum(payload.exercise_frequency_per_week, parseInt);
      await api.patch('/users/me', payload);
      setMessage('Profile updated successfully.');
      setMessageType('info');
      // Re-lock set-once fields after save
      setLocked({
        date_of_birth: !!form.date_of_birth,
        gender_at_birth: !!form.gender_at_birth,
        blood_type: !!form.blood_type,
      });
    } catch (err) {
      setMessage(apiErrorMessage(err, 'Failed to update profile.'));
      setMessageType('error');
    } finally {
      setSaving(false);
    }
  }

  const sectionStyle = { marginBottom: '1.5rem' };
  const sectionTitle = (title) => (
    <h3 style={{ margin: '0 0 0.75rem', fontSize: '1rem', fontWeight: 600, color: 'var(--color-text-secondary, #555)' }}>{title}</h3>
  );
  const lockLabel = ' (locked — cannot be changed)';

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Profile</h1>
        </div>
      </div>

      {/* Email — always read-only */}
      <div className="card" style={sectionStyle}>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">Email</label>
            <input className="form-input" value={email} readOnly style={{ opacity: 0.6 }} />
          </div>
        </div>
      </div>

      <div className="card">
        <form onSubmit={handleSave}>
          {/* ── Identity ── */}
          <div style={sectionStyle}>
            {sectionTitle('Identity')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Full Name</label>
                <input className="form-input" value={form.full_name} onChange={(e) => updateField('full_name', e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">{'Date of Birth' + (locked.date_of_birth ? lockLabel : '')}</label>
                <input className="form-input" type="date" value={form.date_of_birth} onChange={(e) => updateField('date_of_birth', e.target.value)} readOnly={locked.date_of_birth} style={locked.date_of_birth ? { opacity: 0.6 } : {}} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Gender Identity</label>
                <select className="form-input" value={form.gender} onChange={(e) => updateField('gender', e.target.value)}>
                  <option value="">—</option>
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Non-binary">Non-binary</option>
                  <option value="Prefer not to say">Prefer not to say</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{'Sex at Birth' + (locked.gender_at_birth ? lockLabel : '')}</label>
                <select className="form-input" value={form.gender_at_birth} onChange={(e) => updateField('gender_at_birth', e.target.value)} disabled={locked.gender_at_birth} style={locked.gender_at_birth ? { opacity: 0.6 } : {}}>
                  <option value="">—</option>
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Intersex">Intersex</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{'Blood Type' + (locked.blood_type ? lockLabel : '')}</label>
                <select className="form-input" value={form.blood_type} onChange={(e) => updateField('blood_type', e.target.value)} disabled={locked.blood_type} style={locked.blood_type ? { opacity: 0.6 } : {}}>
                  <option value="">—</option>
                  {['A+','A-','B+','B-','AB+','AB-','O+','O-'].map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Profile Picture URL</label>
                <input className="form-input" value={form.profile_picture_url} onChange={(e) => updateField('profile_picture_url', e.target.value)} />
              </div>
            </div>
          </div>

          {/* ── Insurance ── */}
          <div style={sectionStyle}>
            {sectionTitle('Insurance')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Insurance ID</label>
                <input className="form-input" value={form.insurance_id} onChange={(e) => updateField('insurance_id', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Provider</label>
                <input className="form-input" value={form.insurance_provider} onChange={(e) => updateField('insurance_provider', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Country</label>
                <input className="form-input" value={form.insurance_country} onChange={(e) => updateField('insurance_country', e.target.value)} />
              </div>
            </div>
          </div>

          {/* ── Physical ── */}
          <div style={sectionStyle}>
            {sectionTitle('Physical Characteristics')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{`Height (${unitLabel('length')})`}</label>
                <input className="form-input" type="number" step="0.1" value={phys.height_cm} onChange={(e) => updatePhysField('height_cm', 'length', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{`Current Weight (${unitLabel('mass')})`}</label>
                <input className="form-input" type="number" step="0.1" value={phys.current_weight_kg} onChange={(e) => updatePhysField('current_weight_kg', 'mass', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{`Target Weight (${unitLabel('mass')})`}</label>
                <input className="form-input" type="number" step="0.1" value={phys.target_weight_kg} onChange={(e) => updatePhysField('target_weight_kg', 'mass', e.target.value)} />
              </div>
            </div>
            {isImperial && (
              <p style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary, #777)', margin: '0.25rem 0 0' }}>
                Values are stored in metric and shown here in imperial.
              </p>
            )}
          </div>

          {/* ── Location & Culture ── */}
          <div style={sectionStyle}>
            {sectionTitle('Location & Preferences')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Country</label>
                <input className="form-input" value={form.country} onChange={(e) => updateField('country', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Timezone</label>
                <input className="form-input" value={form.timezone} onChange={(e) => updateField('timezone', e.target.value)} placeholder="e.g. America/New_York" />
              </div>
              <div className="form-group">
                <label className="form-label">Preferred Language</label>
                <select className="form-input" value={form.preferred_language} onChange={(e) => updateField('preferred_language', e.target.value)}>
                  <option value="">—</option>
                  <option value="en">English</option>
                  <option value="fr">French</option>
                  <option value="es">Spanish</option>
                  <option value="pt">Portuguese</option>
                  <option value="ar">Arabic</option>
                  <option value="sw">Swahili</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Units</label>
                <div>
                  <UnitToggle />
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary, #777)', margin: '0.35rem 0 0' }}>
                  Applies across the app and is saved to your profile.
                </p>
              </div>
            </div>
          </div>

          {/* ── Health Profile ── */}
          <div style={sectionStyle}>
            {sectionTitle('Health Profile')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Allergies (comma-separated)</label>
                <input className="form-input" value={form.allergies} onChange={(e) => updateField('allergies', e.target.value)} placeholder="e.g. penicillin, shellfish, latex" />
              </div>
              <div className="form-group">
                <label className="form-label">Food Intolerances</label>
                <input className="form-input" value={form.food_intolerances} onChange={(e) => updateField('food_intolerances', e.target.value)} placeholder="e.g. gluten, lactose" />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Dietary Restrictions</label>
                <input className="form-input" value={form.dietary_restrictions} onChange={(e) => updateField('dietary_restrictions', e.target.value)} placeholder="e.g. gluten-free, halal, vegan" />
              </div>
              <div className="form-group">
                <label className="form-label">Dietary Preferences</label>
                <input className="form-input" value={form.dietary_preferences} onChange={(e) => updateField('dietary_preferences', e.target.value)} placeholder="e.g. low-carb, keto, mediterranean" />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Family History</label>
                <input className="form-input" value={form.family_history} onChange={(e) => updateField('family_history', e.target.value)} placeholder="e.g. heart disease, diabetes" />
              </div>
            </div>
          </div>

          {/* ── Fitness ── */}
          <div style={sectionStyle}>
            {sectionTitle('Fitness')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Activity Level</label>
                <select className="form-input" value={form.activity_level} onChange={(e) => updateField('activity_level', e.target.value)}>
                  <option value="">—</option>
                  <option value="sedentary">Sedentary</option>
                  <option value="lightly_active">Lightly Active</option>
                  <option value="moderately_active">Moderately Active</option>
                  <option value="very_active">Very Active</option>
                  <option value="extremely_active">Extremely Active</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Exercise / Week</label>
                <input className="form-input" type="number" min="0" max="14" value={form.exercise_frequency_per_week} onChange={(e) => updateField('exercise_frequency_per_week', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Fitness Goals</label>
                <input className="form-input" value={form.fitness_goals} onChange={(e) => updateField('fitness_goals', e.target.value)} placeholder="e.g. weight loss, endurance, muscle gain" />
              </div>
              <div className="form-group">
                <label className="form-label">Preferred Activities</label>
                <input className="form-input" value={form.preferred_activities} onChange={(e) => updateField('preferred_activities', e.target.value)} placeholder="e.g. running, yoga, swimming" />
              </div>
            </div>
          </div>

          {/* ── Lifestyle ── */}
          <div style={sectionStyle}>
            {sectionTitle('Lifestyle')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Occupation</label>
                <input className="form-input" value={form.occupation} onChange={(e) => updateField('occupation', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Smoking Status</label>
                <select className="form-input" value={form.smoking_status} onChange={(e) => updateField('smoking_status', e.target.value)}>
                  <option value="">—</option>
                  <option value="never">Never</option>
                  <option value="former">Former</option>
                  <option value="current">Current</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Alcohol</label>
                <select className="form-input" value={form.alcohol_consumption} onChange={(e) => updateField('alcohol_consumption', e.target.value)}>
                  <option value="">—</option>
                  <option value="none">None</option>
                  <option value="occasional">Occasional</option>
                  <option value="moderate">Moderate</option>
                  <option value="heavy">Heavy</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Sleep Schedule</label>
                <select className="form-input" value={form.sleep_schedule} onChange={(e) => updateField('sleep_schedule', e.target.value)}>
                  <option value="">—</option>
                  <option value="early_bird">Early Bird</option>
                  <option value="night_owl">Night Owl</option>
                  <option value="shift_worker">Shift Worker</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Stress Level</label>
                <select className="form-input" value={form.stress_level} onChange={(e) => updateField('stress_level', e.target.value)}>
                  <option value="">—</option>
                  <option value="low">Low</option>
                  <option value="moderate">Moderate</option>
                  <option value="high">High</option>
                </select>
              </div>
            </div>
          </div>

          {/* ── AI Preferences ── */}
          <div style={sectionStyle}>
            {sectionTitle('AI Preferences')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={form.ai_coaching_enabled} onChange={(e) => updateField('ai_coaching_enabled', e.target.checked)} />
                  AI Coaching Enabled
                </label>
              </div>
              <div className="form-group">
                <label className="form-label">AI Personality</label>
                <select className="form-input" value={form.ai_personality_preference} onChange={(e) => updateField('ai_personality_preference', e.target.value)}>
                  <option value="">—</option>
                  <option value="supportive">Supportive</option>
                  <option value="motivational">Motivational</option>
                  <option value="clinical">Clinical</option>
                  <option value="casual">Casual</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Language Complexity</label>
                <select className="form-input" value={form.ai_language_complexity} onChange={(e) => updateField('ai_language_complexity', e.target.value)}>
                  <option value="">—</option>
                  <option value="simple">Simple</option>
                  <option value="moderate">Moderate</option>
                  <option value="technical">Technical</option>
                </select>
              </div>
            </div>
          </div>

          {/* ── Privacy ── */}
          <div style={sectionStyle}>
            {sectionTitle('Privacy & Consent')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={form.data_sharing_consent} onChange={(e) => updateField('data_sharing_consent', e.target.checked)} />
                  Data Sharing Consent
                </label>
              </div>
              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={form.ai_training_consent} onChange={(e) => updateField('ai_training_consent', e.target.checked)} />
                  AI Training Consent
                </label>
              </div>
            </div>
          </div>

          {message && (
            <div style={{ color: messageType === 'error' ? 'var(--color-danger, red)' : 'var(--color-info)', marginBottom: '1rem' }}>
              {message}
            </div>
          )}

          <button className="btn btn-primary" type="submit" disabled={saving}>
            {saving ? 'Saving...' : 'Save Profile'}
          </button>
        </form>
      </div>
    </div>
  );
}
