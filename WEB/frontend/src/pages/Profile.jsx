import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import i18n, { SUPPORTED_LANGUAGES, normaliseLanguage, t as translate } from '../i18n';
import AvatarUpload from '../components/AvatarUpload';
import BackButton from '../components/BackButton';
import UnitToggle from '../components/UnitToggle';
import { useUnits } from '../context/UnitsContext';
import { apiErrorMessage } from '../utils/apiError';

const emptyForm = {
  full_name: '',
  first_name: '',
  last_name: '',
  middle_name: '',
  name_prefix: '',
  name_suffix: '',
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
  // The photo is held OUTSIDE `form`: it is saved by its own endpoint the
  // moment it is chosen, not by the Save button, so spreading it into the
  // PATCH payload would send a 40 KB data URI back on every profile save.
  const [photo, setPhoto] = useState(null);
  const [userId, setUserId] = useState(null);
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
    setPhoto(data.profile_picture_url || null);
    setUserId(data.id ?? null);
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
      // The saved language becomes the app's language now, so the language
      // header the assistant reads never contradicts the choice just made.
      const chosen = normaliseLanguage(payload.preferred_language);
      if (chosen && chosen !== i18n.language) i18n.changeLanguage(chosen);
      setMessage(translate('Profile.profile_updated_successfully'));
      setMessageType('info');
      // Re-lock set-once fields after save
      setLocked({
        date_of_birth: !!form.date_of_birth,
        gender_at_birth: !!form.gender_at_birth,
        blood_type: !!form.blood_type,
      });
    } catch (err) {
      setMessage(apiErrorMessage(err, translate('Profile.failed_to_update_profile')));
      setMessageType('error');
    } finally {
      setSaving(false);
    }
  }

  // Conditions live on their own screen (/chronic-conditions) but are surfaced
  // here because this is where people look for them. `conditionsError` is kept
  // apart from an empty list so a failed fetch never reads as "none recorded".
  const [conditions, setConditions] = useState(null);
  const [conditionsError, setConditionsError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get('/chronic/conditions', { params: { limit: 1000 } })
      .then(({ data }) => {
        if (!cancelled) {
          setConditions(Array.isArray(data) ? data : []);
          setConditionsError(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.error('Failed to load conditions:', err);
          setConditionsError(true);
        }
      });
    return () => { cancelled = true; };
  }, []);

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
          <h1 className="page-title">{translate('Profile.profile')}</h1>
        </div>
      </div>

      {/* Email — always read-only */}
      <div className="card" style={sectionStyle}>
        <div className="form-row">
          <div className="form-group">
            <label className="form-label">{translate('Profile.email')}</label>
            <input className="form-input" value={email} readOnly style={{ opacity: 0.6 }} />
          </div>
        </div>
      </div>

      <div className="card">
        <form onSubmit={handleSave}>
          {/* ── Identity ── */}
          <div style={sectionStyle}>
            {sectionTitle('Identity')}
            <div style={{ marginBottom: '1.25rem' }}>
              <AvatarUpload
                user={{ ...form, id: userId, profile_picture_url: photo }}
                onChange={(u) => setPhoto(u.profile_picture_url)}
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.first_name')}</label>
                <input className="form-input" autoComplete="given-name" minLength={3}
                       value={form.first_name} onChange={(e) => updateField('first_name', e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.last_name')}</label>
                <input className="form-input" autoComplete="family-name" minLength={3}
                       value={form.last_name} onChange={(e) => updateField('last_name', e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">{'Date of Birth' + (locked.date_of_birth ? lockLabel : '')}</label>
                <input className="form-input" type="date" value={form.date_of_birth} onChange={(e) => updateField('date_of_birth', e.target.value)} readOnly={locked.date_of_birth} style={locked.date_of_birth ? { opacity: 0.6 } : {}} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.prefix')}</label>
                <input className="form-input" placeholder={translate('Profile.dr_mrs_chief')}
                       value={form.name_prefix} onChange={(e) => updateField('name_prefix', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.middle_name')}</label>
                <input className="form-input" autoComplete="additional-name"
                       value={form.middle_name} onChange={(e) => updateField('middle_name', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.suffix')}</label>
                <input className="form-input" placeholder={translate('Profile.jr_iii_rn')}
                       value={form.name_suffix} onChange={(e) => updateField('name_suffix', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.gender_identity')}</label>
                <select className="form-input" value={form.gender} onChange={(e) => updateField('gender', e.target.value)}>
                  <option value="">—</option>
                  <option value="Male">{translate('Profile.male')}</option>
                  <option value="Female">{translate('Profile.female')}</option>
                  <option value="Non-binary">{translate('Profile.non_binary')}</option>
                  <option value="Prefer not to say">{translate('Profile.prefer_not_to_say')}</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{'Sex at Birth' + (locked.gender_at_birth ? lockLabel : '')}</label>
                <select className="form-input" value={form.gender_at_birth} onChange={(e) => updateField('gender_at_birth', e.target.value)} disabled={locked.gender_at_birth} style={locked.gender_at_birth ? { opacity: 0.6 } : {}}>
                  <option value="">—</option>
                  <option value="Male">{translate('Profile.male')}</option>
                  <option value="Female">{translate('Profile.female')}</option>
                  <option value="Intersex">{translate('Profile.intersex')}</option>
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
                <label className="form-label">{translate('Profile.profile_picture_url')}</label>
                <input className="form-input" value={form.profile_picture_url} onChange={(e) => updateField('profile_picture_url', e.target.value)} />
              </div>
            </div>
          </div>

          {/* ── Insurance ── */}
          <div style={sectionStyle}>
            {sectionTitle('Insurance')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.insurance_id')}</label>
                <input className="form-input" value={form.insurance_id} onChange={(e) => updateField('insurance_id', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.provider')}</label>
                <input className="form-input" value={form.insurance_provider} onChange={(e) => updateField('insurance_provider', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.country')}</label>
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
                {translate('Profile.values_are_stored_in_metric_and_shown')}
              </p>
            )}
          </div>

          {/* ── Location & Culture ── */}
          <div style={sectionStyle}>
            {sectionTitle('Location & Preferences')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.country')}</label>
                <input className="form-input" value={form.country} onChange={(e) => updateField('country', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.timezone')}</label>
                <input className="form-input" value={form.timezone} onChange={(e) => updateField('timezone', e.target.value)} placeholder={translate('Profile.e_g_america_new_york')} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.preferred_language')}</label>
                {/* All eleven languages, each in its own name. A stored "English"
                    (iOS saves names) resolves to its code so the select shows it. */}
                <select className="form-input" value={normaliseLanguage(form.preferred_language) || ''} onChange={(e) => updateField('preferred_language', e.target.value)}>
                  <option value="">—</option>
                  {SUPPORTED_LANGUAGES.map((lang) => (
                    <option key={lang.code} value={lang.code}>{lang.nativeName}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.units')}</label>
                <div>
                  <UnitToggle />
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary, #777)', margin: '0.35rem 0 0' }}>
                  {translate('Profile.applies_across_the_app_and_is_saved_to')}
                </p>
              </div>
            </div>
          </div>

          {/* ── Health Profile ── */}
          <div style={sectionStyle}>
            {sectionTitle('Health Profile')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.allergies_comma_separated')}</label>
                <input className="form-input" value={form.allergies} onChange={(e) => updateField('allergies', e.target.value)} placeholder={translate('Profile.e_g_penicillin_shellfish_latex')} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.food_intolerances')}</label>
                <input className="form-input" value={form.food_intolerances} onChange={(e) => updateField('food_intolerances', e.target.value)} placeholder={translate('Profile.e_g_gluten_lactose')} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.dietary_restrictions')}</label>
                <input className="form-input" value={form.dietary_restrictions} onChange={(e) => updateField('dietary_restrictions', e.target.value)} placeholder={translate('Profile.e_g_gluten_free_halal_vegan')} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.dietary_preferences')}</label>
                <input className="form-input" value={form.dietary_preferences} onChange={(e) => updateField('dietary_preferences', e.target.value)} placeholder={translate('Profile.e_g_low_carb_keto_mediterranean')} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.family_history')}</label>
                <input className="form-input" value={form.family_history} onChange={(e) => updateField('family_history', e.target.value)} placeholder={translate('Profile.e_g_heart_disease_diabetes')} />
              </div>
            </div>
          </div>

          {/* ── Privacy & Your Data ──
              The only surface that manages data-sharing consent — including the
              flag that decides whether meal photos are retained as training data
              (canon §3a). It was built, backed by three live endpoints, and
              unreachable: no route and no link (§3ad). */}
          <div style={sectionStyle}>
            {sectionTitle('Privacy & Your Data')}
            <Link
              to="/privacy-settings"
              data-testid="profile-privacy-link"
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                gap: '1rem', padding: '0.85rem 1rem', borderRadius: '8px',
                border: '1px solid var(--color-border, #e0e0e0)', textDecoration: 'none',
                color: 'inherit', background: 'var(--color-surface-alt, #fafafa)'
              }}
            >
              <span>{translate('Profile.data_sharing_export_and_deletion')}</span>
              <span aria-hidden="true">›</span>
            </Link>
          </div>

          {/* ── Health Conditions ──
              Diagnosed conditions are their own records (ICD-11 coded, with
              severity and diagnosis dates), so they get a dedicated screen
              rather than a text box here. */}
          <div style={sectionStyle}>
            {sectionTitle('Health Conditions')}
            <Link
              to="/chronic-conditions"
              data-testid="profile-conditions-link"
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                gap: '1rem', padding: '0.85rem 1rem', borderRadius: '8px',
                border: '1px solid var(--color-border, #e0e0e0)', textDecoration: 'none',
                color: 'inherit', background: 'var(--color-surface-alt, #fafafa)'
              }}
            >
              <span>
                <span style={{ display: 'block', fontWeight: 600 }}>
                  {translate('Profile.conditions_diagnoses')}
                </span>
                <span style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary, #666)' }}>
                  {conditionsError
                    ? 'Could not load — open to retry'
                    : conditions === null
                      ? 'Loading…'
                      : conditions.length === 0
                        ? 'None recorded yet — add one with its ICD-11 code'
                        : conditions
                            .filter((c) => c.is_active !== false)
                            .slice(0, 3)
                            .map((c) => c.condition_name)
                            .join(', ')
                          || 'No active conditions'}
                </span>
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                {!conditionsError && conditions !== null && conditions.length > 0 && (
                  <span
                    style={{
                      background: 'var(--color-primary, #1565c0)', color: 'white',
                      borderRadius: '999px', padding: '0.1rem 0.6rem', fontSize: '0.8rem',
                      fontWeight: 600
                    }}
                  >
                    {conditions.length}
                  </span>
                )}
                <span aria-hidden="true" style={{ color: 'var(--color-text-secondary, #888)' }}>›</span>
              </span>
            </Link>
          </div>

          {/* ── Fitness ── */}
          <div style={sectionStyle}>
            {sectionTitle('Fitness')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.activity_level')}</label>
                <select className="form-input" value={form.activity_level} onChange={(e) => updateField('activity_level', e.target.value)}>
                  <option value="">—</option>
                  <option value="sedentary">{translate('Profile.sedentary')}</option>
                  <option value="lightly_active">{translate('Profile.lightly_active')}</option>
                  <option value="moderately_active">{translate('Profile.moderately_active')}</option>
                  <option value="very_active">{translate('Profile.very_active')}</option>
                  <option value="extremely_active">{translate('Profile.extremely_active')}</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.exercise_week')}</label>
                <input className="form-input" type="number" min="0" max="14" value={form.exercise_frequency_per_week} onChange={(e) => updateField('exercise_frequency_per_week', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.fitness_goals')}</label>
                <input className="form-input" value={form.fitness_goals} onChange={(e) => updateField('fitness_goals', e.target.value)} placeholder={translate('Profile.e_g_weight_loss_endurance_muscle_gain')} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.preferred_activities')}</label>
                <input className="form-input" value={form.preferred_activities} onChange={(e) => updateField('preferred_activities', e.target.value)} placeholder={translate('Profile.e_g_running_yoga_swimming')} />
              </div>
            </div>
          </div>

          {/* ── Lifestyle ── */}
          <div style={sectionStyle}>
            {sectionTitle('Lifestyle')}
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.occupation')}</label>
                <input className="form-input" value={form.occupation} onChange={(e) => updateField('occupation', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.smoking_status')}</label>
                <select className="form-input" value={form.smoking_status} onChange={(e) => updateField('smoking_status', e.target.value)}>
                  <option value="">—</option>
                  <option value="never">{translate('Profile.never')}</option>
                  <option value="former">{translate('Profile.former')}</option>
                  <option value="current">{translate('Profile.current')}</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.alcohol')}</label>
                <select className="form-input" value={form.alcohol_consumption} onChange={(e) => updateField('alcohol_consumption', e.target.value)}>
                  <option value="">—</option>
                  <option value="none">{translate('Profile.none')}</option>
                  <option value="occasional">{translate('Profile.occasional')}</option>
                  <option value="moderate">{translate('Profile.moderate')}</option>
                  <option value="heavy">{translate('Profile.heavy')}</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Profile.sleep_schedule')}</label>
                <select className="form-input" value={form.sleep_schedule} onChange={(e) => updateField('sleep_schedule', e.target.value)}>
                  <option value="">—</option>
                  <option value="early_bird">{translate('Profile.early_bird')}</option>
                  <option value="night_owl">{translate('Profile.night_owl')}</option>
                  <option value="shift_worker">{translate('Profile.shift_worker')}</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.stress_level')}</label>
                <select className="form-input" value={form.stress_level} onChange={(e) => updateField('stress_level', e.target.value)}>
                  <option value="">—</option>
                  <option value="low">{translate('Profile.low')}</option>
                  <option value="moderate">{translate('Profile.moderate')}</option>
                  <option value="high">{translate('Profile.high')}</option>
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
                  {translate('Profile.ai_coaching_enabled')}
                </label>
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.ai_personality')}</label>
                <select className="form-input" value={form.ai_personality_preference} onChange={(e) => updateField('ai_personality_preference', e.target.value)}>
                  <option value="">—</option>
                  <option value="supportive">{translate('Profile.supportive')}</option>
                  <option value="motivational">{translate('Profile.motivational')}</option>
                  <option value="clinical">{translate('Profile.clinical')}</option>
                  <option value="casual">{translate('Profile.casual')}</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Profile.language_complexity')}</label>
                <select className="form-input" value={form.ai_language_complexity} onChange={(e) => updateField('ai_language_complexity', e.target.value)}>
                  <option value="">—</option>
                  <option value="simple">{translate('Profile.simple')}</option>
                  <option value="moderate">{translate('Profile.moderate')}</option>
                  <option value="technical">{translate('Profile.technical')}</option>
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
                  {translate('Profile.data_sharing_consent')}
                </label>
              </div>
              <div className="form-group">
                <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={form.ai_training_consent} onChange={(e) => updateField('ai_training_consent', e.target.checked)} />
                  {translate('Profile.ai_training_consent')}
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
