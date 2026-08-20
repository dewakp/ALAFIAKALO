import { localToday } from '../utils/datetime';
import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { Calendar, BarChart3, Target } from 'lucide-react';
import BackButton from '../components/BackButton';

/* ─── helpers ─── */
const today = () => localToday();
const fmtDate = (d) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

/* Generic reference values, shown ONLY when the backend cannot personalize
   (incomplete profile). They are labelled as generic in the UI — presenting
   them as "personalized" is what hid the fact that a dialysis patient was being
   shown a healthy adult's phosphorus target.

   Real targets come from GET /nutrition/goal-progress, which derives them from
   age, sex, weight, activity and active chronic conditions
   (app/services/nutrient_goals_service.py). iOS and Android already use it. */
const FALLBACK_TARGETS = [
  { key: 'calories',      label: 'Calories',            unit: 'kcal', target: 2000  },
  { key: 'protein_g',     label: 'Protein',             unit: 'g',    target: 75    },
  { key: 'carbs_g',       label: 'Carbohydrates',       unit: 'g',    target: 250   },
  { key: 'fat_g',         label: 'Total Fat',           unit: 'g',    target: 65    },
  { key: 'fiber_g',       label: 'Dietary Fiber',       unit: 'g',    target: 30    },
  { key: 'sugar_g',       label: 'Added Sugar Limit',   unit: 'g',    target: 50    },
  { key: 'iron_mg',       label: 'Iron',                unit: 'mg',   target: 10    },
  { key: 'phosphorus_mg', label: 'Phosphate',           unit: 'mg',   target: 700   },
  { key: 'calcium_mg',    label: 'Calcium',             unit: 'mg',   target: 1000  },
  { key: 'sodium_mg',     label: 'Sodium',              unit: 'mg',   target: 1500  },
  { key: 'vitamin_d_iu',  label: 'Vitamin D',           unit: 'IU',   target: 600   },
  { key: 'potassium_mg',  label: 'Potassium',           unit: 'mg',   target: 3000  },
  { key: 'vitamin_b12_mcg','label':'Vitamin B12',       unit: 'µg',   target: 2.4   },
  { key: 'vitamin_b9_folate_mcg','label':'Folic Acid',  unit: 'µg',   target: 400   },
  { key: 'cholesterol_mg','label': 'Cholesterol',       unit: 'mg',   target: 300   },
  { key: 'magnesium_mg',  label: 'Magnesium',           unit: 'mg',   target: 420   },
  { key: 'zinc_mg',       label: 'Zinc',                unit: 'mg',   target: 11    },
  { key: 'vitamin_c_mg',  label: 'Vitamin C',           unit: 'mg',   target: 90    },
  { key: 'vitamin_a_iu',  label: 'Vitamin A',           unit: 'IU',   target: 3000  },
  { key: 'omega3_g',      label: 'Omega-3',             unit: 'g',    target: 1.6   },
];

/* Treatment effect on one nutrient, shown beside the intake figure and never
   folded into it — a potassium total driven near zero by dialysis must not
   read as licence to eat more. */
function BalanceLine({ balance, unit }) {
  const gained = balance.direction === 'gained';
  const withheld = balance.withheld;
  if (!withheld && Math.abs(balance.delta) < 0.005) return null;

  return (
    <div style={{ fontSize: '.68rem', marginTop: '.2rem', lineHeight: 1.4 }}>
      {withheld ? (
        <span style={{ color: '#b45309' }}>{withheld}</span>
      ) : (
        <>
          <span style={{ color: gained ? '#b45309' : 'var(--color-primary)', fontWeight: 600 }}>
            {gained ? '+' : ''}{fmtAmount(balance.delta)}{showUnit(unit)} from dialysis
          </span>
          <span style={{ color: 'var(--color-text-tertiary)' }}>
            {' '}· net {fmtAmount(balance.net)}{showUnit(unit)} retained today
          </span>
          {!balance.calibrated && (
            <span style={{ color: 'var(--color-text-tertiary)' }}> · estimated</span>
          )}
        </>
      )}
    </div>
  );
}

function barColor(pct, isLimit) {
  if (isLimit) return pct > 100 ? '#ef4444' : '#f59e0b';
  if (pct >= 100) return '#22c55e';
  if (pct >= 50)  return '#3b82f6';
  return '#f59e0b';
}

/* "mcg" is how the API names the unit; µg is how it should read. */
const UNIT_LABELS = { mcg: 'µg' };
const showUnit = (u) => UNIT_LABELS[u] || u;

/* Human labels for the condition flags the goals engine reports back, so the
   patient can see *why* a limit is what it is. */
const FLAG_LABELS = {
  dialysis: 'Dialysis', ckd: 'Chronic kidney disease', diabetes: 'Diabetes',
  hypertension: 'Hypertension', heart_failure: 'Heart failure',
  cardiovascular: 'Cardiovascular', liver: 'Liver disease', anemia: 'Anemia',
  pregnancy: 'Pregnancy', obesity: 'Weight management',
};

const fmtAmount = (n) => (n == null ? '—' : n < 10 ? Number(n).toFixed(1) : Math.round(n));

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
export default function NutrientTracking() {
  const [trackDate, setTrackDate] = useState(today);
  const [summary, setSummary] = useState(null);
  const [progress, setProgress] = useState(null);
  const [loading, setLoading] = useState(false);
  const [goalsError, setGoalsError] = useState(null);

  const load = useCallback(async (d) => {
    setLoading(true);
    setGoalsError(null);
    /* Settled, not all — a failed goals call must not blank the intake panel,
       and a failed summary must not hide the goals. */
    const [summaryRes, goalsRes] = await Promise.allSettled([
      api.get(`/nutrition/daily-summary?date=${d}`),
      api.get(`/nutrition/goal-progress?date=${d}`),
    ]);

    setSummary(summaryRes.status === 'fulfilled' ? summaryRes.value.data : null);

    if (goalsRes.status === 'fulfilled') {
      setProgress(goalsRes.value.data);
    } else {
      /* Never fall through to the generic table pretending it is personalized —
         say the personalization failed. */
      setProgress(null);
      setGoalsError('Your personalized targets could not be loaded, so the generic reference values below are shown instead.');
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(trackDate); }, [load, trackDate]);

  /* Build a lookup from the summary nutrients list (key → value) */
  const nutrientMap = {};
  if (summary?.nutrients) {
    summary.nutrients.forEach(n => { nutrientMap[n.key] = n.value; });
  }
  /* Also pull top-level fields from summary */
  if (summary) {
    nutrientMap.calories  = summary.total_calories;
    nutrientMap.protein_g = summary.total_protein_g;
    nutrientMap.carbs_g   = summary.total_carbs_g;
    nutrientMap.fat_g     = summary.total_fat_g;
  }

  /* The goals endpoint already aggregates intake per nutrient, so when it is
     available it is the single source for both panels. */
  const personalized = progress?.goals?.length ? progress.goals : null;
  const rows = personalized
    ? personalized.map(g => ({
        key: g.key, label: g.name, unit: g.unit,
        target: g.goal, intake: g.current ?? nutrientMap[g.key] ?? 0,
        isLimit: g.kind === 'limit', rationale: g.rationale, status: g.status,
        balance: g.dialysis_balance || null,
      }))
    : FALLBACK_TARGETS.map(t => ({
        key: t.key, label: t.label, unit: t.unit,
        target: t.target, intake: nutrientMap[t.key] ?? 0,
        isLimit: ['sugar_g','sodium_mg','cholesterol_mg','phosphorus_mg'].includes(t.key),
        rationale: null, status: null,
      }));

  const activeFlags = progress?.conditions || [];
  const dialysis = progress?.dialysis || null;

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Nutrient Tracking</h1>
        </div>
      </div>

      {/* ── Date selector ── */}
      <div className="card" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '.75rem', flexWrap: 'wrap' }}>
        <Calendar size={16} style={{ color: 'var(--color-primary)' }}/>
        <strong style={{ fontSize: '.9rem' }}>Track for Date:</strong>
        <input type="date" className="form-input" value={trackDate}
          onChange={e => setTrackDate(e.target.value)}
          style={{ maxWidth: 180, padding: '.35rem .6rem', fontSize: '.88rem' }}/>
        {summary && (
          <span style={{ fontSize: '.82rem', color: 'var(--color-text-secondary)' }}>
            {summary.meal_count} meal(s) logged
          </span>
        )}
      </div>

      {/* Dialysis changes the day's balance, never the dietary limit — the
          guideline figures already assume the patient is on dialysis. */}
      {dialysis?.had_dialysis && (
        <div className="card" style={{ marginBottom: '1rem', padding: '.75rem 1rem',
          background: 'var(--color-primary-light, #e0f2fe)', border: '1px solid #7dd3fc' }}>
          <strong style={{ fontSize: '.88rem', color: 'var(--color-primary)' }}>
            Dialysis on this day — {dialysis.session_count} session{dialysis.session_count === 1 ? '' : 's'}
          </strong>
          <div style={{ fontSize: '.78rem', color: 'var(--color-text-secondary)', marginTop: '.2rem' }}>
            Your limits are unchanged: they already assume your usual treatment. What changes is
            the day's balance — some of what you ate was removed, and some minerals crossed in
            from the dialysate.
          </div>
          {dialysis.notes?.map((note, i) => (
            <div key={i} style={{ fontSize: '.74rem', color: '#b45309', marginTop: '.25rem' }}>{note}</div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', alignItems: 'start' }}>

        {/* ── LEFT: Intake progress bars ── */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '1rem' }}>
            <BarChart3 size={16} style={{ color: 'var(--color-primary)' }}/>
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>
              Your Intake for {fmtDate(trackDate)}
            </h3>
          </div>

          {loading && <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-tertiary)' }}>Loading…</div>}

          {!loading && (
            <>
              {summary && (
                <p style={{ fontSize: '.78rem', color: 'var(--color-text-tertiary)', marginBottom: '1rem' }}>
                  {summary.meal_count} food {summary.meal_count === 1 ? 'entry' : 'entries'} included.
                </p>
              )}
              {rows.map(r => {
                const pct = r.target > 0 ? Math.round((r.intake / r.target) * 100) : 0;
                const color = barColor(pct, r.isLimit);
                return (
                  <div key={r.key} style={{ marginBottom: '.75rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.82rem', marginBottom: '.2rem' }}>
                      <span style={{ color: 'var(--color-text-primary)', fontWeight: 500 }}>
                        {r.label}
                        {r.isLimit && (
                          <span style={{ fontSize: '.68rem', color: 'var(--color-text-tertiary)', marginLeft: '.35rem' }}>
                            limit
                          </span>
                        )}
                      </span>
                      <span style={{ fontFamily: 'monospace', color: 'var(--color-text-secondary)' }}>
                        {fmtAmount(r.intake)}{showUnit(r.unit)} / {fmtAmount(r.target)}{showUnit(r.unit)}
                      </span>
                    </div>
                    <div style={{ background: 'var(--color-bg-secondary)', borderRadius: 6, height: 10, overflow: 'hidden' }}>
                      <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', background: color,
                        borderRadius: 6, transition: 'width .4s ease' }}/>
                    </div>
                    {r.isLimit && pct > 100 && (
                      <div style={{ fontSize: '.68rem', color: '#ef4444', marginTop: '.15rem' }}>
                        Limit exceeded ({pct}% of daily limit)
                      </div>
                    )}
                    {r.balance && <BalanceLine balance={r.balance} unit={r.unit} />}
                  </div>
                );
              })}
            </>
          )}
        </div>

        {/* ── RIGHT: Personalized Targets reference panel ── */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '1rem' }}>
            <Target size={16} style={{ color: 'var(--color-primary)' }}/>
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Your Personalized Daily Targets</h3>
          </div>
          <p style={{ fontSize: '.78rem', color: 'var(--color-text-tertiary)', marginBottom: '.5rem' }}>
            {personalized
              ? `Derived from your age, sex, weight, activity${activeFlags.length ? ' and active conditions' : ''}.`
              : 'Generic reference values — not personalized to your profile.'}
          </p>

          {goalsError && (
            <p style={{ fontSize: '.78rem', color: '#b45309', background: '#fef3c7',
              border: '1px solid #fcd34d', borderRadius: 6, padding: '.5rem .6rem', marginBottom: '.75rem' }}>
              {goalsError}
            </p>
          )}

          {personalized && progress?.profile_complete === false && (
            <p style={{ fontSize: '.78rem', color: '#b45309', background: '#fef3c7',
              border: '1px solid #fcd34d', borderRadius: 6, padding: '.5rem .6rem', marginBottom: '.75rem' }}>
              Your profile is incomplete, so some targets fall back to general reference values.
              Add your height, weight and date of birth to sharpen them.
            </p>
          )}

          {/* Show which conditions shaped these numbers — otherwise a renal
              limit is indistinguishable from a healthy adult's target. */}
          {activeFlags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.35rem', marginBottom: '.75rem' }}>
              {activeFlags.map(f => (
                <span key={f} style={{ fontSize: '.7rem', fontWeight: 600, padding: '.15rem .5rem',
                  borderRadius: 999, background: 'var(--color-primary-light, #e0f2fe)', color: 'var(--color-primary)' }}>
                  {FLAG_LABELS[f] || f}
                </span>
              ))}
            </div>
          )}

          {rows.map(r => (
            <div key={r.key} style={{ padding: '.4rem 0', borderBottom: '1px solid var(--color-border)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.85rem' }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>
                  {r.label}
                  {r.isLimit && (
                    <span style={{ fontSize: '.68rem', color: '#b45309', marginLeft: '.35rem' }}>limit</span>
                  )}
                </span>
                <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>
                  {fmtAmount(r.target)}{showUnit(r.unit)}
                </span>
              </div>
              {r.rationale && (
                <div style={{ fontSize: '.7rem', color: 'var(--color-text-tertiary)', marginTop: '.15rem', lineHeight: 1.35 }}>
                  {r.rationale}
                </div>
              )}
            </div>
          ))}
          <p style={{ fontSize: '.72rem', color: 'var(--color-text-tertiary)', marginTop: '.75rem', fontStyle: 'italic' }}>
            These are AI-generated estimates and not medical advice. Consult a healthcare professional or registered dietitian for personalized nutritional guidance.
          </p>
        </div>
      </div>
    </div>
  );
}

