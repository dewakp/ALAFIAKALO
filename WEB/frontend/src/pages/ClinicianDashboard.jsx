import { useState, useEffect } from 'react';
import api from '../services/api';
import {
  Users, Activity, Pill, FlaskConical, Apple, Dumbbell, Brain, Heart,
  Eye, Stethoscope,
} from 'lucide-react';
import BackButton from '../components/BackButton';
import { useClinicianMode } from '../context/ClinicianModeContext';
import PatientBoard from './clinician/PatientBoard';
import CategoryDetail from './clinician/CategoryDetail';

const categoryIcons = {
  vitals: Activity, medications: Pill, labs: FlaskConical,
  nutrition: Apple, fitness: Dumbbell, mood: Brain, lifestyle: Heart,
  all: Eye,
};

// Deterministic avatar tint per patient, so a card keeps the same colour
// between loads and the grid stays scannable.
const AVATAR_TINTS = ['#0ea5e9', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#6366f1'];
const tintFor = (id) => AVATAR_TINTS[Math.abs(Number(id) || 0) % AVATAR_TINTS.length];

const initials = (name) => (name || '?')
  .split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?';

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
        ? 'Access denied. This view is available to clinicians and social workers only.'
        : 'Could not load your patients.');
    } finally {
      setLoading(false);
    }
  }


  if (loading) return <div className="loading">Loading...</div>;

  if (error) return (
    <div>
      <div className="page-header"><h1 className="page-title">My Patients</h1></div>
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
          <h1 className="page-title">My Patients</h1>
        </div>
        <span style={{ color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', gap: 8 }}>
          {role && (
            <span style={{ textTransform: 'capitalize', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Stethoscope size={15} /> {role.replace(/_/g, ' ')}
            </span>
          )}
          · {patients.length} patient{patients.length !== 1 ? 's' : ''}
        </span>
      </div>

      {patients.length === 0 ? (
        <div className="card" style={{ padding: '3rem 2rem', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
          <Users size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
          <h3>No patients yet</h3>
          <p>Patients appear here as soon as they share their records with you.</p>
          <p style={{ fontSize: '0.85rem', marginTop: '0.75rem' }}>
            They do that from <strong>Share Records</strong>, using your account email.
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
        <div style={{
          width: 44, height: 44, borderRadius: '50%', flexShrink: 0,
          background: tintFor(p.user_id), color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontWeight: 700, fontSize: '0.95rem',
        }}>
          {initials(p.full_name)}
        </div>
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
        <Metric label="Weight" value={vitals?.weight_kg ? `${vitals.weight_kg} kg` : null} />
      </div>

      <div style={{ display: 'flex', gap: '1rem', fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
        <span>{(p.latest_labs || []).length} labs</span>
        <span>{(p.medications || []).length} meds</span>
        {abnormalLabs > 0 && (
          <span style={{ color: 'var(--color-danger)', fontWeight: 600 }}>
            ⚠ {abnormalLabs} abnormal
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
