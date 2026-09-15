import { useState, useEffect } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import api, { AI_TIMEOUT_MS } from '../services/api';
import {
  UtensilsCrossed,
  Sparkles,
  ShoppingCart,
  Loader2,
  Flame,
  Beef,
  Wheat,
  Droplets,
  Check,
  Lightbulb,
} from 'lucide-react';
import BackButton from '../components/BackButton';
import { t as translate } from '../i18n';

const MEAL_EMOJI = { breakfast: '🌅', lunch: '☀️', dinner: '🌙', snack: '🍎', meal: '🍽️' };

function Chip({ children, tone = 'neutral' }) {
  const tones = {
    neutral: { bg: 'var(--color-bg-secondary, rgba(127,127,127,.12))', fg: 'var(--color-text-secondary, #6b7280)' },
    pantry: { bg: 'rgba(34,197,94,.15)', fg: '#16a34a' },
    buy: { bg: 'rgba(245,158,11,.15)', fg: '#d97706' },
  };
  const t = tones[tone] || tones.neutral;
  return (
    <span style={{
      fontSize: '.72rem', padding: '.18rem .5rem', borderRadius: 999,
      background: t.bg, color: t.fg, whiteSpace: 'nowrap',
    }}>{children}</span>
  );
}

function SuggestionCard({ s }) {
  const macro = (icon, val, label) =>
    val == null ? null : (
      <span title={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
        {icon}{Math.round(val)}{label === 'Calories' ? '' : 'g'} {label[0]}
      </span>
    );
  return (
    <div className="card" style={{ padding: '1.1rem', marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '.75rem', flexWrap: 'wrap' }}>
        <h4 style={{ margin: 0, fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '.4rem' }}>
          <span>{MEAL_EMOJI[s.meal_type] || '🍽️'}</span>
          {s.name}
          <span style={{ fontSize: '.68rem', textTransform: 'capitalize', color: 'var(--color-text-tertiary,#9ca3af)', fontWeight: 400 }}>
            {s.meal_type}
          </span>
        </h4>
        <div style={{ display: 'flex', gap: '.75rem', fontSize: '.78rem', color: 'var(--color-text-secondary,#6b7280)' }}>
          {macro(<Flame size={13} />, s.calories, 'Calories')}
          {s.calories != null && <span style={{ fontSize: '.72rem' }}>{translate('MealPlanner.cal')}</span>}
          {macro(<Beef size={12} />, s.protein_g, 'Protein')}
          {macro(<Wheat size={12} />, s.carbs_g, 'Carbs')}
          {macro(<Droplets size={12} />, s.fat_g, 'Fat')}
        </div>
      </div>

      {s.description && (
        <p style={{ margin: '.5rem 0 .25rem', fontSize: '.85rem', color: 'var(--color-text-secondary,#6b7280)', lineHeight: 1.5 }}>
          {s.description}
        </p>
      )}

      {s.ingredients?.length > 0 && (
        <div style={{ marginTop: '.5rem' }}>
          <div style={{ fontSize: '.72rem', fontWeight: 600, color: 'var(--color-text-tertiary,#9ca3af)', marginBottom: '.3rem' }}>INGREDIENTS</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.3rem' }}>
            {s.ingredients.map((ing, i) => <Chip key={i}>{ing}</Chip>)}
          </div>
        </div>
      )}

      {s.pantry_used?.length > 0 && (
        <div style={{ marginTop: '.5rem', display: 'flex', flexWrap: 'wrap', gap: '.3rem', alignItems: 'center' }}>
          <span style={{ fontSize: '.72rem', fontWeight: 600, color: '#16a34a' }}>✓ FROM YOUR PANTRY</span>
          {s.pantry_used.map((p, i) => <Chip key={i} tone="pantry">{p}</Chip>)}
        </div>
      )}

      {s.missing_items?.length > 0 && (
        <div style={{ marginTop: '.5rem', display: 'flex', flexWrap: 'wrap', gap: '.3rem', alignItems: 'center' }}>
          <span style={{ fontSize: '.72rem', fontWeight: 600, color: '#d97706' }}>🛒 TO BUY</span>
          {s.missing_items.map((m, i) => <Chip key={i} tone="buy">{m}</Chip>)}
        </div>
      )}

      {s.rationale && (
        <div style={{ marginTop: '.6rem', padding: '.55rem .7rem', borderRadius: 8, background: 'rgba(59,130,246,.08)', borderLeft: '3px solid var(--color-info,#3b82f6)' }}>
          <p style={{ margin: 0, fontSize: '.8rem', color: 'var(--color-text-secondary,#374151)', lineHeight: 1.5, display: 'flex', gap: '.4rem' }}>
            <Lightbulb size={14} color="var(--color-warning,#f59e0b)" style={{ flexShrink: 0, marginTop: 2 }} />
            {s.rationale}
          </p>
        </div>
      )}
    </div>
  );
}

function ShoppingList({ items }) {
  const [checked, setChecked] = useState({});
  if (!items?.length) return null;
  const toggle = (i) => setChecked((p) => ({ ...p, [i]: !p[i] }));
  const done = Object.values(checked).filter(Boolean).length;
  return (
    <div className="card" style={{ padding: '1.25rem', marginTop: '.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '.75rem' }}>
        <h4 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '.5rem' }}>
          <ShoppingCart size={18} /> {translate('MealPlanner.shopping_list')} <span style={{ fontSize: '.75rem', fontWeight: 400, color: 'var(--color-text-tertiary,#9ca3af)' }}>{translate('MealPlanner.missing_items')}</span>
        </h4>
        <span style={{ fontSize: '.8rem', color: 'var(--color-text-tertiary,#6b7280)' }}>{done}/{items.length}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '.25rem' }}>
        {items.map((item, i) => (
          <label key={i} onClick={() => toggle(i)} style={{
            display: 'flex', alignItems: 'center', gap: '.5rem', padding: '.35rem .5rem',
            borderRadius: 6, cursor: 'pointer', fontSize: '.85rem',
            textDecoration: checked[i] ? 'line-through' : 'none',
            color: checked[i] ? 'var(--color-text-tertiary,#9ca3af)' : 'var(--color-text-primary,#374151)',
          }}>
            <span style={{
              width: 18, height: 18, borderRadius: 4, flexShrink: 0,
              border: checked[i] ? 'none' : '2px solid var(--color-border,#d1d5db)',
              background: checked[i] ? 'var(--color-primary)' : 'transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>{checked[i] && <Check size={13} color="#fff" />}</span>
            {item}
          </label>
        ))}
      </div>
    </div>
  );
}

export default function MealPlanner() {
  const [form, setForm] = useState({ health_goals: '', preferences: '', pantry_items: '', count: 3 });
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  // Pre-fill the pantry box with the items already saved in the user's profile.
  useEffect(() => {
    api.get('/pantry/')
      .then(({ data }) => {
        const names = (Array.isArray(data) ? data : []).map((it) => it.name).filter(Boolean);
        if (names.length) {
          setForm((p) => (p.pantry_items ? p : { ...p, pantry_items: names.join(', ') }));
        }
      })
      .catch(() => {});
  }, []);

  const change = (e) => {
    const { name, value } = e.target;
    setForm((p) => ({ ...p, [name]: name === 'count' ? Number(value) : value }));
  };

  const generate = async (e) => {
    e.preventDefault();
    if (!form.health_goals.trim()) {
      setError(translate('MealPlanner.please_enter_your_main_health_goals'));
      return;
    }
    setGenerating(true);
    setError('');
    setResult(null);
    try {
      const { data } = await api.post('/planners/meal-suggestions', {
        health_goals: form.health_goals,
        preferences: form.preferences || undefined,
        pantry_items: form.pantry_items || undefined,
        count: form.count,
      }, { timeout: AI_TIMEOUT_MS }); // must stay BELOW Cloud Run's 300s, not equal to it
      setResult(data);
    } catch (err) {
      setError(apiErrorMessage(err, translate('MealPlanner.failed_to_generate_meal_plan_please_try')));
    } finally {
      setGenerating(false);
    }
  };

  const label = { display: 'block', fontWeight: 600, fontSize: '.9rem', marginBottom: '.4rem' };

  return (
    <div style={{ maxWidth: 920, margin: '0 auto', padding: '1.5rem 1rem' }}>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
            <UtensilsCrossed size={28} color="var(--color-primary)" /> {translate('MealPlanner.ai_meal_planner')}
          </h1>
        </div>
        <p style={{ margin: '.25rem 0 0', color: 'var(--color-text-secondary,#6b7280)', fontSize: '.95rem' }}>
          {translate('MealPlanner.get_personalized_meal_recommendations')}
        </p>
      </div>

      {/* Generator form */}
      <div className="card" style={{ padding: '1.75rem', marginBottom: '2rem' }}>
        <h3 style={{ margin: '0 0 .35rem', display: 'flex', alignItems: 'center', gap: '.5rem', fontSize: '1.15rem' }}>
          <Sparkles size={20} color="var(--color-primary)" /> {translate('MealPlanner.generate_your_meal_plan')}
        </h3>
        <p style={{ margin: '0 0 1.25rem', color: 'var(--color-text-secondary,#6b7280)', fontSize: '.88rem' }}>
          {translate('MealPlanner.tell_alafia_your_goals_and_preferences')}
        </p>

        <form onSubmit={generate}>
          <div style={{ marginBottom: '1.1rem' }}>
            <label style={label} htmlFor="health_goals">{translate('MealPlanner.what_are_your_main_health_goals_right')}</label>
            <input
              id="health_goals" name="health_goals" className="form-input"
              placeholder={translate('MealPlanner.e_g_improve_hemoglobin_increase_vitamin')}
              value={form.health_goals} onChange={change} required
            />
          </div>

          <div style={{ marginBottom: '1.1rem' }}>
            <label style={label} htmlFor="preferences">{translate('MealPlanner.any_specific_meal_preferences_likes_or')}</label>
            <textarea
              id="preferences" name="preferences" className="form-input" rows={3}
              placeholder={translate('MealPlanner.e_g_i_enjoy_a_variety_of_foods_no_fava')}
              value={form.preferences} onChange={change} style={{ resize: 'vertical' }}
            />
          </div>

          <div style={{ marginBottom: '.4rem' }}>
            <label style={label} htmlFor="pantry_items">{translate('MealPlanner.pantry_fridge_items_optional')}</label>
            <textarea
              id="pantry_items" name="pantry_items" className="form-input" rows={3}
              placeholder={translate('MealPlanner.e_g_brown_eggs_brown_rice_cashew_butter')}
              value={form.pantry_items} onChange={change} style={{ resize: 'vertical' }}
            />
            <p style={{ margin: '.35rem 0 0', fontSize: '.78rem', color: 'var(--color-text-tertiary,#9ca3af)' }}>
              {translate('MealPlanner.list_ingredients_you_have_on_hand_to_get')}
            </p>
          </div>

          <div style={{ margin: '1.25rem 0' }}>
            <label style={label} htmlFor="count">{translate('MealPlanner.how_many_meal_suggestions_would_you_like')}</label>
            <select id="count" name="count" className="form-select" value={form.count} onChange={change} style={{ maxWidth: 220 }}>
              {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>

          {error && (
            <div style={{ marginBottom: '1rem', padding: '.65rem 1rem', borderRadius: 8, background: 'rgba(239,68,68,.1)', color: 'var(--color-danger,#dc2626)', fontSize: '.85rem' }}>
              {error}
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={generating} style={{ minWidth: 210, opacity: generating ? 0.7 : 1 }}>
            {generating
              ? <><Loader2 size={16} className="spin" style={{ marginRight: 6 }} /> {translate('MealPlanner.generating')}</>
              : <><Sparkles size={16} style={{ marginRight: 6 }} /> {translate('MealPlanner.generate_my_meal_plan')}</>}
          </button>
        </form>
      </div>

      {/* Results */}
      {result && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.5rem' }}>
            <UtensilsCrossed size={20} color="var(--color-primary)" />
            <h3 style={{ margin: 0, fontSize: '1.1rem' }}>{translate('MealPlanner.your_meal_suggestions')}</h3>
          </div>
          {result.advice && (
            <p style={{ margin: '0 0 1rem', fontSize: '.85rem', color: 'var(--color-text-secondary,#6b7280)' }}>{result.advice}</p>
          )}

          {result.suggestions?.map((s, i) => <SuggestionCard key={i} s={s} />)}

          <ShoppingList items={result.shopping_list} />

          {result.pantry_saved > 0 && (
            <p style={{ margin: '.75rem 0 0', fontSize: '.78rem', color: 'var(--color-text-tertiary,#9ca3af)' }}>
              {(result.pantry_saved === 1) ? translate('MealPlanner.new_pantry_item_saved_to_your_profile', { pantry_saved: result.pantry_saved }) : translate('MealPlanner.new_pantry_items_saved_to_your_profile', { pantry_saved: result.pantry_saved })}
            </p>
          )}
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } } .spin { animation: spin 1s linear infinite; }`}</style>
    </div>
  );
}
