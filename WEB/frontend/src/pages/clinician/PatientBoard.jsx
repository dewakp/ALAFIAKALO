import { useEffect, useState } from 'react';
import api from '../../services/api';
import {
  ArrowLeft, Gauge, HeartPulse, FlaskConical, Pill, Activity, Apple,
  Dumbbell, Droplets, Brain, BookOpen, Link2, ChevronRight, Lock,
  Thermometer, Cross, Heart,
} from 'lucide-react';

// Icon per category key. The backend sends an icon name so every client can
// agree on the board's shape; each client maps it to its own icon set.
const ICONS = {
  gauge: Gauge, 'heart-pulse': HeartPulse, flask: FlaskConical, pill: Pill,
  activity: Activity, apple: Apple, dumbbell: Dumbbell, droplets: Droplets,
  brain: Brain, book: BookOpen, link: Link2,
  thermometer: Thermometer, cross: Cross, heart: Heart,
};

const ACCENTS = {
  score: 'var(--color-primary)', vitals: '#e11d48', labs: '#7c3aed',
  medications: '#ea580c', conditions: '#dc2626', nutrition: '#16a34a',
  fitness: '#0891b2', elimination: '#a16207', mood: '#db2777',
  journal: '#4f46e5', connected_records: '#0284c7',
  symptoms: '#f59e0b', dialysis: '#0d9488', lifestyle: '#65a30d',
};

export default function PatientBoard({ patientId, onBack, onOpenCategory }) {
  const [board, setBoard] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setBoard(null);
    setError(null);
    api.get(`/clinician-dashboard/patient/${patientId}/board`)
      .then(({ data }) => { if (!cancelled) setBoard(data); })
      .catch((err) => {
        if (cancelled) return;
        setError(err.response?.status === 403
          ? 'This patient has revoked access.'
          : 'Could not load this patient.');
      });
    return () => { cancelled = true; };
  }, [patientId]);

  if (error) {
    return (
      <div>
        <Header onBack={onBack} title="Patient" />
        <div className="card" style={{ padding: '2rem', color: 'var(--color-danger)' }}>{error}</div>
      </div>
    );
  }
  if (!board) return <div className="loading">Loading patient…</div>;

  const sharesAll = board.permissions.includes('all');

  return (
    <div>
      <Header
        onBack={onBack}
        title={board.patient.full_name || `Patient #${board.patient.user_id}`}
        right={board.patient.email}
      />

      <div style={{
        marginBottom: '1rem', fontSize: '0.85rem', color: 'var(--color-text-secondary)',
        display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap',
      }}>
        <Lock size={13} />
        {sharesAll
          ? 'This patient shares all of their data with you.'
          : `Shared with you: ${board.permissions.join(', ')}`}
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
        gap: '1rem',
      }}>
        {board.cards.map(card => (
          <CategoryCard
            key={card.key}
            card={card}
            onOpen={() => card.shared && onOpenCategory(card.key)}
          />
        ))}
      </div>
    </div>
  );
}

function Header({ onBack, title, right }) {
  return (
    <div className="page-header">
      <div className="page-header-left">
        <button className="btn btn-secondary btn-sm" onClick={onBack}>
          <ArrowLeft size={16} /> All patients
        </button>
        <h1 className="page-title">{title}</h1>
      </div>
      {right && <span style={{ color: 'var(--color-text-secondary)' }}>{right}</span>}
    </div>
  );
}

function CategoryCard({ card, onOpen }) {
  const Icon = ICONS[card.icon] || Activity;
  const accent = ACCENTS[card.key] || 'var(--color-primary)';
  const hasData = card.items.length > 0;

  return (
    <button
      onClick={onOpen}
      disabled={!card.shared}
      className="card"
      style={{
        padding: '1.1rem', textAlign: 'left', width: '100%', font: 'inherit',
        border: '1px solid var(--color-border)',
        background: 'var(--color-surface)',
        cursor: card.shared ? 'pointer' : 'default',
        opacity: card.shared ? 1 : 0.55,
        display: 'flex', flexDirection: 'column', gap: '0.75rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Icon size={17} style={{ color: accent }} />
        <strong style={{ flex: 1 }}>{card.label}</strong>
        {card.count != null && (
          <span style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
            {card.count}
          </span>
        )}
        {card.shared ? <ChevronRight size={15} style={{ color: 'var(--color-text-secondary)' }} />
                     : <Lock size={13} style={{ color: 'var(--color-text-secondary)' }} />}
      </div>

      {hasData ? (
        <div style={{ minWidth: 0, overflow: 'hidden' }}>
          {card.items.slice(0, 5).map((item, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', gap: '1rem',
              fontSize: '0.85rem', marginBottom: '0.25rem',
              color: item.danger ? 'var(--color-danger)' : 'inherit',
            }}>
              <span style={{
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                minWidth: 0, flexShrink: 1,
              }}>
                {item.label}{item.danger ? ' ⚠' : ''}
              </span>
              {item.value != null && (
                <strong style={{
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  minWidth: 0, maxWidth: '65%',
                }}>
                  {item.value}{item.unit ? ` ${item.unit}` : ''}
                </strong>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)' }}>
          {/* "Not shared" and "nothing recorded" are different facts and the
              card says which — collapsing them reads as an empty record. */}
          {card.empty_reason || 'Nothing recorded.'}
        </div>
      )}

      {card.last_updated && (
        <div style={{ fontSize: '0.72rem', color: 'var(--color-text-secondary)', marginTop: 'auto' }}>
          Updated {String(card.last_updated).slice(0, 10)}
        </div>
      )}
    </button>
  );
}
