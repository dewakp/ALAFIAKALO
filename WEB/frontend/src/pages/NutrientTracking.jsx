import { localToday } from '../utils/datetime';
import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { Calendar, BarChart3, Target } from 'lucide-react';
import BackButton from '../components/BackButton';

/* ─── helpers ─── */
const today = () => localToday();
const fmtDate = (d) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

/* Static personalized targets — FDA DV 2020, renal-adjusted per app profile
   These mirror the "Personalized Daily Targets" panel in the Firebase app.
   TODO(alafia-model): replace with ALAFIAModel.infer('targets', userProfile) — Phase 3 */
const TARGETS = [
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

function barColor(pct, isLimit) {
  if (isLimit) return pct > 100 ? '#ef4444' : '#f59e0b';
  if (pct >= 100) return '#22c55e';
  if (pct >= 50)  return '#3b82f6';
  return '#f59e0b';
}
const LIMIT_KEYS = new Set(['sugar_g','sodium_mg','cholesterol_mg','phosphorus_mg']);

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
export default function NutrientTracking() {
  const [trackDate, setTrackDate] = useState(today);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (d) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/nutrition/daily-summary?date=${d}`);
      setSummary(data);
    } catch { setSummary(null); } finally { setLoading(false); }
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
              {TARGETS.map(t => {
                const intake = nutrientMap[t.key] ?? 0;
                const pct = t.target > 0 ? Math.round((intake / t.target) * 100) : 0;
                const isLimit = LIMIT_KEYS.has(t.key);
                const color = barColor(pct, isLimit);
                const intakeFmt = intake < 10 ? intake.toFixed(1) : Math.round(intake);
                return (
                  <div key={t.key} style={{ marginBottom: '.75rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.82rem', marginBottom: '.2rem' }}>
                      <span style={{ color: 'var(--color-text-primary)', fontWeight: 500 }}>{t.label}</span>
                      <span style={{ fontFamily: 'monospace', color: 'var(--color-text-secondary)' }}>
                        {intakeFmt}{t.unit} / {t.target}{t.unit}
                      </span>
                    </div>
                    <div style={{ background: 'var(--color-bg-secondary)', borderRadius: 6, height: 10, overflow: 'hidden' }}>
                      <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', background: color,
                        borderRadius: 6, transition: 'width .4s ease' }}/>
                    </div>
                    {isLimit && pct > 100 && (
                      <div style={{ fontSize: '.68rem', color: '#ef4444', marginTop: '.15rem' }}>
                        Limit exceeded ({pct}% of daily limit)
                      </div>
                    )}
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
          <p style={{ fontSize: '.78rem', color: 'var(--color-text-tertiary)', marginBottom: '1rem' }}>
            Estimated by Alafia based on your profile.
          </p>
          {TARGETS.map(t => (
            <div key={t.key} style={{ display: 'flex', justifyContent: 'space-between', padding: '.4rem 0',
              borderBottom: '1px solid var(--color-border)', fontSize: '.85rem' }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>{t.label}</span>
              <span style={{ fontWeight: 600, fontFamily: 'monospace' }}>{t.target}{t.unit}</span>
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

