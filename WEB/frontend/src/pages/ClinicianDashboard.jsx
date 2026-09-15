import { useState, useEffect } from 'react';
import api from '../services/api';
import {
  Users, Activity, Pill, FlaskConical, Apple, Dumbbell, Brain, Heart,
  Eye, Stethoscope,
} from 'lucide-react';
import Avatar from '../components/Avatar';
import BackButton from '../components/BackButton';
import { useClinicianMode } from '../context/ClinicianModeContext';
import PatientBoard from './clinician/PatientBoard';
import CategoryDetail from './clinician/CategoryDetail';
import { t as translate } from '../i18n';

const categoryIcons = {
  vitals: Activity, medications: Pill, labs: FlaskConical,
  nutrition: Apple, fitness: Dumbbell, mood: Brain, lifestyle: Heart,
  all: Eye,
};


export default function ClinicianDashboard() {
  const { canBeClinician, clinicianMode, enterClinicianMode } = useClinicianMode();
  const [patients, setPatients] = useState([]);
  const [role, setRole] = useState(null);
  const [selected, setSelected] = useState(null);      // patient opened from the grid
  const [category, setCategory] = useState(null);      // category opened from the board
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Reaching this page by link or bookmark should put the app in clinician
  // mode too — otherwise the patient nav stays up around a clinical screen.
  useEffect(() => {
    if (canBeClinician && !clinicianMode) enterClinicianMode();
  }, [canBeClinician, clinicianMode, enterClinicianMode]);

  useEffect(() => { loadPatients(); }, []);

  async function loadPatients() {
    try {
      const { data } = await api.get('/clinician-dashboard/');
      setPatients(data.patients || []);
      setRole(data.role || null);
    } catch (err) {
      setError(err.response?.status === 403
        ? translate('ClinicianDashboard.access_denied_this_view_is_available_to')
        : translate('ClinicianDashboard.could_not_load_your_patients'));
    } finally {
      setLoading(false);
    }
  }


  if (loading) return <div className="loading">{translate('ClinicianDashboard.loading')}</div>;

  if (error) return (
    <div>
      <div className="page-header"><h1 className="page-title">{translate('ClinicianDashboard.my_patients')}</h1></div>
      <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-danger)' }}>
        {error}
      </div>
    </div>
  );

  if (selected && category) {
    return (
      <CategoryDetail
        patientId={selected.user_id}
        categoryKey={category}
        onBack={() => setCategory(null)}
      />
    );
  }

  if (selected) {
    return (
      <PatientBoard
        patientId={selected.user_id}
        onBack={() => setSelected(null)}
        onOpenCategory={setCategory}
      />
    );
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">{translate('ClinicianDashboard.my_patients')}</h1>
        </div>
        <span style={{ color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', gap: 8 }}>
          {role && (
            <span style={{ textTransform: 'capitalize', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Stethoscope size={15} /> {role.replace(/_/g, ' ')}
            </span>
          )}
          {(patients.length !== 1) ? translate('ClinicianDashboard.patients', { patients: patients.length }) : translate('ClinicianDashboard.patient', { patients: patients.length })}
        </span>
      </div>

      {patients.length === 0 ? (
        <div className="card" style={{ padding: '3rem 2rem', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
          <Users size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
          <h3>{translate('ClinicianDashboard.no_patients_yet')}</h3>
          <p>{translate('ClinicianDashboard.patients_appear_here_as_soon_as_they')}</p>
          <p style={{ fontSize: '0.85rem', marginTop: '0.75rem' }}>
            {translate('ClinicianDashboard.they_do_that_from')} <strong>{translate('ClinicianDashboard.share_records')}</strong>{translate('ClinicianDashboard.using_your_account_email')}
          </p>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: '1rem',
        }}>
          {patients.map(p => (
            <PatientCard key={p.user_id} patient={p} onOpen={() => { setSelected(p); setCategory(null); }} />
          ))}
        </div>
      )}
    </div>
  );
}

function PatientCard({ patient: p, onOpen }) {
  const vitals = p.latest_vitals || null;
  const abnormalLabs = (p.latest_labs || []).filter(l => l.is_abnormal).length;

  return (
    <button
      onClick={onOpen}
      className="card"
      style={{
        padding: '1.25rem', textAlign: 'left', cursor: 'pointer', width: '100%',
        border: '1px solid var(--color-border)', background: 'var(--color-surface, #fff)',
        display: 'flex', flexDirection: 'column', gap: '0.9rem', font: 'inherit',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
        <Avatar src={p.profile_picture_url} name={p.full_name} id={p.user_id} size={44} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {p.full_name || `Patient #${p.user_id}`}
          </div>
          {p.email && (
            <div style={{
              fontSize: '0.8rem', color: 'var(--color-text-secondary)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {p.email}
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: '1.25rem', fontSize: '0.85rem' }}>
        <Metric label="BP" value={vitals?.bp} />
        <Metric label="HR" value={vitals?.hr ? `${vitals.hr}` : null} />
        <Metric label={translate('ClinicianDashboard.weight')} value={vitals?.weight_kg ? `${vitals.weight_kg} kg` : null} />
      </div>

      <div style={{ display: 'flex', gap: '1rem', fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
        <span>{translate('ClinicianDashboard.labs', { latest_labs: (p.latest_labs || []).length })}</span>
        <span>{translate('ClinicianDashboard.meds', { medications: (p.medications || []).length })}</span>
        {abnormalLabs > 0 && (
          <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>
            {translate('ClinicianDashboard.abnormal', { abnormalLabs })}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
        {(p.permissions || []).map(t => {
          const Icon = categoryIcons[t] || Eye;
          return (
            <span key={t} style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '2px 8px', borderRadius: 6, fontSize: 11,
              background: 'var(--color-primary-light)', color: 'var(--color-primary-dark)',
            }}>
              <Icon size={12} /> {t}
            </span>
          );
        })}
      </div>
    </button>
  );
}

function Metric({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: '0.7rem', color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
        {label}
      </div>
      <div style={{ fontWeight: 600 }}>{value || '—'}</div>
    </div>
  );
}
