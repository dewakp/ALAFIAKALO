import { useState, useEffect } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import api from '../services/api';
import {
  Dumbbell,
  Plus,
  ChevronDown,
  ChevronUp,
  Lightbulb,
  Loader2,
  Trash2,
  Calendar,
  Clock,
  Timer,
  Activity,
  RefreshCw,
  Moon,
  Check,
} from 'lucide-react';
import BackButton from '../components/BackButton';

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const DAY_LABELS = { monday: 'Mon', tuesday: 'Tue', wednesday: 'Wed', thursday: 'Thu', friday: 'Fri', saturday: 'Sat', sunday: 'Sun' };
const FITNESS_OPTIONS = [
  { value: 'beginner', label: 'Beginner' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'advanced', label: 'Advanced' },
];

const levelColor = (level) => {
  const map = {
    beginner: 'var(--color-primary)',
    moderate: 'var(--color-warning)',
    advanced: 'var(--color-danger)',
  };
  return map[level] || 'var(--color-primary)';
};

function ExerciseCard({ exercise }) {
  return (
    <div className="card" style={{ padding: '0.75rem', marginBottom: '0.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
        <div style={{ flex: 1 }}>
          <h5 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600 }}>{exercise.name}</h5>
          {exercise.description && (
            <p style={{ margin: '0.25rem 0 0', fontSize: '0.8rem', color: '#6b7280', lineHeight: 1.5 }}>{exercise.description}</p>
          )}
        </div>
        <span
          style={{
            fontSize: '0.8rem',
            fontWeight: 600,
            color: 'var(--color-info)',
            whiteSpace: 'nowrap',
            display: 'flex',
            alignItems: 'center',
            gap: 3,
          }}
        >
          <Clock size={13} />
          {exercise.duration_minutes} min
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.5rem', alignItems: 'center' }}>
        {exercise.sets != null && exercise.reps != null && (
          <span style={{ fontSize: '0.75rem', color: '#374151', fontWeight: 500 }}>
            {exercise.sets} × {exercise.reps}
          </span>
        )}
        {exercise.sets != null && exercise.reps == null && (
          <span style={{ fontSize: '0.75rem', color: '#374151', fontWeight: 500 }}>
            {exercise.sets} sets
          </span>
        )}
        {exercise.muscle_groups && exercise.muscle_groups.length > 0 && (
          exercise.muscle_groups.map((mg, i) => (
            <span
              key={i}
              style={{
                padding: '0.1rem 0.45rem',
                borderRadius: '999px',
                fontSize: '0.65rem',
                fontWeight: 500,
                background: '#ede9fe',
                color: '#7c3aed',
                textTransform: 'capitalize',
              }}
            >
              {mg}
            </span>
          ))
        )}
      </div>
    </div>
  );
}

function DayExercises({ exercises }) {
  if (!exercises || exercises.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '2.5rem 1rem', color: '#9ca3af' }}>
        <Moon size={32} style={{ marginBottom: '0.5rem', opacity: 0.5 }} />
        <p style={{ margin: 0, fontSize: '0.9rem', fontWeight: 500 }}>Rest Day</p>
        <p style={{ margin: '0.25rem 0 0', fontSize: '0.8rem' }}>Recovery is part of the plan.</p>
      </div>
    );
  }

  const totalMinutes = exercises.reduce((sum, ex) => sum + (ex.duration_minutes || 0), 0);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.5rem' }}>
        <span style={{ fontSize: '0.8rem', color: '#6b7280', display: 'flex', alignItems: 'center', gap: 4 }}>
          <Timer size={13} /> {totalMinutes} min total
        </span>
      </div>
      {exercises.map((exercise, i) => (
        <ExerciseCard key={i} exercise={exercise} />
      ))}
    </div>
  );
}

function PlanViewer({ plan }) {
  const [activeDay, setActiveDay] = useState('monday');
  if (!plan) return null;

  const planData = plan.plan_data || {};

  const dayMinutes = (day) => {
    const exercises = planData[day];
    if (!exercises || !Array.isArray(exercises)) return 0;
    return exercises.reduce((sum, ex) => sum + (ex.duration_minutes || 0), 0);
  };

  const totalWeeklyMinutes = DAYS.reduce((sum, day) => sum + dayMinutes(day), 0);
  const activeDays = DAYS.filter((day) => {
    const ex = planData[day];
    return ex && Array.isArray(ex) && ex.length > 0;
  }).length;

  return (
    <div>
      {/* Weekly summary stats */}
      <div className="stats-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
        <div className="card" style={{ padding: '0.75rem', textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-primary)' }}>{totalWeeklyMinutes}</div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Weekly Minutes</div>
        </div>
        <div className="card" style={{ padding: '0.75rem', textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-info)' }}>{activeDays}</div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Active Days</div>
        </div>
        <div className="card" style={{ padding: '0.75rem', textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#6b7280' }}>{7 - activeDays}</div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Rest Days</div>
        </div>
        {plan.weekly_minutes_target && (
          <div className="card" style={{ padding: '0.75rem', textAlign: 'center' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: totalWeeklyMinutes >= plan.weekly_minutes_target ? 'var(--color-primary)' : 'var(--color-warning)' }}>
              {Math.round((totalWeeklyMinutes / plan.weekly_minutes_target) * 100)}%
            </div>
            <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Goal Met</div>
          </div>
        )}
      </div>

      {/* Day tabs */}
      <div style={{ display: 'flex', gap: '0.25rem', overflowX: 'auto', marginBottom: '1rem', borderBottom: '2px solid #e5e7eb', paddingBottom: 0 }}>
        {DAYS.map((day) => {
          const mins = dayMinutes(day);
          const isRest = mins === 0;
          return (
            <button
              key={day}
              onClick={() => setActiveDay(day)}
              style={{
                padding: '0.5rem 1rem',
                border: 'none',
                borderBottom: activeDay === day ? '2px solid var(--color-primary)' : '2px solid transparent',
                background: 'none',
                cursor: 'pointer',
                fontWeight: activeDay === day ? 600 : 400,
                color: activeDay === day ? 'var(--color-primary)' : isRest ? '#d1d5db' : '#6b7280',
                fontSize: '0.85rem',
                marginBottom: '-2px',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s',
              }}
            >
              {DAY_LABELS[day]}
              <span style={{ display: 'block', fontSize: '0.7rem', fontWeight: 400 }}>
                {isRest ? 'Rest' : `${mins} min`}
              </span>
            </button>
          );
        })}
      </div>

      <DayExercises exercises={planData[activeDay]} />

      {plan.advice && (
        <div className="card" style={{ padding: '1rem', marginTop: '1rem', borderLeft: '3px solid var(--color-info)' }}>
          <h4 style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
            <Lightbulb size={16} color="var(--color-warning)" /> Trainer Advice
          </h4>
          <p style={{ margin: 0, fontSize: '0.85rem', color: '#374151', lineHeight: 1.6 }}>{plan.advice}</p>
        </div>
      )}
    </div>
  );
}

function SavedPlanCard({ plan, onDelete }) {
  const [expanded, setExpanded] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async (e) => {
    e.stopPropagation();
    if (!window.confirm('Delete this exercise plan?')) return;
    setDeleting(true);
    try {
      await api.delete(`/planners/exercise-plans/${plan.id}`);
      onDelete(plan.id);
    } catch {
      /* ignore */
    } finally {
      setDeleting(false);
    }
  };

  const totalMinutes = plan.plan_data
    ? DAYS.reduce((sum, day) => {
        const ex = plan.plan_data[day];
        if (!ex || !Array.isArray(ex)) return sum;
        return sum + ex.reduce((s, e) => s + (e.duration_minutes || 0), 0);
      }, 0)
    : null;

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          padding: '1rem 1.25rem',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '0.75rem',
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <h4 style={{ margin: 0, fontSize: '0.95rem' }}>{plan.plan_name || 'Exercise Plan'}</h4>
            <span
              style={{
                padding: '0.15rem 0.5rem',
                borderRadius: '999px',
                fontSize: '0.7rem',
                fontWeight: 500,
                background: levelColor(plan.fitness_level),
                color: '#fff',
                textTransform: 'capitalize',
              }}
            >
              {plan.fitness_level}
            </span>
          </div>
          <div style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <Calendar size={13} /> {plan.start_date} — {plan.end_date}
            </span>
            {totalMinutes != null && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Timer size={13} /> {totalMinutes} min/week
              </span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button className="btn btn-sm" onClick={handleDelete} disabled={deleting} title="Delete plan" style={{ color: 'var(--color-danger)', padding: '0.3rem' }}>
            {deleting ? <Loader2 size={15} className="spin" /> : <Trash2 size={15} />}
          </button>
          {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </div>
      </div>
      {expanded && (
        <div style={{ padding: '0 1.25rem 1.25rem', borderTop: '1px solid #e5e7eb' }}>
          <div style={{ paddingTop: '1rem' }}>
            <PlanViewer plan={plan} />
          </div>
        </div>
      )}
    </div>
  );
}

export default function ExercisePlanner() {
  const [form, setForm] = useState({
    fitness_level: 'beginner',
    weekly_minutes_target: 150,
    limitations: '',
  });
  const [generating, setGenerating] = useState(false);
  const [generatedPlan, setGeneratedPlan] = useState(null);
  const [savedPlans, setSavedPlans] = useState([]);
  const [loadingPlans, setLoadingPlans] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchSavedPlans();
  }, []);

  const fetchSavedPlans = async () => {
    setLoadingPlans(true);
    try {
      const { data } = await api.get('/planners/exercise-plans');
      setSavedPlans(Array.isArray(data) ? data : []);
    } catch {
      /* ignore */
    } finally {
      setLoadingPlans(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: name === 'weekly_minutes_target' ? Number(value) : value }));
  };

  const handleGenerate = async (e) => {
    e.preventDefault();
    setGenerating(true);
    setError('');
    setGeneratedPlan(null);
    try {
      const { data } = await api.post('/planners/exercise-plan', {
        fitness_level: form.fitness_level,
        weekly_minutes_target: form.weekly_minutes_target,
        limitations: form.limitations || undefined,
      });
      setGeneratedPlan(data);
      fetchSavedPlans();
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to generate exercise plan. Please try again.'));
    } finally {
      setGenerating(false);
    }
  };

  const handleDeletePlan = (id) => {
    setSavedPlans((prev) => prev.filter((p) => p.id !== id));
  };

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', padding: '1.5rem 1rem' }}>
      {/* Header */}
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Dumbbell size={28} color="var(--color-primary)" />
            AI Exercise Planner
          </h1>
        </div>
        <p style={{ margin: '0.25rem 0 0', color: '#6b7280', fontSize: '0.9rem' }}>
          Generate personalized weekly exercise plans matched to your fitness level.
        </p>
      </div>

      {/* Generate form */}
      <div className="card" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
        <h3 style={{ margin: '0 0 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem' }}>
          <Plus size={18} /> Generate New Plan
        </h3>
        <form onSubmit={handleGenerate}>
          <div className="card-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            <div className="form-group">
              <label className="form-label" htmlFor="fitness_level">Fitness Level</label>
              <select
                id="fitness_level"
                name="fitness_level"
                className="form-select"
                value={form.fitness_level}
                onChange={handleChange}
              >
                {FITNESS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="weekly_minutes_target">Weekly Minutes Target</label>
              <input
                id="weekly_minutes_target"
                name="weekly_minutes_target"
                type="number"
                className="form-input"
                value={form.weekly_minutes_target}
                onChange={handleChange}
                min={30}
                max={600}
                step={10}
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="limitations">Physical Limitations</label>
              <input
                id="limitations"
                name="limitations"
                type="text"
                className="form-input"
                placeholder="e.g. knee injury, lower back pain"
                value={form.limitations}
                onChange={handleChange}
              />
            </div>
          </div>

          {error && (
            <div style={{ marginTop: '0.75rem', padding: '0.65rem 1rem', borderRadius: '0.375rem', background: '#fef2f2', color: 'var(--color-danger)', fontSize: '0.85rem' }}>
              {error}
            </div>
          )}

          <div style={{ marginTop: '1.25rem' }}>
            <button type="submit" className="btn btn-primary" disabled={generating} style={{ minWidth: 180 }}>
              {generating ? (
                <>
                  <Loader2 size={16} className="spin" style={{ marginRight: 6 }} />
                  Generating…
                </>
              ) : (
                <>
                  <Dumbbell size={16} style={{ marginRight: 6 }} />
                  Generate Exercise Plan
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Generated plan display */}
      {generatedPlan && (
        <div className="card" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '1rem' }}>{generatedPlan.plan_name || 'Your Exercise Plan'}</h3>
              <div style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                <span
                  style={{
                    padding: '0.15rem 0.5rem',
                    borderRadius: '999px',
                    fontSize: '0.7rem',
                    fontWeight: 500,
                    background: levelColor(generatedPlan.fitness_level),
                    color: '#fff',
                    textTransform: 'capitalize',
                  }}
                >
                  {generatedPlan.fitness_level}
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                  <Calendar size={13} /> {generatedPlan.start_date} — {generatedPlan.end_date}
                </span>
                {generatedPlan.weekly_minutes_target && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                    <Activity size={13} /> Target: {generatedPlan.weekly_minutes_target} min/week
                  </span>
                )}
              </div>
            </div>
          </div>
          <PlanViewer plan={generatedPlan} />
        </div>
      )}

      {/* Saved plans */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem' }}>
            <Calendar size={18} /> Saved Plans
          </h3>
          <button className="btn btn-secondary btn-sm" onClick={fetchSavedPlans} disabled={loadingPlans}>
            <RefreshCw size={14} style={{ marginRight: 4 }} /> Refresh
          </button>
        </div>

        {loadingPlans ? (
          <div style={{ textAlign: 'center', padding: '2rem 0', color: '#9ca3af' }}>
            <Loader2 size={24} className="spin" />
            <p style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>Loading saved plans…</p>
          </div>
        ) : savedPlans.length === 0 ? (
          <div className="card" style={{ padding: '2rem', textAlign: 'center', color: '#9ca3af' }}>
            <Dumbbell size={36} style={{ marginBottom: '0.5rem', opacity: 0.4 }} />
            <p style={{ margin: 0, fontSize: '0.9rem' }}>No saved exercise plans yet. Generate your first plan above!</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {savedPlans.map((plan) => (
              <SavedPlanCard key={plan.id} plan={plan} onDelete={handleDeletePlan} />
            ))}
          </div>
        )}
      </div>

      {/* Spinner animation */}
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        .spin { animation: spin 1s linear infinite; }
      `}</style>
    </div>
  );
}
