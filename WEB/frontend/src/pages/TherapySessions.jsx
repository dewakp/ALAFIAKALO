import { fmtDateTime } from '../utils/datetime';
import React, { useState, useEffect } from 'react';
import api from '../services/api';
import BackButton from '../components/BackButton';
import DrugsAdministered from '../components/DrugsAdministered';

const TherapySessions = () => {
  const [sessions, setSessions] = useState([]);
  const [conditions, setConditions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [formData, setFormData] = useState({
    condition_id: '',
    therapy_type: 'dialysis',
    therapy_name: '',
    session_number: '',
    total_sessions_planned: '',
    scheduled_date: '',
    status: 'scheduled',
    facility_name: '',
    facility_address: '',
    attending_physician: '',
    attending_nurse: '',
    // Dialysis
    dialysis_access_type: '',
    pre_dialysis_weight_kg: '',
    post_dialysis_weight_kg: '',
    fluid_removed_ml: '',
    // Chemo
    drugs_administered: '',
    dosage: '',
    route_of_administration: '',
    // Vitals
    pre_systolic_bp: '',
    pre_diastolic_bp: '',
    post_systolic_bp: '',
    post_diastolic_bp: '',
    // Notes
    side_effects: '',
    clinical_notes: '',
    patient_notes: ''
  });

  const therapyTypes = [
    { value: 'dialysis', label: 'Dialysis' },
    { value: 'hemodialysis', label: 'Hemodialysis' },
    { value: 'peritoneal_dialysis', label: 'Peritoneal Dialysis' },
    { value: 'chemotherapy', label: 'Chemotherapy' },
    { value: 'radiation_therapy', label: 'Radiation Therapy' },
    { value: 'immunotherapy', label: 'Immunotherapy' },
    { value: 'targeted_therapy', label: 'Targeted Therapy' },
    { value: 'hormone_therapy', label: 'Hormone Therapy' },
    { value: 'infusion_therapy', label: 'Infusion Therapy' },
    { value: 'blood_transfusion', label: 'Blood Transfusion' },
    { value: 'other', label: 'Other' }
  ];

  const statuses = [
    { value: 'scheduled', label: 'Scheduled' },
    { value: 'in_progress', label: 'In Progress' },
    { value: 'completed', label: 'Completed' },
    { value: 'cancelled', label: 'Cancelled' },
    { value: 'missed', label: 'Missed' }
  ];

  useEffect(() => {
    loadSessions();
    loadConditions();
  }, []);

  const loadSessions = async () => {
    try {
      const response = await api.get('/chronic/therapy-sessions');
      setSessions(response.data);
    } catch (error) {
      console.error('Failed to load therapy sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadConditions = async () => {
    try {
      const response = await api.get('/chronic/conditions?is_active=true');
      setConditions(response.data);
    } catch (error) {
      console.error('Failed to load conditions:', error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const payload = { ...formData };
      
      // Convert empty strings to null
      Object.keys(payload).forEach(key => {
        if (payload[key] === '') payload[key] = null;
      });

      // Convert numeric fields
      if (payload.session_number) payload.session_number = parseInt(payload.session_number);
      if (payload.total_sessions_planned) payload.total_sessions_planned = parseInt(payload.total_sessions_planned);
      if (payload.pre_dialysis_weight_kg) payload.pre_dialysis_weight_kg = parseFloat(payload.pre_dialysis_weight_kg);
      if (payload.post_dialysis_weight_kg) payload.post_dialysis_weight_kg = parseFloat(payload.post_dialysis_weight_kg);
      if (payload.fluid_removed_ml) payload.fluid_removed_ml = parseFloat(payload.fluid_removed_ml);
      if (payload.pre_systolic_bp) payload.pre_systolic_bp = parseInt(payload.pre_systolic_bp);
      if (payload.pre_diastolic_bp) payload.pre_diastolic_bp = parseInt(payload.pre_diastolic_bp);
      if (payload.post_systolic_bp) payload.post_systolic_bp = parseInt(payload.post_systolic_bp);
      if (payload.post_diastolic_bp) payload.post_diastolic_bp = parseInt(payload.post_diastolic_bp);

      if (editing) {
        await api.put(`/chronic/therapy-sessions/${editing.id}`, payload);
      } else {
        await api.post('/chronic/therapy-sessions', payload);
      }
      
      setShowForm(false);
      setEditing(null);
      resetForm();
      loadSessions();
    } catch (error) {
      console.error('Failed to save session:', error);
      alert('Failed to save therapy session');
    }
  };

  const handleEdit = (session) => {
    setEditing(session);
    setFormData({
      condition_id: session.condition_id || '',
      therapy_type: session.therapy_type || 'dialysis',
      therapy_name: session.therapy_name || '',
      session_number: session.session_number || '',
      total_sessions_planned: session.total_sessions_planned || '',
      scheduled_date: session.scheduled_date ? session.scheduled_date.split('T')[0] : '',
      status: session.status || 'scheduled',
      facility_name: session.facility_name || '',
      facility_address: session.facility_address || '',
      attending_physician: session.attending_physician || '',
      attending_nurse: session.attending_nurse || '',
      dialysis_access_type: session.dialysis_access_type || '',
      pre_dialysis_weight_kg: session.pre_dialysis_weight_kg || '',
      post_dialysis_weight_kg: session.post_dialysis_weight_kg || '',
      fluid_removed_ml: session.fluid_removed_ml || '',
      drugs_administered: session.drugs_administered || '',
      dosage: session.dosage || '',
      route_of_administration: session.route_of_administration || '',
      pre_systolic_bp: session.pre_systolic_bp || '',
      pre_diastolic_bp: session.pre_diastolic_bp || '',
      post_systolic_bp: session.post_systolic_bp || '',
      post_diastolic_bp: session.post_diastolic_bp || '',
      side_effects: session.side_effects || '',
      clinical_notes: session.clinical_notes || '',
      patient_notes: session.patient_notes || ''
    });
    setShowForm(true);
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this therapy session?')) return;
    
    try {
      await api.delete(`/chronic/therapy-sessions/${id}`);
      loadSessions();
    } catch (error) {
      console.error('Failed to delete session:', error);
      alert('Failed to delete therapy session');
    }
  };

  const resetForm = () => {
    setFormData({
      condition_id: '',
      therapy_type: 'dialysis',
      therapy_name: '',
      session_number: '',
      total_sessions_planned: '',
      scheduled_date: '',
      status: 'scheduled',
      facility_name: '',
      facility_address: '',
      attending_physician: '',
      attending_nurse: '',
      dialysis_access_type: '',
      pre_dialysis_weight_kg: '',
      post_dialysis_weight_kg: '',
      fluid_removed_ml: '',
      drugs_administered: '',
      dosage: '',
      route_of_administration: '',
      pre_systolic_bp: '',
      pre_diastolic_bp: '',
      post_systolic_bp: '',
      post_diastolic_bp: '',
      side_effects: '',
      clinical_notes: '',
      patient_notes: ''
    });
  };

  const getStatusColor = (status) => {
    const colors = {
      scheduled: '#2196F3',
      in_progress: '#FF9800',
      completed: '#4CAF50',
      cancelled: '#9E9E9E',
      missed: '#F44336'
    };
    return colors[status] || '#9E9E9E';
  };

  const isDialysisSession = () => {
    return ['dialysis', 'hemodialysis', 'peritoneal_dialysis'].includes(formData.therapy_type);
  };

  const isChemoSession = () => {
    return ['chemotherapy', 'immunotherapy', 'targeted_therapy', 'hormone_therapy', 'infusion_therapy'].includes(formData.therapy_type);
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
            <h1>Therapy Sessions</h1>
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
          + Add Session
        </button>
      </div>

      {showForm && (
        <div style={{
          backgroundColor: '#f5f5f5',
          padding: '30px',
          borderRadius: '8px',
          marginBottom: '30px'
        }}>
          <h2>{editing ? 'Edit Session' : 'Add New Session'}</h2>
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Therapy Type *
                </label>
                <select
                  value={formData.therapy_type}
                  onChange={(e) => setFormData({ ...formData, therapy_type: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                >
                  {therapyTypes.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Related Condition
                </label>
                <select
                  value={formData.condition_id}
                  onChange={(e) => setFormData({ ...formData, condition_id: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                >
                  <option value="">-- Select Condition --</option>
                  {conditions.map(cond => (
                    <option key={cond.id} value={cond.id}>{cond.condition_name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Therapy Name
                </label>
                <input
                  type="text"
                  value={formData.therapy_name}
                  onChange={(e) => setFormData({ ...formData, therapy_name: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder="e.g., Cisplatin + Etoposide Protocol"
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Session Number
                </label>
                <input
                  type="number"
                  value={formData.session_number}
                  onChange={(e) => setFormData({ ...formData, session_number: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder="e.g., 3"
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Total Sessions Planned
                </label>
                <input
                  type="number"
                  value={formData.total_sessions_planned}
                  onChange={(e) => setFormData({ ...formData, total_sessions_planned: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                  placeholder="e.g., 12"
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Scheduled Date *
                </label>
                <input
                  type="date"
                  value={formData.scheduled_date}
                  onChange={(e) => setFormData({ ...formData, scheduled_date: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Status *
                </label>
                <select
                  value={formData.status}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                >
                  {statuses.map(st => (
                    <option key={st.value} value={st.value}>{st.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Facility Name
                </label>
                <input
                  type="text"
                  value={formData.facility_name}
                  onChange={(e) => setFormData({ ...formData, facility_name: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Attending Physician
                </label>
                <input
                  type="text"
                  value={formData.attending_physician}
                  onChange={(e) => setFormData({ ...formData, attending_physician: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                  Attending Nurse
                </label>
                <input
                  type="text"
                  value={formData.attending_nurse}
                  onChange={(e) => setFormData({ ...formData, attending_nurse: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                />
              </div>
            </div>

            {isDialysisSession() && (
              <div style={{ marginTop: '30px', padding: '20px', backgroundColor: '#e3f2fd', borderRadius: '6px' }}>
                <h3 style={{ marginTop: 0 }}>Dialysis-Specific Data</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                  <div>
                    <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                      Access Type
                    </label>
                    <input
                      type="text"
                      value={formData.dialysis_access_type}
                      onChange={(e) => setFormData({ ...formData, dialysis_access_type: e.target.value })}
                      style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                      placeholder="e.g., AV Fistula, Central Catheter"
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                      Pre-Dialysis Weight (kg)
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      value={formData.pre_dialysis_weight_kg}
                      onChange={(e) => setFormData({ ...formData, pre_dialysis_weight_kg: e.target.value })}
                      style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                      Post-Dialysis Weight (kg)
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      value={formData.post_dialysis_weight_kg}
                      onChange={(e) => setFormData({ ...formData, post_dialysis_weight_kg: e.target.value })}
                      style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                      Fluid Removed (mL)
                    </label>
                    <input
                      type="number"
                      step="0.1"
                      value={formData.fluid_removed_ml}
                      onChange={(e) => setFormData({ ...formData, fluid_removed_ml: e.target.value })}
                      style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    />
                  </div>
                </div>
              </div>
            )}

            {isChemoSession() && (
              <div style={{ marginTop: '30px', padding: '20px', backgroundColor: '#fff3e0', borderRadius: '6px' }}>
                <h3 style={{ marginTop: 0 }}>Chemotherapy/Infusion Data</h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px' }}>
                  <div>
                    <DrugsAdministered
                      value={formData.drugs_administered}
                      onChange={(text) => setFormData({ ...formData, drugs_administered: text })}
                    />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                    <div>
                      <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                        Dosage
                      </label>
                      <input
                        type="text"
                        value={formData.dosage}
                        onChange={(e) => setFormData({ ...formData, dosage: e.target.value })}
                        style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                        placeholder="e.g., 75mg/m²"
                      />
                    </div>
                    <div>
                      <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                        Route of Administration
                      </label>
                      <input
                        type="text"
                        value={formData.route_of_administration}
                        onChange={(e) => setFormData({ ...formData, route_of_administration: e.target.value })}
                        style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                        placeholder="e.g., IV, Oral"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div style={{ marginTop: '30px', padding: '20px', backgroundColor: '#f1f8e9', borderRadius: '6px' }}>
              <h3 style={{ marginTop: 0 }}>Vital Signs</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '15px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', fontSize: '14px' }}>
                    Pre-BP Systolic
                  </label>
                  <input
                    type="number"
                    value={formData.pre_systolic_bp}
                    onChange={(e) => setFormData({ ...formData, pre_systolic_bp: e.target.value })}
                    style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    placeholder="mmHg"
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', fontSize: '14px' }}>
                    Pre-BP Diastolic
                  </label>
                  <input
                    type="number"
                    value={formData.pre_diastolic_bp}
                    onChange={(e) => setFormData({ ...formData, pre_diastolic_bp: e.target.value })}
                    style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    placeholder="mmHg"
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', fontSize: '14px' }}>
                    Post-BP Systolic
                  </label>
                  <input
                    type="number"
                    value={formData.post_systolic_bp}
                    onChange={(e) => setFormData({ ...formData, post_systolic_bp: e.target.value })}
                    style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    placeholder="mmHg"
                  />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold', fontSize: '14px' }}>
                    Post-BP Diastolic
                  </label>
                  <input
                    type="number"
                    value={formData.post_diastolic_bp}
                    onChange={(e) => setFormData({ ...formData, post_diastolic_bp: e.target.value })}
                    style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd' }}
                    placeholder="mmHg"
                  />
                </div>
              </div>
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                Side Effects
              </label>
              <textarea
                value={formData.side_effects}
                onChange={(e) => setFormData({ ...formData, side_effects: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '60px' }}
                placeholder="Any side effects experienced..."
              />
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                Clinical Notes
              </label>
              <textarea
                value={formData.clinical_notes}
                onChange={(e) => setFormData({ ...formData, clinical_notes: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '60px' }}
                placeholder="Clinical observations..."
              />
            </div>

            <div style={{ marginTop: '20px' }}>
              <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>
                Patient Notes
              </label>
              <textarea
                value={formData.patient_notes}
                onChange={(e) => setFormData({ ...formData, patient_notes: e.target.value })}
                style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #ddd', minHeight: '60px' }}
                placeholder="Your personal notes about the session..."
              />
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
                {editing ? 'Update Session' : 'Create Session'}
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

      {sessions.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '50px', color: '#666' }}>
          <p>No therapy sessions recorded yet.</p>
          <p>Click "Add Session" to record your first session.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '20px' }}>
          {sessions.map((session) => (
            <div
              key={session.id}
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
                    {therapyTypes.find(t => t.value === session.therapy_type)?.label || session.therapy_type}
                    {session.session_number && ` - Session ${session.session_number}`}
                    {session.total_sessions_planned && ` of ${session.total_sessions_planned}`}
                    <span
                      style={{
                        fontSize: '12px',
                        padding: '4px 12px',
                        borderRadius: '12px',
                        backgroundColor: getStatusColor(session.status),
                        color: 'white',
                        fontWeight: 'normal'
                      }}
                    >
                      {session.status.toUpperCase().replace('_', ' ')}
                    </span>
                  </h3>
                  
                  <div style={{ color: '#666', marginBottom: '15px' }}>
                    <p style={{ margin: '5px 0' }}>
                      <strong>Scheduled:</strong> {fmtDateTime(session.scheduled_date)}
                    </p>
                    {session.therapy_name && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>Protocol:</strong> {session.therapy_name}
                      </p>
                    )}
                    {session.facility_name && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>Facility:</strong> {session.facility_name}
                      </p>
                    )}
                    {session.attending_physician && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>Physician:</strong> {session.attending_physician}
                      </p>
                    )}
                    {session.pre_dialysis_weight_kg && session.post_dialysis_weight_kg && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>Weight:</strong> {session.pre_dialysis_weight_kg}kg → {session.post_dialysis_weight_kg}kg 
                        {session.fluid_removed_ml && ` (${session.fluid_removed_ml}mL removed)`}
                      </p>
                    )}
                    {session.drugs_administered && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>Drugs:</strong> {session.drugs_administered}
                        {session.dosage && ` - ${session.dosage}`}
                      </p>
                    )}
                    {(session.pre_systolic_bp && session.pre_diastolic_bp) && (
                      <p style={{ margin: '5px 0' }}>
                        <strong>BP:</strong> Pre: {session.pre_systolic_bp}/{session.pre_diastolic_bp}
                        {(session.post_systolic_bp && session.post_diastolic_bp) && 
                          ` → Post: ${session.post_systolic_bp}/${session.post_diastolic_bp}`}
                      </p>
                    )}
                    {session.patient_notes && (
                      <p style={{ margin: '10px 0', padding: '10px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                        <strong>Notes:</strong> {session.patient_notes}
                      </p>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '10px', marginLeft: '20px' }}>
                  <button
                    onClick={() => handleEdit(session)}
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
                    onClick={() => handleDelete(session.id)}
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

export default TherapySessions;
