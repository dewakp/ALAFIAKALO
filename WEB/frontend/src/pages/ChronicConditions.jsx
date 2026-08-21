import React, { useState, useEffect } from 'react';
import api from '../services/api';
import BackButton from '../components/BackButton';
import ICD11Picker from '../components/ICD11Picker';

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
    { value: 'cancer', label: 'Cancer' },
    { value: 'renal', label: 'Kidney/Renal Disease' },
    { value: 'diabetes', label: 'Diabetes' },
    { value: 'blood_disorder', label: 'Blood Disorder (G6PD, etc.)' },
    { value: 'cardiovascular', label: 'Cardiovascular' },
    { value: 'respiratory', label: 'Respiratory' },
    { value: 'autoimmune', label: 'Autoimmune' },
    { value: 'neurological', label: 'Neurological' },
    { value: 'endocrine', label: 'Endocrine' },
    { value: 'other', label: 'Other' }
  ];

  const severities = [
    { value: 'mild', label: 'Mild' },
    { value: 'moderate', label: 'Moderate' },
    { value: 'severe', label: 'Severe' },
    { value: 'critical', label: 'Critical' },
    { value: 'remission', label: 'In Remission' }
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
      alert(typeof detail === 'string' ? detail : 'Failed to save condition');
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
    if (!confirm('Are you sure you want to delete this condition?')) return;
    
    try {
      await api.delete(`/chronic/conditions/${id}`);
      loadConditions();
    } catch (error) {
      console.error('Failed to delete condition:', error);
      alert('Failed to delete condition');
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
    return <div style={{ textAlign: 'center', padding: '50px' }}>Loading...</div>;
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
        <div className="page-header">
          <div className="page-header-left">
            <BackButton />
            <h1>Chronic Health Conditions</h1>
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
          + Add Condition
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
                  Condition Name *
                </label>
                <input
                  type="text"
                  value={formData.condition_name}
                  onChange={(e) => setFormData({ ...formData, condition_name: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder="e.g., Type 2 Diabetes, Chronic Kidney Disease Stage 3"
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Category *
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
                  ICD-10 Code
                </label>
                <input
                  type="text"
                  value={formData.icd10_code}
                  onChange={(e) => setFormData({ ...formData, icd10_code: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder="e.g., E11.9, N18.3 — usually filled in from an imported record"
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Severity *
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
                  Diagnosis Date
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
                  Diagnosed By
                </label>
                <input
                  type="text"
                  value={formData.diagnosed_by}
                  onChange={(e) => setFormData({ ...formData, diagnosed_by: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder="Doctor's name"
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Diagnosing Facility
                </label>
                <input
                  type="text"
                  value={formData.diagnosing_facility}
                  onChange={(e) => setFormData({ ...formData, diagnosing_facility: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder="Hospital/clinic name"
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Stage/Classification
                </label>
                <input
                  type="text"
                  value={formData.stage}
                  onChange={(e) => setFormData({ ...formData, stage: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder="e.g., Stage IIIA, ESRD"
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Grade
                </label>
                <input
                  type="text"
                  value={formData.grade}
                  onChange={(e) => setFormData({ ...formData, grade: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder="e.g., Grade 2"
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Primary Physician
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
                  Specialist Physician
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
                  Monitoring Frequency
                </label>
                <input
                  type="text"
                  value={formData.monitoring_frequency}
                  onChange={(e) => setFormData({ ...formData, monitoring_frequency: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder="e.g., Monthly, Every 3 months"
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Next Appointment
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
                Current Treatment Plan
              </label>
              <textarea
                value={formData.current_treatment_plan}
                onChange={(e) => setFormData({ ...formData, current_treatment_plan: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '80px' }}
                placeholder="Describe the current treatment approach..."
              />
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                Symptoms
              </label>
              <textarea
                value={formData.symptoms}
                onChange={(e) => setFormData({ ...formData, symptoms: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '60px' }}
                placeholder="Common symptoms experienced..."
              />
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                Complications
              </label>
              <textarea
                value={formData.complications}
                onChange={(e) => setFormData({ ...formData, complications: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '60px' }}
                placeholder="Any complications or concerns..."
              />
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                Notes
              </label>
              <textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '80px' }}
                placeholder="Additional notes..."
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
                <span style={{ fontWeight: 'bold' }}>Condition is currently active</span>
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
                Cancel
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
            Retry
          </button>
        </div>
      ) : conditions.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '50px', color: '#666' }}>
          <p>No chronic conditions recorded yet.</p>
          <p>Click "Add Condition" to get started.</p>
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
                      <strong>Category:</strong> {categories.find(c => c.value === condition.category)?.label}
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
                        <strong>Diagnosed:</strong> {new Date(condition.diagnosis_date).toLocaleDateString()}
                        {condition.diagnosed_by && ` by ${condition.diagnosed_by}`}
                      </p>
                    )}
                    {condition.stage && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>Stage:</strong> {condition.stage}
                        {condition.grade && ` | Grade: ${condition.grade}`}
                      </p>
                    )}
                    {condition.primary_physician && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>Primary Physician:</strong> {condition.primary_physician}
                      </p>
                    )}
                    {condition.specialist_physician && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>Specialist:</strong> {condition.specialist_physician}
                      </p>
                    )}
                    {condition.next_appointment && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>Next Appointment:</strong> {new Date(condition.next_appointment).toLocaleDateString()}
                      </p>
                    )}
                    {condition.current_treatment_plan && (
                      <p style={{ margin: '10px 0', padding: '10px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                        <strong>Treatment Plan:</strong><br />
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
                    Edit
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
                    Delete
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
