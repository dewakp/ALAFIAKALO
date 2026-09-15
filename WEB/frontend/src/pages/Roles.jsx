import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiErrorMessage } from '../utils/apiError';
import api from '../services/api';
import BackButton from '../components/BackButton';
import { useClinicianMode, CLINICIAN_ROLES } from '../context/ClinicianModeContext';
import { t as translate } from '../i18n';

/* ── helpers ──────────────────────────────────────────────────────── */

const CATEGORY_ICONS = {
  physician: '🩺', surgeon: '🔪', nursing: '💉', therapy: '🧘',
  mental_health: '🧠', social_work: '🤝', dental: '🦷', pharmacy: '💊',
  diagnostics: '🔬', emergency: '🚑', allied_health: '🏥', public_health: '🌍',
  administration: '📋', research: '🔎', traditional_complementary: '🌿',
  midwifery: '👶', other: '📌',
};

const VERIFY_COLORS = {
  unverified: '#94a3b8', pending: '#f59e0b', verified: '#10b981',
  rejected: '#ef4444', expired: '#6b7280',
};

function Badge({ label, color = 'var(--color-primary)', outline = false }) {
  return (
    <span style={{
      display: 'inline-block', padding: '3px 12px', borderRadius: 20,
      fontSize: 12, fontWeight: 600, marginRight: 6, marginBottom: 4,
      background: outline ? 'transparent' : color,
      color: outline ? color : '#fff',
      border: outline ? `1.5px solid ${color}` : 'none',
    }}>
      {label}
    </span>
  );
}

/* ── main component ───────────────────────────────────────────────── */

export default function Roles() {
  const navigate = useNavigate();
  const { enterClinicianMode } = useClinicianMode();
  const [persona, setPersona] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overview');  // overview | add | profile

  // Acting on a clinical role switches the whole app into clinician mode and
  // lands on the patient grid, rather than just linking to a page that would
  // otherwise sit inside the patient navigation.
  const openClinicianView = () => {
    enterClinicianMode();
    navigate('/clinician-dashboard');
  };

  // Add-role state
  const [selectedCategory, setSelectedCategory] = useState('');
  const [roleSearch, setRoleSearch] = useState('');
  const [adding, setAdding] = useState(false);

  // Profile-edit state
  const [editRoleId, setEditRoleId] = useState(null);
  const [profileForm, setProfileForm] = useState({});
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMsg, setProfileMsg] = useState('');

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [p, c] = await Promise.all([
        api.get('/users/roles/me'),
        api.get('/users/roles/catalog'),
      ]);
      setPersona(p.data);
      setCatalog(c.data);
    } catch (err) { console.error(err); }
    setLoading(false);
  }

  /* ── Add role ──────────────────────────────────────────────── */
  async function handleAddRole(roleId) {
    setAdding(true);
    try {
      await api.post('/users/roles', {
        role: roleId,
        is_primary: !persona || persona.active_roles.length <= 1,
      });
      await loadAll();
      setTab('overview');
    } catch (err) {
      alert(apiErrorMessage(err, translate('Roles.failed_to_add_role')));
    }
    setAdding(false);
  }

  /* ── Remove role ───────────────────────────────────────────── */
  async function handleRemove(roleId) {
    if (!confirm(translate('Roles.remove_this_role_associated_professional'))) return;
    try {
      await api.delete(`/users/roles/${roleId}`);
      await loadAll();
    } catch (err) {
      alert(apiErrorMessage(err, translate('Roles.failed_to_remove_role')));
    }
  }

  /* ── Set primary ───────────────────────────────────────────── */
  async function handleSetPrimary(roleId) {
    try {
      await api.put(`/users/roles/${roleId}/primary`);
      await loadAll();
    } catch (err) {
      alert(apiErrorMessage(err, 'Failed'));
    }
  }

  /* ── Edit professional profile ─────────────────────────────── */
  async function openProfileEditor(roleAssignment) {
    setEditRoleId(roleAssignment.id);
    setProfileMsg('');
    if (roleAssignment.professional_profile) {
      const p = { ...roleAssignment.professional_profile };
      // Convert arrays to comma-separated for form inputs
      for (const k of ['board_certifications', 'hospital_affiliations', 'clinical_languages',
        'telemedicine_platforms', 'publications', 'research_interests']) {
        if (Array.isArray(p[k])) p[k] = p[k].join(', ');
        else p[k] = '';
      }
      setProfileForm(p);
    } else {
      setProfileForm({});
    }
    setTab('profile');
  }

  function updatePF(field, val) {
    setProfileForm(prev => ({ ...prev, [field]: val }));
  }

  async function handleSaveProfile(e) {
    e.preventDefault();
    setSavingProfile(true);
    setProfileMsg('');
    try {
      const payload = { ...profileForm };
      // Remove read-only fields
      delete payload.id;
      delete payload.role_assignment_id;
      delete payload.verification_status;
      delete payload.verification_date;
      delete payload.created_at;
      delete payload.updated_at;

      // Convert comma-separated strings back to arrays
      for (const k of ['board_certifications', 'hospital_affiliations', 'clinical_languages',
        'telemedicine_platforms', 'publications', 'research_interests']) {
        if (typeof payload[k] === 'string' && payload[k].trim()) {
          payload[k] = payload[k].split(',').map(s => s.trim()).filter(Boolean);
        } else {
          payload[k] = null;
        }
      }

      // Convert numeric fields
      if (payload.graduation_year) payload.graduation_year = Number(payload.graduation_year);
      if (payload.years_of_experience) payload.years_of_experience = Number(payload.years_of_experience);

      await api.put(`/users/roles/${editRoleId}/profile`, payload);
      setProfileMsg('Professional profile saved successfully.');
      await loadAll();
    } catch (err) {
      setProfileMsg(apiErrorMessage(err, translate('Roles.failed_to_save_profile')));
    }
    setSavingProfile(false);
  }

  /* ── Catalog filtering ─────────────────────────────────────── */
  const filteredCatalog = useMemo(() => {
    if (!catalog.length) return [];
    const existingRoles = new Set(persona?.active_roles || []);
    let cats = catalog;
    if (selectedCategory) cats = cats.filter(c => c.id === selectedCategory);
    return cats.map(cat => ({
      ...cat,
      roles: cat.roles.filter(r =>
        !existingRoles.has(r.id) &&
        (!roleSearch || r.name.toLowerCase().includes(roleSearch.toLowerCase()))
      ),
    })).filter(cat => cat.roles.length > 0);
  }, [catalog, selectedCategory, roleSearch, persona]);

  if (loading) return <div className="loading">{translate('Roles.loading')}</div>;
  if (!persona) return <div className="card">{translate('Roles.unable_to_load_persona_data')}</div>;

  /* ─────────────────────────────────────────────────────────── */
  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">{translate('Roles.role')}</h1>
        </div>
      </div>

      {/* Persona summary card */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <div style={{
            width: 56, height: 56, borderRadius: '50%',
            background: 'var(--color-primary-light)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', fontSize: 24,
          }}>
            {persona.is_healthcare_professional ? '⚕️' : '🧑'}
          </div>
          <div>
            <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>
              {persona.full_name}
            </div>
            <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
              {persona.email}
            </div>
          </div>
          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
            <Badge label={persona.primary_role.replace(/_/g, ' ').toUpperCase()} />
            {persona.is_healthcare_professional && (
              <Badge label={translate('Roles.healthcare_professional')} color="var(--color-info)" />
            )}
          </div>
        </div>

        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginBottom: 6 }}>{translate('Roles.active_roles')}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {persona.active_roles.map(r => (
              <Badge key={r} label={r.replace(/_/g, ' ')} outline color="var(--color-primary)" />
            ))}
          </div>
        </div>

        {persona.role_categories.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginBottom: 6 }}>{translate('Roles.categories')}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {persona.role_categories.map(c => (
                <Badge key={c} label={`${CATEGORY_ICONS[c] || '📌'} ${c.replace(/_/g, ' ')}`} color="#334155" />
              ))}
            </div>
          </div>
        )}

        {persona.permissions.length > 0 && (
          <details style={{ marginTop: 16 }}>
            <summary style={{ cursor: 'pointer', fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
              {translate('Roles.permissions', { permissions: persona.permissions.length })}
            </summary>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 8 }}>
              {persona.permissions.map(p => (
                <span key={p} style={{
                  display: 'inline-block', padding: '2px 8px', borderRadius: 6,
                  fontSize: 11, background: '#f1f5f9', color: '#475569',
                }}>
                  {p.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </details>
        )}
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: '1.5rem' }}>
        {[
          { id: 'overview', label: translate('Roles.my_roles') },
          { id: 'add', label: translate('Roles.add_role') },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: '8px 20px', borderRadius: 8,
            border: tab === t.id ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
            background: tab === t.id ? 'var(--color-primary)' : 'var(--color-surface)',
            color: tab === t.id ? '#fff' : 'var(--color-text)',
            fontWeight: tab === t.id ? 700 : 400, cursor: 'pointer',
          }}>
            {t.label}
          </button>
        ))}
        {editRoleId && (
          <button onClick={() => setTab('profile')} style={{
            padding: '8px 20px', borderRadius: 8,
            border: tab === 'profile' ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
            background: tab === 'profile' ? 'var(--color-primary)' : 'var(--color-surface)',
            color: tab === 'profile' ? '#fff' : 'var(--color-text)',
            fontWeight: tab === 'profile' ? 700 : 400, cursor: 'pointer',
          }}>
            {translate('Roles.edit_profile')}
          </button>
        )}
      </div>

      {/* ── Overview tab ──────────────────────────────────────── */}
      {tab === 'overview' && (
        <div>
          {/* Patient is always present */}
          <div className="card" style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ fontSize: 28 }}>🧑</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600 }}>{translate('Roles.patient')}</div>
              <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
                {translate('Roles.core_role_always_active')}
              </div>
            </div>
            <Badge label="ALWAYS ACTIVE" color="#64748b" />
          </div>

          {persona.role_details.map(rd => (
            <div key={rd.id} className="card" style={{
              marginBottom: 12, display: 'flex', alignItems: 'flex-start', gap: 16,
            }}>
              <span style={{ fontSize: 28 }}>
                {CATEGORY_ICONS[
                  catalog.find(c => c.roles.some(r => r.id === rd.role))?.id
                ] || '📌'}
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>
                  {rd.role.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                </div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 6 }}>
                  {rd.is_primary && <Badge label="PRIMARY" color="var(--color-info)" />}
                  <Badge label={rd.is_active ? 'Active' : 'Inactive'}
                    color={rd.is_active ? '#10b981' : '#94a3b8'} />
                  {rd.professional_profile && (
                    <Badge label={`Verification: ${rd.professional_profile.verification_status}`}
                      color={VERIFY_COLORS[rd.professional_profile.verification_status] || '#94a3b8'} />
                  )}
                </div>
                {rd.professional_profile && (
                  <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
                    {[
                      rd.professional_profile.specialty,
                      rd.professional_profile.practice_name,
                      rd.professional_profile.years_of_experience && `${rd.professional_profile.years_of_experience} yrs exp`,
                    ].filter(Boolean).join(' • ')}
                  </div>
                )}
                {rd.granted_at && (
                  <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: 4 }}>
                    {translate('Roles.added', { value: new Date(rd.granted_at).toLocaleDateString() })}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
                {rd.is_active && CLINICIAN_ROLES.includes(rd.role) && (
                  <button className="btn btn-sm btn-primary" onClick={openClinicianView}>
                    {translate('Roles.open_clinician_view')}
                  </button>
                )}
                {!rd.is_primary && (
                  <button className="btn btn-sm btn-secondary" onClick={() => handleSetPrimary(rd.id)}>
                    {translate('Roles.set_primary')}
                  </button>
                )}
                <button className="btn btn-sm btn-primary" onClick={() => openProfileEditor(rd)}>
                  {rd.professional_profile ? 'Edit Profile' : 'Add Profile'}
                </button>
                <button className="btn btn-sm btn-danger" onClick={() => handleRemove(rd.id)}>
                  {translate('Roles.remove')}
                </button>
              </div>
            </div>
          ))}

          {persona.role_details.length === 0 && (
            <div className="card" style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-secondary)' }}>
              {translate('Roles.no_professional_roles_added_yet_click')}
            </div>
          )}
        </div>
      )}

      {/* ── Add role tab ──────────────────────────────────────── */}
      {tab === 'add' && (
        <div>
          <div className="card" style={{ marginBottom: '1rem' }}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Roles.filter_by_category')}</label>
                <select className="form-input" value={selectedCategory}
                  onChange={e => setSelectedCategory(e.target.value)}>
                  <option value="">{translate('Roles.all_categories')}</option>
                  {catalog.map(c => (
                    <option key={c.id} value={c.id}>
                      {CATEGORY_ICONS[c.id] || '📌'} {c.name} ({c.roles.length})
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.search_roles')}</label>
                <input className="form-input" placeholder={translate('Roles.e_g_cardiologist_nurse')}
                  value={roleSearch} onChange={e => setRoleSearch(e.target.value)} />
              </div>
            </div>
          </div>

          {filteredCatalog.map(cat => (
            <div key={cat.id} style={{ marginBottom: '1.5rem' }}>
              <h3 style={{ marginBottom: 8, fontSize: '1rem', color: 'var(--color-text-secondary)' }}>
                {CATEGORY_ICONS[cat.id] || '📌'} {cat.name}
              </h3>
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8,
              }}>
                {cat.roles.map(role => (
                  <div key={role.id} className="card" style={{
                    padding: '12px 16px', display: 'flex', alignItems: 'center',
                    justifyContent: 'space-between', gap: 8,
                  }}>
                    <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>{role.name}</span>
                    <button className="btn btn-sm btn-primary" disabled={adding}
                      onClick={() => handleAddRole(role.id)}>
                      {translate('Roles.add')}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {filteredCatalog.length === 0 && (
            <div className="card" style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-secondary)' }}>
              {roleSearch || selectedCategory
                ? 'No matching roles found. Try a different search or category.'
                : 'All available roles have already been added.'}
            </div>
          )}
        </div>
      )}

      {/* ── Professional profile editor ───────────────────────── */}
      {tab === 'profile' && editRoleId && (
        <div className="card">
          <h3 style={{ marginBottom: '1rem' }}>{translate('Roles.professional_profile')}</h3>
          <form onSubmit={handleSaveProfile}>
            {/* Credentials */}
            <h4 style={{ marginBottom: 8, marginTop: 16, color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
              {translate('Roles.credentials_licensing')}
            </h4>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Roles.license_number')}</label>
                <input className="form-input" value={profileForm.license_number || ''}
                  onChange={e => updatePF('license_number', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.license_state')}</label>
                <input className="form-input" value={profileForm.license_state || ''}
                  onChange={e => updatePF('license_state', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.license_country')}</label>
                <input className="form-input" value={profileForm.license_country || ''}
                  onChange={e => updatePF('license_country', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Roles.license_expiry')}</label>
                <input className="form-input" type="date" value={profileForm.license_expiry || ''}
                  onChange={e => updatePF('license_expiry', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.npi_number')}</label>
                <input className="form-input" value={profileForm.npi_number || ''}
                  onChange={e => updatePF('npi_number', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.dea_number')}</label>
                <input className="form-input" value={profileForm.dea_number || ''}
                  onChange={e => updatePF('dea_number', e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">{translate('Roles.board_certifications_comma_separated')}</label>
              <input className="form-input" value={profileForm.board_certifications || ''}
                onChange={e => updatePF('board_certifications', e.target.value)}
                placeholder={translate('Roles.e_g_abim_internal_medicine_abms')} />
            </div>

            {/* Education */}
            <h4 style={{ marginBottom: 8, marginTop: 24, color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
              {translate('Roles.education_training')}
            </h4>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Roles.medical_school_institution')}</label>
                <input className="form-input" value={profileForm.medical_school || ''}
                  onChange={e => updatePF('medical_school', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.degree')}</label>
                <input className="form-input" value={profileForm.degree || ''}
                  onChange={e => updatePF('degree', e.target.value)} placeholder="e.g. MD, DO, DNP" />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.graduation_year')}</label>
                <input className="form-input" type="number" value={profileForm.graduation_year || ''}
                  onChange={e => updatePF('graduation_year', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Roles.residency_program')}</label>
                <input className="form-input" value={profileForm.residency_program || ''}
                  onChange={e => updatePF('residency_program', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.fellowship_program')}</label>
                <input className="form-input" value={profileForm.fellowship_program || ''}
                  onChange={e => updatePF('fellowship_program', e.target.value)} />
              </div>
            </div>

            {/* Practice */}
            <h4 style={{ marginBottom: 8, marginTop: 24, color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
              {translate('Roles.specialty_practice')}
            </h4>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Roles.specialty')}</label>
                <input className="form-input" value={profileForm.specialty || ''}
                  onChange={e => updatePF('specialty', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.sub_specialty')}</label>
                <input className="form-input" value={profileForm.sub_specialty || ''}
                  onChange={e => updatePF('sub_specialty', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.years_of_experience')}</label>
                <input className="form-input" type="number" value={profileForm.years_of_experience || ''}
                  onChange={e => updatePF('years_of_experience', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Roles.practice_name')}</label>
                <input className="form-input" value={profileForm.practice_name || ''}
                  onChange={e => updatePF('practice_name', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.practice_type')}</label>
                <select className="form-input" value={profileForm.practice_type || ''}
                  onChange={e => updatePF('practice_type', e.target.value)}>
                  <option value="">{translate('Roles.select')}</option>
                  <option value="solo">{translate('Roles.solo_practice')}</option>
                  <option value="group">{translate('Roles.group_practice')}</option>
                  <option value="hospital">{translate('Roles.hospital')}</option>
                  <option value="clinic">{translate('Roles.clinic')}</option>
                  <option value="academic">{translate('Roles.academic_teaching')}</option>
                  <option value="government">{translate('Roles.government')}</option>
                  <option value="telehealth">{translate('Roles.telehealth_only')}</option>
                  <option value="community_health">{translate('Roles.community_health_center')}</option>
                  <option value="research">{translate('Roles.research_institution')}</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Roles.practice_address')}</label>
                <input className="form-input" value={profileForm.practice_address || ''}
                  onChange={e => updatePF('practice_address', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.practice_phone')}</label>
                <input className="form-input" value={profileForm.practice_phone || ''}
                  onChange={e => updatePF('practice_phone', e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Roles.practice_email')}</label>
                <input className="form-input" type="email" value={profileForm.practice_email || ''}
                  onChange={e => updatePF('practice_email', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.practice_website')}</label>
                <input className="form-input" value={profileForm.practice_website || ''}
                  onChange={e => updatePF('practice_website', e.target.value)} />
              </div>
              <div className="form-group" style={{ display: 'flex', alignItems: 'flex-end' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={profileForm.accepting_patients || false}
                    onChange={e => updatePF('accepting_patients', e.target.checked)} />
                  <span className="form-label" style={{ margin: 0 }}>{translate('Roles.accepting_patients')}</span>
                </label>
              </div>
            </div>

            {/* Hospital & Department */}
            <h4 style={{ marginBottom: 8, marginTop: 24, color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
              {translate('Roles.hospital_affiliations')}
            </h4>
            <div className="form-group">
              <label className="form-label">{translate('Roles.hospital_affiliations_comma_separated')}</label>
              <input className="form-input" value={profileForm.hospital_affiliations || ''}
                onChange={e => updatePF('hospital_affiliations', e.target.value)}
                placeholder={translate('Roles.e_g_johns_hopkins_mayo_clinic')} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{translate('Roles.department')}</label>
                <input className="form-input" value={profileForm.department || ''}
                  onChange={e => updatePF('department', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.title')}</label>
                <input className="form-input" value={profileForm.title || ''}
                  onChange={e => updatePF('title', e.target.value)} placeholder={translate('Roles.e_g_chief_of_surgery_attending')} />
              </div>
            </div>

            {/* Languages & Telemedicine */}
            <h4 style={{ marginBottom: 8, marginTop: 24, color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
              {translate('Roles.languages_telemedicine')}
            </h4>
            <div className="form-group">
              <label className="form-label">{translate('Roles.clinical_languages_comma_separated')}</label>
              <input className="form-input" value={profileForm.clinical_languages || ''}
                onChange={e => updatePF('clinical_languages', e.target.value)}
                placeholder={translate('Roles.e_g_english_spanish_french')} />
            </div>
            <div className="form-row">
              <div className="form-group" style={{ display: 'flex', alignItems: 'flex-end' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={profileForm.telemedicine_available || false}
                    onChange={e => updatePF('telemedicine_available', e.target.checked)} />
                  <span className="form-label" style={{ margin: 0 }}>{translate('Roles.telemedicine_available')}</span>
                </label>
              </div>
              <div className="form-group">
                <label className="form-label">{translate('Roles.telemedicine_platforms_comma_separated')}</label>
                <input className="form-input" value={profileForm.telemedicine_platforms || ''}
                  onChange={e => updatePF('telemedicine_platforms', e.target.value)}
                  placeholder={translate('Roles.e_g_zoom_doxy_me_teladoc')} />
              </div>
            </div>

            {/* Bio & Research */}
            <h4 style={{ marginBottom: 8, marginTop: 24, color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>
              {translate('Roles.bio_research')}
            </h4>
            <div className="form-group">
              <label className="form-label">{translate('Roles.professional_bio')}</label>
              <textarea className="form-input" rows={4} value={profileForm.professional_bio || ''}
                onChange={e => updatePF('professional_bio', e.target.value)}
                placeholder={translate('Roles.brief_professional_biography')} />
            </div>
            <div className="form-group">
              <label className="form-label">{translate('Roles.publications_comma_separated')}</label>
              <textarea className="form-input" rows={2} value={profileForm.publications || ''}
                onChange={e => updatePF('publications', e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">{translate('Roles.research_interests_comma_separated')}</label>
              <input className="form-input" value={profileForm.research_interests || ''}
                onChange={e => updatePF('research_interests', e.target.value)} />
            </div>

            {profileMsg && (
              <div style={{
                color: profileMsg.includes('success') ? 'var(--color-primary)' : 'var(--color-danger)',
                marginBottom: '1rem',
              }}>
                {profileMsg}
              </div>
            )}

            <div style={{ display: 'flex', gap: 12, marginTop: '1rem' }}>
              <button className="btn btn-primary" type="submit" disabled={savingProfile}>
                {savingProfile ? 'Saving...' : 'Save Professional Profile'}
              </button>
              <button className="btn btn-secondary" type="button"
                onClick={() => { setTab('overview'); setEditRoleId(null); }}>
                {translate('Roles.cancel')}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
