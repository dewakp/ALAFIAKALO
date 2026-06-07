import { useState, useEffect } from 'react';
import api from '../services/api';
import { Users, Eye, ChevronDown, ChevronUp, Activity, Pill, FlaskConical, Apple, Dumbbell, Brain, Heart } from 'lucide-react';
import BackButton from '../components/BackButton';

const categoryIcons = {
  vitals: Activity, medications: Pill, labs: FlaskConical,
  nutrition: Apple, fitness: Dumbbell, mood: Brain, lifestyle: Heart,
};

export default function ClinicianDashboard() {
  const [patients, setPatients] = useState([]);
  const [expanded, setExpanded] = useState(null);
  const [patientDetail, setPatientDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => { loadPatients(); }, []);

  async function loadPatients() {
    try {
      const { data } = await api.get('/clinician-dashboard/');
      setPatients(data.patients || []);
    } catch (err) {
      if (err.response?.status === 403) {
        setError('Access denied. This page is available to clinicians and social workers only.');
      } else {
        setError('Error loading dashboard');
      }
    } finally {
      setLoading(false);
    }
  }

  async function loadPatientDetail(patientId) {
    if (expanded === patientId) {
      setExpanded(null);
      setPatientDetail(null);
      return;
    }
    try {
      const { data } = await api.get(`/clinician-dashboard/patient/${patientId}`);
      setPatientDetail(data);
      setExpanded(patientId);
    } catch (err) {
      alert('Error loading patient details');
    }
  }

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return (
    <div>
      <div className="page-header"><h1 className="page-title">Clinician Dashboard</h1></div>
      <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-danger)' }}>{error}</div>
    </div>
  );

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Clinician Dashboard</h1>
        </div>
        <span style={{ color: 'var(--color-text-secondary)' }}>{patients.length} patient{patients.length !== 1 ? 's' : ''}</span>
      </div>

      {patients.length === 0 ? (
        <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
          <Users size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
          <h3>No Patients Yet</h3>
          <p>Patients who share their data with you will appear here.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {patients.map(p => (
            <div key={p.patient_id} className="card" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                onClick={() => loadPatientDetail(p.patient_id)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: '50%', background: 'var(--color-primary-light)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700,
                    color: 'var(--color-primary-dark)',
                  }}>
                    {(p.display_name || 'U')[0].toUpperCase()}
                  </div>
                  <div>
                    <strong>{p.display_name || `Patient #${p.patient_id}`}</strong>
                    <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                      {p.shared_data_types?.map(t => {
                        const Icon = categoryIcons[t] || Eye;
                        return <span key={t} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Icon size={14} /> {t}</span>;
                      })}
                    </div>
                  </div>
                </div>
                {expanded === p.patient_id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>

              {expanded === p.patient_id && patientDetail && (
                <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                  <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                    {patientDetail.recent_labs?.length > 0 && (
                      <StatCard title="Recent Labs" color="var(--color-info)">
                        {patientDetail.recent_labs.slice(0, 5).map((l, i) => (
                          <div key={i} style={{ fontSize: '0.85rem', marginBottom: '0.25rem' }}>
                            <strong>{l.test_name}:</strong> {l.value} {l.unit}
                            {l.is_abnormal && <span style={{ color: 'var(--color-danger)', marginLeft: '0.25rem' }}>⚠</span>}
                          </div>
                        ))}
                      </StatCard>
                    )}
                    {patientDetail.recent_vitals && (
                      <StatCard title="Latest Vitals" color="var(--color-primary)">
                        <div style={{ fontSize: '0.85rem' }}>
                          {patientDetail.recent_vitals.blood_pressure_systolic && (
                            <div>BP: {patientDetail.recent_vitals.blood_pressure_systolic}/{patientDetail.recent_vitals.blood_pressure_diastolic}</div>
                          )}
                          {patientDetail.recent_vitals.heart_rate_bpm && <div>HR: {patientDetail.recent_vitals.heart_rate_bpm} bpm</div>}
                          {patientDetail.recent_vitals.weight_kg && <div>Weight: {patientDetail.recent_vitals.weight_kg} kg</div>}
                        </div>
                      </StatCard>
                    )}
                    {patientDetail.active_medications?.length > 0 && (
                      <StatCard title="Active Medications" color="var(--color-warning)">
                        {patientDetail.active_medications.slice(0, 5).map((m, i) => (
                          <div key={i} style={{ fontSize: '0.85rem', marginBottom: '0.25rem' }}>
                            {m.name} — {m.dosage} {m.dosage_unit} ({m.frequency})
                          </div>
                        ))}
                      </StatCard>
                    )}
                    {patientDetail.wellness_score && (
                      <StatCard title="Wellness Score" color="var(--color-primary)">
                        <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--color-primary)' }}>
                          {patientDetail.wellness_score.overall_score}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                          as of {patientDetail.wellness_score.score_date}
                        </div>
                      </StatCard>
                    )}
                  </div>
                  {patientDetail.recent_mood && (
                    <div style={{ marginTop: '1rem', fontSize: '0.9rem' }}>
                      <strong>Latest Mood:</strong> Score {patientDetail.recent_mood.mood_score}/10
                      {patientDetail.recent_mood.energy_level && ` · Energy ${patientDetail.recent_mood.energy_level}/10`}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatCard({ title, color, children }) {
  return (
    <div className="card" style={{ padding: '1rem', background: 'var(--color-bg)' }}>
      <h4 style={{ marginBottom: '0.5rem', color, fontSize: '0.9rem' }}>{title}</h4>
      {children}
    </div>
  );
}
