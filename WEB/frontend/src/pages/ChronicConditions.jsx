import React, { useState, useEffect } from 'react';
import api from '../services/api';
import BackButton from '../components/BackButton';
import ICD11Picker from '../components/ICD11Picker';
import { t } from '../i18n';

const ChronicConditions = () => {
  const [conditions, setConditions] = useState([]);
  const [loading, setLoading] = useState(true);
  // Kept separate from `conditions` on purpose: a failed fetch must never
  // render as "No chronic conditions recorded yet" (CLAUDE.md §3aa).
  const [loadError, setLoadError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [formData, setFormData] = useState({
    condition_name: '',
    category: 'other',
    icd10_code: '',
    icd11_code: '',
    icd11_title: '',
    severity: 'moderate',
    diagnosis_date: '',
    diagnosed_by: '',
    diagnosing_facility: '',
    stage: '',
    grade: '',
    current_treatment_plan: '',
    primary_physician: '',
    specialist_physician: '',
    monitoring_frequency: '',
    next_appointment: '',
    notes: '',
    symptoms: '',
    complications: '',
    is_active: true
  });

  const categories = [
    { value: 'cancer', label: t('ChronicConditions.cancer') },
    { value: 'renal', label: t('ChronicConditions.kidney_renal_disease') },
    { value: 'diabetes', label: t('ChronicConditions.diabetes') },
    { value: 'blood_disorder', label: t('ChronicConditions.blood_disorder_g6pd_etc') },
    { value: 'cardiovascular', label: t('ChronicConditions.cardiovascular') },
    { value: 'respiratory', label: t('ChronicConditions.respiratory') },
    { value: 'autoimmune', label: t('ChronicConditions.autoimmune') },
    { value: 'neurological', label: t('ChronicConditions.neurological') },
    { value: 'endocrine', label: t('ChronicConditions.endocrine') },
    { value: 'other', label: t('ChronicConditions.other') }
  ];

  const severities = [
    { value: 'mild', label: t('ChronicConditions.mild') },
    { value: 'moderate', label: t('ChronicConditions.moderate') },
    { value: 'severe', label: t('ChronicConditions.severe') },
    { value: 'critical', label: t('ChronicConditions.critical') },
    { value: 'remission', label: t('ChronicConditions.in_remission') }
  ];

  useEffect(() => {
    loadConditions();
  }, []);

  const loadConditions = async () => {
    try {
      // Ask for the maximum the endpoint allows. The default page size is
      // 100, and a truncated page here would silently hide conditions from a
      // patient who has many — the same shape of bug as a LIMIT being reported
      // as a count (CLAUDE.md §3aa).
      const response = await api.get('/chronic/conditions', { params: { limit: 1000 } });
      setConditions(response.data);
      setLoadError(null);
    } catch (error) {
      console.error('Failed to load conditions:', error);
      setLoadError(
        'Could not load your conditions. This is a loading problem, not an empty list — '
        + 'please retry before assuming nothing is recorded.'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...formData };
      
      // Convert empty strings to null for datetime fields
      if (!payload.diagnosis_date) payload.diagnosis_date = null;
      if (!payload.next_appointment) payload.next_appointment = null;

      if (editing) {
        await api.put(`/chronic/conditions/${editing.id}`, payload);
      } else {
        await api.post('/chronic/conditions', payload);
      }
      
      setShowForm(false);
      setEditing(null);
      resetForm();
      loadConditions();
    } catch (error) {
      console.error('Failed to save condition:', error);
      // Surface the server's reason. The ICD-11 check replies 422 with the
      // specific problem ("code 'ZZ99.9' does not exist"); a flat "failed to
      // save" leaves the patient with no idea which field to correct.
      const detail = error?.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : t('ChronicConditions.failed_to_save_condition'));
    }
  };

  const handleEdit = (condition) => {
    setEditing(condition);
    setFormData({
      condition_name: condition.condition_name || '',
      category: condition.category || 'other',
      icd10_code: condition.icd10_code || '',
      icd11_code: condition.icd11_code || '',
      icd11_title: condition.icd11_title || '',
      severity: condition.severity || 'moderate',
      diagnosis_date: condition.diagnosis_date ? condition.diagnosis_date.split('T')[0] : '',
      diagnosed_by: condition.diagnosed_by || '',
      diagnosing_facility: condition.diagnosing_facility || '',
      stage: condition.stage || '',
      grade: condition.grade || '',
      current_treatment_plan: condition.current_treatment_plan || '',
      primary_physician: condition.primary_physician || '',
      specialist_physician: condition.specialist_physician || '',
      monitoring_frequency: condition.monitoring_frequency || '',
      next_appointment: condition.next_appointment ? condition.next_appointment.split('T')[0] : '',
      notes: condition.notes || '',
      symptoms: condition.symptoms || '',
      complications: condition.complications || '',
      is_active: condition.is_active !== false
    });
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    if (!confirm(t('ChronicConditions.are_you_sure_you_want_to_delete_this'))) return;
    
    try {
      await api.delete(`/chronic/conditions/${id}`);
      loadConditions();
    } catch (error) {
      console.error('Failed to delete condition:', error);
      alert(t('ChronicConditions.failed_to_delete_condition'));
    }
  };

  const resetForm = () => {
    setFormData({
      condition_name: '',
      category: 'other',
      icd10_code: '',
      icd11_code: '',
      icd11_title: '',
      severity: 'moderate',
      diagnosis_date: '',
      diagnosed_by: '',
      diagnosing_facility: '',
      stage: '',
      grade: '',
      current_treatment_plan: '',
      primary_physician: '',
      specialist_physician: '',
      monitoring_frequency: '',
      next_appointment: '',
      notes: '',
      symptoms: '',
      complications: '',
      is_active: true
    });
  };

  const getSeverityColor = (severity) => {
    const colors = {
      mild: '#4CAF50',
      moderate: '#FF9800',
      severe: '#F44336',
      critical: '#D32F2F',
      remission: '#2196F3'
    };
    return colors[severity] || '#9E9E9E';
  };

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '50px' }}>{t('ChronicConditions.loading')}</div>;
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
        <div className="page-header">
          <div className="page-header-left">
            <BackButton />
            <h1>{t('ChronicConditions.chronic_health_conditions')}</h1>
          </div>
        </div>
        <button
          onClick={() => {
            setEditing(null);
            resetForm();
            setShowForm(true);
          }}
          style={{
            padding: '12px 24px',
            backgroundColor: '#1976D2',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '16px'
          }}
        >
          {t('ChronicConditions.add_condition')}
        </button>
      </div>

      {showForm && (
        <div style={{
          backgroundColor: '#f5f5f5',
          padding: '30px',
          borderRadius: '8px',
          marginBottom: '30px'
        }}>
          <h2>{editing ? 'Edit Condition' : 'Add New Condition'}</h2>
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.condition_name')}
                </label>
                <input
                  type="text"
                  value={formData.condition_name}
                  onChange={(e) => setFormData({ ...formData, condition_name: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder={t('ChronicConditions.e_g_type_2_diabetes_chronic_kidney')}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.category')}
                </label>
                <select
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                >
                  {categories.map(cat => (
                    <option key={cat.value} value={cat.value}>{cat.label}</option>
                  ))}
                </select>
              </div>

              <ICD11Picker
                code={formData.icd11_code}
                title={formData.icd11_title}
                onChange={({ code, title }) =>
                  setFormData({ ...formData, icd11_code: code, icd11_title: title })
                }
              />

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.icd_10_code')}
                </label>
                <input
                  type="text"
                  value={formData.icd10_code}
                  onChange={(e) => setFormData({ ...formData, icd10_code: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder={t('ChronicConditions.e_g_e11_9_n18_3_usually_filled_in_from')}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.severity')}
                </label>
                <select
                  value={formData.severity}
                  onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                >
                  {severities.map(sev => (
                    <option key={sev.value} value={sev.value}>{sev.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.diagnosis_date')}
                </label>
                <input
                  type="date"
                  value={formData.diagnosis_date}
                  onChange={(e) => setFormData({ ...formData, diagnosis_date: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.diagnosed_by')}
                </label>
                <input
                  type="text"
                  value={formData.diagnosed_by}
                  onChange={(e) => setFormData({ ...formData, diagnosed_by: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder={t('ChronicConditions.doctor_s_name')}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.diagnosing_facility')}
                </label>
                <input
                  type="text"
                  value={formData.diagnosing_facility}
                  onChange={(e) => setFormData({ ...formData, diagnosing_facility: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder={t('ChronicConditions.hospital_clinic_name')}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.stage_classification')}
                </label>
                <input
                  type="text"
                  value={formData.stage}
                  onChange={(e) => setFormData({ ...formData, stage: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder={t('ChronicConditions.e_g_stage_iiia_esrd')}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.grade')}
                </label>
                <input
                  type="text"
                  value={formData.grade}
                  onChange={(e) => setFormData({ ...formData, grade: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder={t('ChronicConditions.e_g_grade_2')}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.primary_physician')}
                </label>
                <input
                  type="text"
                  value={formData.primary_physician}
                  onChange={(e) => setFormData({ ...formData, primary_physician: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.specialist_physician')}
                </label>
                <input
                  type="text"
                  value={formData.specialist_physician}
                  onChange={(e) => setFormData({ ...formData, specialist_physician: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.monitoring_frequency')}
                </label>
                <input
                  type="text"
                  value={formData.monitoring_frequency}
                  onChange={(e) => setFormData({ ...formData, monitoring_frequency: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder={t('ChronicConditions.e_g_monthly_every_3_months')}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  {t('ChronicConditions.next_appointment')}
                </label>
                <input
                  type="date"
                  value={formData.next_appointment}
                  onChange={(e) => setFormData({ ...formData, next_appointment: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                />
              </div>
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                {t('ChronicConditions.current_treatment_plan')}
              </label>
              <textarea
                value={formData.current_treatment_plan}
                onChange={(e) => setFormData({ ...formData, current_treatment_plan: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '80px' }}
                placeholder={t('ChronicConditions.describe_the_current_treatment_approach')}
              />
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                {t('ChronicConditions.symptoms')}
              </label>
              <textarea
                value={formData.symptoms}
                onChange={(e) => setFormData({ ...formData, symptoms: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '60px' }}
                placeholder={t('ChronicConditions.common_symptoms_experienced')}
              />
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                {t('ChronicConditions.complications')}
              </label>
              <textarea
                value={formData.complications}
                onChange={(e) => setFormData({ ...formData, complications: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '60px' }}
                placeholder={t('ChronicConditions.any_complications_or_concerns')}
              />
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                {t('ChronicConditions.notes')}
              </label>
              <textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '80px' }}
                placeholder={t('ChronicConditions.additional_notes')}
              />
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  style={{ marginRight: '8px' }}
                />
                <span style={{ fontWeight: 'bold' }}>{t('ChronicConditions.condition_is_currently_active')}</span>
              </label>
            </div>

            <div style={{ marginTop: '30px', display: 'flex', gap: '10px' }}>
              <button
                type="submit"
                style={{
                  padding: '12px 24px',
                  backgroundColor: '#1976D2',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '16px'
                }}
              >
                {editing ? 'Update Condition' : 'Create Condition'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowForm(false);
                  setEditing(null);
                  resetForm();
                }}
                style={{
                  padding: '12px 24px',
                  backgroundColor: '#757575',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '16px'
                }}
              >
                {t('ChronicConditions.cancel')}
              </button>
            </div>
          </form>
        </div>
      )}

      {loadError ? (
        <div
          data-testid="conditions-load-error"
          style={{
            textAlign: 'center', padding: '40px', backgroundColor: '#fdecea',
            border: '1px solid #f5c6cb', borderRadius: '8px', color: '#a12622'
          }}
        >
          <p style={{ fontWeight: 600 }}>{loadError}</p>
          <button
            type="button"
            onClick={() => { setLoading(true); loadConditions(); }}
            style={{
              marginTop: '10px', padding: '8px 20px', borderRadius: '4px',
              border: 'none', backgroundColor: '#a12622', color: 'white', cursor: 'pointer'
            }}
          >
            {t('ChronicConditions.retry')}
          </button>
        </div>
      ) : conditions.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '50px', color: '#666' }}>
          <p>{t('ChronicConditions.no_chronic_conditions_recorded_yet')}</p>
          <p>{t('ChronicConditions.click_add_condition_to_get_started')}</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '20px' }}>
          {conditions.map((condition) => (
            <div
              key={condition.id}
              style={{
                backgroundColor: 'white',
                border: '1px solid #e0e0e0',
                borderRadius: '8px',
                padding: '20px',
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                <div style={{ flex: 1 }}>
                  <h3 style={{ margin: '0 0 10px 0', display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {condition.condition_name}
                    <span
                      style={{
                        fontSize: '12px',
                        padding: '4px 12px',
                        borderRadius: '12px',
                        backgroundColor: getSeverityColor(condition.severity),
                        color: 'white',
                        fontWeight: 'normal'
                      }}
                    >
                      {condition.severity.toUpperCase()}
                    </span>
                    {!condition.is_active && (
                      <span style={{
                        fontSize: '12px',
                        padding: '4px 12px',
                        borderRadius: '12px',
                        backgroundColor: '#9E9E9E',
                        color: 'white'
                      }}>
                        INACTIVE
                      </span>
                    )}
                  </h3>
                  
                  <div style={{ color: '#666', marginBottom: '15px' }}>
                    <p style={{ margin: '5px 0' }}>
                      <strong>{t('ChronicConditions.category_2')}</strong> {categories.find(c => c.value === condition.category)?.label}
                      {condition.icd11_code && ` | ICD-11: ${condition.icd11_code}`}
                      {condition.icd10_code && ` | ICD-10: ${condition.icd10_code}`}
                    </p>
                    {condition.icd11_title && (
                      <p style={{ margin: '5px 0', fontSize: '0.85rem', fontStyle: 'italic' }}>
                        {condition.icd11_title}
                      </p>
                    )}
                    {condition.diagnosis_date && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>{t('ChronicConditions.diagnosed')}</strong> {new Date(condition.diagnosis_date).toLocaleDateString()}
                        {condition.diagnosed_by && ` by ${condition.diagnosed_by}`}
                      </p>
                    )}
                    {condition.stage && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>{t('ChronicConditions.stage')}</strong> {condition.stage}
                        {condition.grade && ` | Grade: ${condition.grade}`}
                      </p>
                    )}
                    {condition.primary_physician && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>{t('ChronicConditions.primary_physician_2')}</strong> {condition.primary_physician}
                      </p>
                    )}
                    {condition.specialist_physician && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>{t('ChronicConditions.specialist')}</strong> {condition.specialist_physician}
                      </p>
                    )}
                    {condition.next_appointment && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>{t('ChronicConditions.next_appointment_2')}</strong> {new Date(condition.next_appointment).toLocaleDateString()}
                      </p>
                    )}
                    {condition.current_treatment_plan && (
                      <p style={{ margin: '10px 0', padding: '10px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                        <strong>{t('ChronicConditions.treatment_plan')}</strong><br />
                        {condition.current_treatment_plan}
                      </p>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '10px', marginLeft: '20px' }}>
                  <button
                    onClick={() => handleEdit(condition)}
                    style={{
                      padding: '8px 16px',
                      backgroundColor: '#1976D2',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer'
                    }}
                  >
                    {t('ChronicConditions.edit')}
                  </button>
                  <button
                    onClick={() => handleDelete(condition.id)}
                    style={{
                      padding: '8px 16px',
                      backgroundColor: '#F44336',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer'
                    }}
                  >
                    {t('ChronicConditions.delete')}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ChronicConditions;
