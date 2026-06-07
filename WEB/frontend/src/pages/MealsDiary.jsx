import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { ChevronLeft, ChevronRight, Clock, Weight, Plus, RefreshCw, Edit2 } from 'lucide-react';
import BackButton from '../components/BackButton';

/* ─── helpers ─── */
const today = () => new Date().toISOString().split('T')[0];
const fmt = (d) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
const MEAL_ORDER = ['breakfast', 'lunch', 'dinner', 'snack', 'other'];
const MEAL_EMOJI = { breakfast: '🌅', lunch: '☀️', dinner: '🌙', snack: '🍎', other: '🍽️' };

/* Macro pills shown on each meal card (matches Firebase app) */
const MACRO_PILLS = [
  { key: 'calories',      label: 'Cal',   unit: 'kcal', danger: null },
  { key: 'protein_g',     label: 'P',     unit: 'g',    danger: null },
  { key: 'carbs_g',       label: 'C',     unit: 'g',    danger: null },
  { key: 'fat_g',         label: 'F',     unit: 'g',    danger: null },
  { key: 'fiber_g',       label: 'Fib',   unit: 'g',    danger: null },
  { key: 'sugar_g',       label: 'Sug',   unit: 'g',    danger: 50  },
  { key: 'iron_mg',       label: 'Fe',    unit: 'mg',   danger: null },
  { key: 'phosphorus_mg', label: 'Phos',  unit: 'mg',   danger: 1000 },
  { key: 'calcium_mg',    label: 'Ca',    unit: 'mg',   danger: null },
  { key: 'sodium_mg',     label: 'Na',    unit: 'mg',   danger: 2300 },
  { key: 'vitamin_d_iu',  label: 'VitD',  unit: 'IU',   danger: null },
  { key: 'potassium_mg',  label: 'K',     unit: 'mg',   danger: null },
  { key: 'vitamin_b12_mcg','label': 'B12', unit: 'µg',  danger: null },
  { key: 'vitamin_b9_folate_mcg','label':'Fol','unit':'µg',danger:null },
  { key: 'cholesterol_mg','label': 'Chol','unit': 'mg', danger: 300 },
];

function pillColor(pill, value) {
  if (value == null || value === 0) return 'rgba(255,255,255,.12)';
  if (pill.danger && value > pill.danger) return 'rgba(239,68,68,.25)';
  return 'rgba(34,197,94,.18)';
}
function pillText(pill, value) {
  if (value == null) return `${pill.label}: —`;
  const v = value < 10 ? value.toFixed(1) : Math.round(value);
  return `${pill.label}: ${v}${pill.unit}`;
}

/* ─── Calendar grid helpers ─── */
function buildCalendar(year, month) {
  const first = new Date(year, month, 1).getDay(); // 0=Sun
  const days = new Date(year, month + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < first; i++) cells.push(null);
  for (let d = 1; d <= days; d++) cells.push(d);
  return cells;
}
const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
export default function MealsDiary() {
  const navigate = useNavigate();
  const now = new Date();
  const [calYear, setCalYear]   = useState(now.getFullYear());
  const [calMonth, setCalMonth] = useState(now.getMonth());
  const [selectedDate, setSelectedDate] = useState(today());
  const [logsByDate, setLogsByDate] = useState({});   // { 'YYYY-MM-DD': [log, …] }
  const [loading, setLoading] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(null); // log id being re-analyzed

  /* Load the entire visible month + next few days so dots are accurate */
  const loadMonth = useCallback(async (year, month) => {
    setLoading(true);
    const startDate = `${year}-${String(month + 1).padStart(2, '0')}-01`;
    const lastDay = new Date(year, month + 1, 0).getDate();
    const endDate = `${year}-${String(month + 1).padStart(2, '0')}-${lastDay}`;
    try {
      const { data } = await api.get(`/nutrition/?start_date=${startDate}&end_date=${endDate}`);
      const grouped = {};
      data.forEach((log) => {
        if (!grouped[log.log_date]) grouped[log.log_date] = [];
        grouped[log.log_date].push(log);
      });
      setLogsByDate(grouped);
    } catch { setLogsByDate({}); } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadMonth(calYear, calMonth); }, [loadMonth, calYear, calMonth]);

  /* Navigate calendar months */
  const prevMonth = () => {
    if (calMonth === 0) { setCalYear(y => y - 1); setCalMonth(11); }
    else setCalMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (calMonth === 11) { setCalYear(y => y + 1); setCalMonth(0); }
    else setCalMonth(m => m + 1);
  };

  /* Re-analyze a meal via NLM pipeline */
  const reanalyze = async (log) => {
    if (!log.food_name) return;
    setReanalyzing(log.id);
    try {
      // TODO(alafia-model): replace with ALAFIAModel.infer('nlm', log.food_name) — Phase 1
      await api.post('/nutrition/estimate-meal', {
        description: log.food_name,
        log_date: log.log_date,
        meal_type: log.meal_type,
      });
      await loadMonth(calYear, calMonth);
    } catch { /* silent */ } finally { setReanalyzing(null); }
  };

  const cells = buildCalendar(calYear, calMonth);
  const selectedLogs = logsByDate[selectedDate] || [];
  const grouped = {};
  selectedLogs.forEach((l) => {
    const m = l.meal_type || 'other';
    if (!grouped[m]) grouped[m] = [];
    grouped[m].push(l);
  });

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Meals Diary</h1>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/nutrition')}>
          <Plus size={16}/> Log New Food Intake
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '1rem', alignItems: 'start' }}>
        {/* ── LEFT: Calendar ── */}
        <div className="card" style={{ padding: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '.75rem' }}>
            <button className="btn btn-secondary btn-sm" onClick={prevMonth}><ChevronLeft size={14}/></button>
            <span style={{ fontWeight: 700, fontSize: '.9rem' }}>{MONTH_NAMES[calMonth]} {calYear}</span>
            <button className="btn btn-secondary btn-sm" onClick={nextMonth}><ChevronRight size={14}/></button>
          </div>
          {/* Day-of-week header */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', textAlign: 'center',
            fontSize: '.7rem', color: 'var(--color-text-tertiary)', marginBottom: '.35rem' }}>
            {['Su','Mo','Tu','We','Th','Fr','Sa'].map(d => <span key={d}>{d}</span>)}
          </div>
          {/* Day cells */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '2px' }}>
            {cells.map((day, i) => {
              if (!day) return <div key={i}/>;
              const dateStr = `${calYear}-${String(calMonth+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
              const hasLog = !!logsByDate[dateStr];
              const isSelected = dateStr === selectedDate;
              const isToday = dateStr === today();
              return (
                <button key={i} onClick={() => setSelectedDate(dateStr)}
                  style={{ position: 'relative', padding: '.35rem 0', fontSize: '.82rem', fontWeight: isToday ? 700 : 400,
                    border: 'none', borderRadius: 6, cursor: 'pointer', textAlign: 'center',
                    background: isSelected ? 'var(--color-primary)' : 'transparent',
                    color: isSelected ? '#fff' : isToday ? 'var(--color-primary)' : 'var(--color-text-primary)' }}>
                  {day}
                  {hasLog && (
                    <span style={{ position: 'absolute', bottom: 2, left: '50%', transform: 'translateX(-50%)',
                      width: 5, height: 5, borderRadius: '50%',
                      background: isSelected ? '#fff' : 'var(--color-primary)' }}/>
                  )}
                </button>
              );
            })}
          </div>
          <div style={{ marginTop: '.75rem', fontSize: '.72rem', color: 'var(--color-text-tertiary)', textAlign: 'center' }}>
            Dates with a <span style={{ color: 'var(--color-primary)', fontSize: '1em' }}>●</span> have logged meals.
          </div>
        </div>

        {/* ── RIGHT: Meals for selected date ── */}
        <div>
          <h2 style={{ margin: '0 0 .75rem', fontSize: '1.1rem', fontWeight: 700 }}>
            Meals for {fmt(selectedDate)}
          </h2>

          {loading && <div className="card" style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-tertiary)' }}>Loading…</div>}

          {!loading && selectedLogs.length === 0 && (
            <div className="card" style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-tertiary)' }}>
              No meals logged for this date.
              <div style={{ marginTop: '1rem' }}>
                <button className="btn btn-primary btn-sm" onClick={() => navigate('/nutrition')}>Log New Food Intake</button>
              </div>
            </div>
          )}

          {MEAL_ORDER.filter(m => grouped[m]).map(mealType => (
            <div key={mealType} className="card" style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '.6rem' }}>
                <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, textTransform: 'capitalize' }}>
                  {MEAL_EMOJI[mealType]} {mealType}
                </h3>
              </div>
              {grouped[mealType].map(log => (
                <div key={log.id} style={{ marginBottom: '1rem', paddingBottom: '1rem',
                  borderBottom: '1px solid var(--color-border)' }}>
                  {/* Header row: description + buttons */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '.5rem', marginBottom: '.4rem' }}>
                    <p style={{ margin: 0, fontSize: '.88rem', fontWeight: 500, flex: 1 }}>
                      <strong>Description:</strong> {log.food_name}
                    </p>
                    <div style={{ display: 'flex', gap: '.4rem', flexShrink: 0 }}>
                      <button className="btn btn-secondary btn-sm" onClick={() => reanalyze(log)}
                        disabled={reanalyzing === log.id}
                        style={{ fontSize: '.72rem', padding: '.25rem .5rem', display: 'flex', alignItems: 'center', gap: '.25rem' }}>
                        <RefreshCw size={11} style={reanalyzing === log.id ? { animation: 'spin 1s linear infinite' } : {}}/>
                        Re-analyze
                      </button>
                      <button className="btn btn-secondary btn-sm"
                        onClick={() => navigate('/nutrition')}
                        style={{ fontSize: '.72rem', padding: '.25rem .5rem', display: 'flex', alignItems: 'center', gap: '.25rem' }}>
                        <Edit2 size={11}/> Edit
                      </button>
                    </div>
                  </div>

                  {/* Time & weight */}
                  <div style={{ display: 'flex', gap: '1rem', fontSize: '.78rem', color: 'var(--color-text-secondary)', marginBottom: '.5rem', flexWrap: 'wrap' }}>
                    {(log.start_time || log.end_time) && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '.25rem' }}>
                        <Clock size={12}/>
                        {log.start_time ? log.start_time.slice(0,5) : '?'}
                        {log.end_time ? ` - ${log.end_time.slice(0,5)}` : ''}
                      </span>
                    )}
                    {log.pre_meal_weight_kg && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '.25rem' }}>
                        <Weight size={12}/> Pre-Meal: {log.pre_meal_weight_kg} kg
                      </span>
                    )}
                    {log.post_meal_weight_kg && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '.25rem' }}>
                        <Weight size={12}/> Post-Meal: {log.post_meal_weight_kg} kg
                      </span>
                    )}
                  </div>

                  {/* Macro row (always shown) */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.3rem', marginBottom: '.4rem' }}>
                    {/* Top 4 inline first */}
                    {['calories','protein_g','carbs_g','fat_g'].map(k => {
                      const p = MACRO_PILLS.find(p => p.key === k);
                      const v = log[k];
                      return (
                        <span key={k} style={{ fontSize: '.72rem', fontFamily: 'monospace', padding: '.15rem .4rem',
                          borderRadius: 4, background: pillColor(p, v), color: 'var(--color-text-primary)' }}>
                          {pillText(p, v)}
                        </span>
                      );
                    })}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.3rem' }}>
                    {MACRO_PILLS.filter(p => !['calories','protein_g','carbs_g','fat_g'].includes(p.key)).map(pill => {
                      const v = log[pill.key];
                      return (
                        <span key={pill.key} style={{ fontSize: '.7rem', fontFamily: 'monospace', padding: '.12rem .35rem',
                          borderRadius: 4, background: pillColor(pill, v), color: 'var(--color-text-secondary)' }}>
                          {pillText(pill, v)}
                        </span>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

