import { useState, useEffect } from 'react';
import api from '../services/api';
import {
  UtensilsCrossed,
  Plus,
  ChevronDown,
  ChevronUp,
  ShoppingCart,
  Lightbulb,
  Loader2,
  Trash2,
  Calendar,
  Flame,
  Beef,
  Wheat,
  Droplets,
  Check,
  RefreshCw,
} from 'lucide-react';
import BackButton from '../components/BackButton';

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const DAY_LABELS = { monday: 'Mon', tuesday: 'Tue', wednesday: 'Wed', thursday: 'Thu', friday: 'Fri', saturday: 'Sat', sunday: 'Sun' };
const MEAL_TYPES = ['breakfast', 'lunch', 'dinner', 'snacks'];
const DIETARY_OPTIONS = [
  { value: 'balanced', label: 'Balanced' },
  { value: 'renal', label: 'Renal' },
  { value: 'low_sodium', label: 'Low Sodium' },
  { value: 'diabetic', label: 'Diabetic' },
  { value: 'heart_healthy', label: 'Heart Healthy' },
];

const dietaryColor = (pattern) => {
  const map = {
    balanced: '--color-primary',
    renal: '--color-info',
    low_sodium: '--color-warning',
    diabetic: '--color-danger',
    heart_healthy: '--color-primary',
  };
  return `var(${map[pattern] || '--color-primary'})`;
};

function MealCard({ meal }) {
  return (
    <div className="card" style={{ padding: '0.75rem', marginBottom: '0.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
        <div style={{ flex: 1 }}>
          <h5 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600 }}>{meal.name}</h5>
          {meal.description && (
            <p style={{ margin: '0.25rem 0 0', fontSize: '0.8rem', color: '#6b7280' }}>{meal.description}</p>
          )}
        </div>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-primary)', whiteSpace: 'nowrap' }}>
          <Flame size={13} style={{ verticalAlign: '-2px', marginRight: 2 }} />
          {meal.calories} cal
        </span>
      </div>
      <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem', fontSize: '0.75rem', color: '#6b7280' }}>
        <span title="Protein"><Beef size={12} style={{ verticalAlign: '-2px', marginRight: 2 }} />{meal.protein_g}g P</span>
        <span title="Carbs"><Wheat size={12} style={{ verticalAlign: '-2px', marginRight: 2 }} />{meal.carbs_g}g C</span>
        <span title="Fat"><Droplets size={12} style={{ verticalAlign: '-2px', marginRight: 2 }} />{meal.fat_g}g F</span>
      </div>
    </div>
  );
}

function DayPlan({ dayData }) {
  if (!dayData) return <p style={{ color: '#9ca3af', textAlign: 'center', padding: '2rem 0' }}>No meals planned for this day.</p>;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
      {MEAL_TYPES.map((type) => {
        const meals = dayData[type];
        if (!meals || meals.length === 0) return null;
        return (
          <div key={type}>
            <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.85rem', textTransform: 'capitalize', color: '#374151', letterSpacing: '0.03em' }}>
              {type}
            </h4>
            {meals.map((meal, i) => (
              <MealCard key={i} meal={meal} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

function ShoppingList({ items }) {
  const [checked, setChecked] = useState({});
  if (!items || items.length === 0) return null;

  const toggle = (idx) => setChecked((prev) => ({ ...prev, [idx]: !prev[idx] }));
  const checkedCount = Object.values(checked).filter(Boolean).length;

  return (
    <div className="card" style={{ padding: '1.25rem', marginTop: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
        <h4 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <ShoppingCart size={18} /> Shopping List
        </h4>
        <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>{checkedCount}/{items.length} items</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.25rem' }}>
        {items.map((item, i) => (
          <label
            key={i}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.35rem 0.5rem',
              borderRadius: '0.375rem',
              cursor: 'pointer',
              fontSize: '0.85rem',
              textDecoration: checked[i] ? 'line-through' : 'none',
              color: checked[i] ? '#9ca3af' : '#374151',
              background: checked[i] ? '#f9fafb' : 'transparent',
              transition: 'all 0.15s',
            }}
          >
            <span
              onClick={() => toggle(i)}
              style={{
                width: 18,
                height: 18,
                borderRadius: 4,
                border: checked[i] ? 'none' : '2px solid #d1d5db',
                background: checked[i] ? 'var(--color-primary)' : 'transparent',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              {checked[i] && <Check size={13} color="#fff" />}
            </span>
            {item}
          </label>
        ))}
      </div>
    </div>
  );
}

function PlanViewer({ plan }) {
  const [activeDay, setActiveDay] = useState('monday');
  if (!plan) return null;

  const planData = plan.plan_data || {};

  const dayCalories = (day) => {
    const d = planData[day];
    if (!d) return 0;
    return MEAL_TYPES.reduce((sum, type) => {
      return sum + (d[type] || []).reduce((s, m) => s + (m.calories || 0), 0);
    }, 0);
  };

  return (
    <div>
      {/* Day tabs */}
      <div style={{ display: 'flex', gap: '0.25rem', overflowX: 'auto', marginBottom: '1rem', borderBottom: '2px solid #e5e7eb', paddingBottom: 0 }}>
        {DAYS.map((day) => (
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
              color: activeDay === day ? 'var(--color-primary)' : '#6b7280',
              fontSize: '0.85rem',
              marginBottom: '-2px',
              whiteSpace: 'nowrap',
              transition: 'all 0.15s',
            }}
          >
            {DAY_LABELS[day]}
            <span style={{ display: 'block', fontSize: '0.7rem', fontWeight: 400 }}>{dayCalories(day)} cal</span>
          </button>
        ))}
      </div>

      <DayPlan dayData={planData[activeDay]} />

      <ShoppingList items={plan.shopping_list} />

      {plan.advice && (
        <div className="card" style={{ padding: '1rem', marginTop: '1rem', borderLeft: '3px solid var(--color-info)' }}>
          <h4 style={{ margin: '0 0 0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
            <Lightbulb size={16} color="var(--color-warning)" /> Nutritional Advice
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
    if (!window.confirm('Delete this meal plan?')) return;
    setDeleting(true);
    try {
      await api.delete(`/planners/meal-plans/${plan.id}`);
      onDelete(plan.id);
    } catch {
      /* ignore */
    } finally {
      setDeleting(false);
    }
  };

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
            <h4 style={{ margin: 0, fontSize: '0.95rem' }}>{plan.plan_name || 'Meal Plan'}</h4>
            <span
              style={{
                padding: '0.15rem 0.5rem',
                borderRadius: '999px',
                fontSize: '0.7rem',
                fontWeight: 500,
                background: dietaryColor(plan.dietary_pattern),
                color: '#fff',
                textTransform: 'capitalize',
              }}
            >
              {(plan.dietary_pattern || '').replace('_', ' ')}
            </span>
          </div>
          <div style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Calendar size={13} />
            {plan.start_date} — {plan.end_date}
            {plan.total_daily_calories && (
              <span style={{ marginLeft: '0.5rem' }}>
                <Flame size={13} style={{ verticalAlign: '-2px' }} /> {plan.total_daily_calories} cal/day
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

export default function MealPlanner() {
  const [form, setForm] = useState({
    dietary_pattern: 'balanced',
    daily_calorie_target: 2000,
    allergies: '',
    preferences: '',
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
      const { data } = await api.get('/planners/meal-plans');
      setSavedPlans(Array.isArray(data) ? data : []);
    } catch {
      /* ignore */
    } finally {
      setLoadingPlans(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: name === 'daily_calorie_target' ? Number(value) : value }));
  };

  const handleGenerate = async (e) => {
    e.preventDefault();
    setGenerating(true);
    setError('');
    setGeneratedPlan(null);
    try {
      const { data } = await api.post('/planners/meal-plan', {
        dietary_pattern: form.dietary_pattern,
        daily_calorie_target: form.daily_calorie_target,
        allergies: form.allergies || undefined,
        preferences: form.preferences || undefined,
      });
      setGeneratedPlan(data);
      fetchSavedPlans();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to generate meal plan. Please try again.');
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
            <UtensilsCrossed size={28} color="var(--color-primary)" />
            AI Meal Planner
          </h1>
        </div>
        <p style={{ margin: '0.25rem 0 0', color: '#6b7280', fontSize: '0.9rem' }}>
          Generate personalized weekly meal plans tailored to your dietary needs.
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
              <label className="form-label" htmlFor="dietary_pattern">Dietary Pattern</label>
              <select
                id="dietary_pattern"
                name="dietary_pattern"
                className="form-select"
                value={form.dietary_pattern}
                onChange={handleChange}
              >
                {DIETARY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="daily_calorie_target">Daily Calorie Target</label>
              <input
                id="daily_calorie_target"
                name="daily_calorie_target"
                type="number"
                className="form-input"
                value={form.daily_calorie_target}
                onChange={handleChange}
                min={800}
                max={5000}
                step={50}
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="allergies">Allergies</label>
              <input
                id="allergies"
                name="allergies"
                type="text"
                className="form-input"
                placeholder="e.g. peanuts, gluten"
                value={form.allergies}
                onChange={handleChange}
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="preferences">Preferences</label>
              <input
                id="preferences"
                name="preferences"
                type="text"
                className="form-input"
                placeholder="e.g. high protein, West African"
                value={form.preferences}
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
                  <UtensilsCrossed size={16} style={{ marginRight: 6 }} />
                  Generate Meal Plan
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
              <h3 style={{ margin: 0, fontSize: '1rem' }}>{generatedPlan.plan_name || 'Your Meal Plan'}</h3>
              <div style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span
                  style={{
                    padding: '0.15rem 0.5rem',
                    borderRadius: '999px',
                    fontSize: '0.7rem',
                    fontWeight: 500,
                    background: dietaryColor(generatedPlan.dietary_pattern),
                    color: '#fff',
                    textTransform: 'capitalize',
                  }}
                >
                  {(generatedPlan.dietary_pattern || '').replace('_', ' ')}
                </span>
                <span><Calendar size={13} style={{ verticalAlign: '-2px' }} /> {generatedPlan.start_date} — {generatedPlan.end_date}</span>
                {generatedPlan.total_daily_calories && (
                  <span><Flame size={13} style={{ verticalAlign: '-2px' }} /> {generatedPlan.total_daily_calories} cal/day</span>
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
            <UtensilsCrossed size={36} style={{ marginBottom: '0.5rem', opacity: 0.4 }} />
            <p style={{ margin: 0, fontSize: '0.9rem' }}>No saved meal plans yet. Generate your first plan above!</p>
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
