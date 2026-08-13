import { localToday } from '../utils/datetime';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import {
  ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Plus, BookOpen, Apple, Zap, Pill,
  CalendarDays, ExternalLink, Sparkles, Heart, FlaskConical, FileText, Activity, Bot,
  MessageSquareText, UtensilsCrossed, User, HeartPulse, Droplets, Share2, AlertTriangle,
  Globe, Loader2,
} from 'lucide-react';
import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from 'recharts';

/* ─── helpers ─── */
const todayStr = () => localToday();
const fmtDateLabel = (d) => new Date(d + 'T12:00:00').toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
const fmtTime = (t) => { if (!t) return ''; const [h, m] = t.split(':'); const hr = parseInt(h, 10); return `${String(hr % 12 || 12).padStart(2,'0')}:${m} ${hr < 12 ? 'AM' : 'PM'}`; };

function daysInMonth(y, mo) { return new Date(y, mo + 1, 0).getDate(); }
function calGrid(y, mo) {
  const first = new Date(y, mo, 1).getDay();
  const total = daysInMonth(y, mo);
  const rows = []; let d = 1 - first;
  for (let w = 0; w < 6; w++) {
    const row = [];
    for (let i = 0; i < 7; i++, d++) row.push(d >= 1 && d <= total ? d : null);
    if (row.some(x => x !== null)) rows.push(row);
  }
  return rows;
}

/* ─── mini calendar ─── */
function MiniCalendar({ selected, onChange, dotDates }) {
  const [view, setView] = useState(() => { const d = new Date(selected + 'T12:00:00'); return { y: d.getFullYear(), mo: d.getMonth() }; });
  const grid = useMemo(() => calGrid(view.y, view.mo), [view]);
  const label = new Date(view.y, view.mo).toLocaleString('default', { month: 'long', year: 'numeric' });
  const td = todayStr();

  function prev() { setView(v => v.mo === 0 ? { y: v.y - 1, mo: 11 } : { y: v.y, mo: v.mo - 1 }); }
  function next() { setView(v => v.mo === 11 ? { y: v.y + 1, mo: 0 } : { y: v.y, mo: v.mo + 1 }); }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '.75rem' }}>
        <button className="btn btn-secondary btn-sm" onClick={prev} style={{ padding: '4px 8px' }}><ChevronLeft size={14}/></button>
        <span style={{ fontWeight: 700, fontSize: '.9rem' }}>{label}</span>
        <button className="btn btn-secondary btn-sm" onClick={next} style={{ padding: '4px 8px' }}><ChevronRight size={14}/></button>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
        <thead>
          <tr>{['Su','Mo','Tu','We','Th','Fr','Sa'].map(d => (
            <th key={d} style={{ padding: '4px 0', textAlign: 'center', fontSize: '.72rem', color: 'var(--color-text-tertiary)' }}>{d}</th>
          ))}</tr>
        </thead>
        <tbody>
          {grid.map((row, ri) => (
            <tr key={ri}>
              {row.map((day, di) => {
                if (!day) return <td key={di}/>;
                const ds = `${view.y}-${String(view.mo+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
                const isSel = ds === selected;
                const isToday = ds === td;
                const hasDot = dotDates?.has(ds);
                return (
                  <td key={di} style={{ padding: '2px 0', textAlign: 'center', cursor: 'pointer' }} onClick={() => onChange(ds)}>
                    <div style={{ width: 30, height: 30, lineHeight: '30px', borderRadius: '50%', margin: '0 auto',
                      fontWeight: isToday ? 700 : 400, fontSize: '.85rem',
                      background: isSel ? 'var(--color-primary)' : isToday ? 'rgba(var(--color-primary-rgb),0.15)' : 'transparent',
                      color: isSel ? '#fff' : isToday ? 'var(--color-primary)' : 'inherit',
                      position: 'relative' }}>
                      {day}
                      {hasDot && !isSel && (
                        <span style={{ position: 'absolute', bottom: 2, left: '50%', transform: 'translateX(-50%)',
                          width: 4, height: 4, borderRadius: '50%', background: 'var(--color-primary)' }}/>
                      )}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ─── collapsible section ─── */
function Section({ icon: Icon, title, badge, children, link, linkLabel, onLink, defaultOpen = true, accentColor }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card" style={{ marginBottom: '.75rem', padding: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '.85rem 1rem',
        cursor: 'pointer', borderBottom: open ? '1px solid var(--color-border)' : 'none' }}
        onClick={() => setOpen(o => !o)}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
          {Icon && <Icon size={16} style={{ color: accentColor || 'var(--color-primary)' }}/>}
          <span style={{ fontWeight: 700, fontSize: '.95rem' }}>{title}</span>
          {badge != null && (
            <span style={{ fontSize: '.75rem', background: 'var(--color-bg-secondary)', borderRadius: 10,
              padding: '1px 8px', color: 'var(--color-text-secondary)' }}>{badge}</span>
          )}
        </div>
        {open ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
      </div>
      {open && (
        <div style={{ padding: '.85rem 1rem' }}>
          {children}
          {link && (
            <button className="btn btn-sm" onClick={e => { e.stopPropagation(); onLink(); }}
              style={{ marginTop: '.6rem', color: 'var(--color-primary)', background: 'none', border: 'none',
                padding: 0, display: 'flex', alignItems: 'center', gap: '.3rem', fontSize: '.82rem', cursor: 'pointer' }}>
              <ExternalLink size={12}/>{linkLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── overview: card chrome shared by the new sections ─── */
function OverviewCard({ icon: Icon, title, subtitle, children, style }) {
  return (
    <div className="card" style={{ marginBottom: '1rem', ...style }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: subtitle ? '.25rem' : '.75rem' }}>
        {Icon && <Icon size={20} style={{ color: 'var(--color-primary)', flexShrink: 0 }}/>}
        <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700 }}>{title}</h2>
      </div>
      {subtitle && (
        <p style={{ margin: '0 0 1rem 0', color: 'var(--color-text-secondary)', fontSize: '.9rem' }}>{subtitle}</p>
      )}
      {children}
    </div>
  );
}

/* ─── overview: current wellness score ─── */
function WellnessScoreCard() {
  const [score, setScore] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.get('/wellness/score')
      .then(({ data }) => setScore(data))
      .catch(() => setFailed(true));
  }, []);

  const value = score ? Math.round(score.overall_score) : null;
  return (
    <div className="card" style={{ marginBottom: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.75rem' }}>
        <Heart size={18} style={{ color: 'var(--color-primary)' }}/>
        <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700 }}>Current Wellness Score</h3>
      </div>
      {failed ? (
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '.85rem', margin: 0 }}>
          Score unavailable right now. <Link to="/wellness" style={{ color: 'var(--color-primary)' }}>Open Wellness Score</Link>
        </p>
      ) : value == null ? (
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '.85rem', margin: 0 }}>Calculating…</p>
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '.25rem' }}>
            <span style={{ fontSize: '3rem', fontWeight: 800, color: 'var(--color-primary)', lineHeight: 1.1 }}>{value}</span>
            <span style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--color-text-secondary)' }}>/100</span>
          </div>
          <div style={{ height: 8, borderRadius: 4, background: 'var(--color-border)', margin: '.75rem 0' }}>
            <div style={{ height: '100%', width: `${Math.min(100, Math.max(0, value))}%`, borderRadius: 4, background: 'var(--color-primary)' }}/>
          </div>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: '.82rem', margin: 0 }}>
            {score.explanation || 'Calculated from your recent nutrition, vitals, sleep, mood and medication data.'}
          </p>
        </>
      )}
    </div>
  );
}

/* ─── overview: latest lab results ─── */
function LatestLabsCard() {
  const navigate = useNavigate();
  const [labs, setLabs] = useState(null);

  useEffect(() => {
    api.get('/labs/')
      .then(({ data }) => setLabs(data))
      .catch(() => setLabs([]));
  }, []);

  /* labs come back ordered by test_date desc — the latest draw is the first date group */
  const latest = useMemo(() => {
    if (!labs?.length) return null;
    const d = labs[0].test_date;
    return { date: d, items: labs.filter(l => l.test_date === d) };
  }, [labs]);

  const fmtVal = (l) => l.value_string || (l.value != null ? `${l.value} ${l.unit || ''}`.trim() : '—');

  return (
    <div className="card" style={{ marginBottom: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
          <FlaskConical size={18} style={{ color: 'var(--color-primary)' }}/>
          <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700 }}>Latest Lab Results</h3>
        </div>
        <button onClick={() => navigate('/labs')}
          style={{ display: 'flex', alignItems: 'center', gap: '.3rem', background: 'none', border: 'none',
            color: 'var(--color-primary)', cursor: 'pointer', fontSize: '.85rem', padding: 0 }}>
          <FileText size={14}/> View All
        </button>
      </div>
      {labs == null ? (
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '.85rem', margin: 0 }}>Loading…</p>
      ) : !latest ? (
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '.85rem', margin: 0 }}>
          No lab results yet. <Link to="/labs" style={{ color: 'var(--color-primary)' }}>Add your first result</Link>
        </p>
      ) : (
        <>
          <div style={{ fontWeight: 700, fontSize: '.95rem' }}>Lab Draw Report</div>
          <div style={{ color: 'var(--color-text-secondary)', fontSize: '.8rem', marginBottom: '.6rem' }}>
            Date: {fmtDateLabel(latest.date)}
          </div>
          {latest.items.slice(0, 3).map(l => (
            <div key={l.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.88rem', padding: '.2rem 0' }}>
              <span>{l.test_name}:</span>
              <span style={{ fontWeight: 600 }}>{fmtVal(l)}</span>
            </div>
          ))}
          {latest.items.length > 3 && (
            <div style={{ fontStyle: 'italic', color: 'var(--color-text-secondary)', fontSize: '.8rem', marginTop: '.35rem' }}>
              …and {latest.items.length - 3} more.
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ─── overview: historical vitals trend (BP + HR, last 7 entries) ─── */
function VitalsTrendCard() {
  const [vitals, setVitals] = useState(null);

  useEffect(() => {
    api.get('/vitals/')
      .then(({ data }) => setVitals(data))
      .catch(() => setVitals([]));
  }, []);

  const chartData = useMemo(() => {
    if (!vitals?.length) return [];
    return vitals
      .filter(v => v.blood_pressure_systolic != null || v.heart_rate_bpm != null)
      .sort((a, b) => (a.log_date > b.log_date ? 1 : -1))
      .slice(-7)
      .map(v => ({
        date: new Date(v.log_date + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        systolic: v.blood_pressure_systolic,
        diastolic: v.blood_pressure_diastolic,
        heartRate: v.heart_rate_bpm,
      }));
  }, [vitals]);

  return (
    <OverviewCard icon={Activity} title="Historical Vitals Trend"
      subtitle={
        <>A quick look at your blood pressure and heart rate over the last 7 entries.{' '}
          <Link to="/chart-dashboard" style={{ color: 'var(--color-primary)' }}>View full trends page.</Link></>
      }>
      {vitals == null ? (
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '.85rem', margin: 0 }}>Loading…</p>
      ) : chartData.length === 0 ? (
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '.85rem', margin: 0 }}>
          No blood pressure or heart rate entries yet.{' '}
          <Link to="/vitals" style={{ color: 'var(--color-primary)' }}>Log your vitals</Link> to see the trend.
        </p>
      ) : (
        <div style={{ width: '100%', height: 320 }}>
          <ResponsiveContainer>
            <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)"/>
              <XAxis dataKey="date" stroke="var(--color-text-secondary)" fontSize={12}/>
              <YAxis yAxisId="bp" stroke="#2dd4bf" fontSize={12}
                domain={['dataMin - 5', 'dataMax + 5']}
                label={{ value: 'BP (mmHg)', angle: -90, position: 'insideLeft', fontSize: 11 }}/>
              <YAxis yAxisId="hr" orientation="right" stroke="var(--color-primary)" fontSize={12}
                domain={['dataMin - 10', 'dataMax + 10']}
                label={{ value: 'HR (bpm)', angle: 90, position: 'insideRight', fontSize: 11 }}/>
              <Tooltip contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 8 }}/>
              <Legend/>
              <Area yAxisId="bp" type="monotone" dataKey="systolic" name="Systolic" stroke="#2dd4bf" fill="#2dd4bf" fillOpacity={0.25}/>
              <Area yAxisId="bp" type="monotone" dataKey="diastolic" name="Diastolic" stroke="#eab308" fill="#eab308" fillOpacity={0.2}/>
              <Line yAxisId="hr" type="monotone" dataKey="heartRate" name="Heart Rate" stroke="var(--color-primary)" strokeWidth={2} dot={false}/>
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </OverviewCard>
  );
}

/* ─── overview: AI personalized recommendations ─── */
function RecommendationsCard() {
  const [notes, setNotes] = useState('');
  const [prefs, setPrefs] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function run() {
    setBusy(true); setError(null); setResult(null);
    const extra = [notes.trim() && `Supplementary journal notes: ${notes.trim()}`,
      prefs.trim() && `Preferences for today: ${prefs.trim()}`].filter(Boolean).join('\n');
    try {
      const { data } = await api.post('/personalization/recommendations', {
        type: 'wellness',
        specific_request: extra ? extra.slice(0, 500) : null,
      });
      setResult(data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not generate recommendations right now. Please try again later.');
    } finally {
      setBusy(false);
    }
  }

  const taStyle = { width: '100%', minHeight: 90, resize: 'vertical' };
  return (
    <OverviewCard icon={MessageSquareText} title="Alafia Personalized Recommendations"
      subtitle="Enter supplementary notes or preferences. Alafia will primarily use your latest profile, journal, nutrition, vitals, and lab data.">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginBottom: '.85rem' }}>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: '.88rem', marginBottom: '.35rem' }}>
            Supplementary Journal Notes (Optional)
          </label>
          <textarea className="form-input" style={taStyle} value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="e.g., Feeling particularly tired today, specific dietary craving…"/>
        </div>
        <div>
          <label style={{ display: 'block', fontWeight: 600, fontSize: '.88rem', marginBottom: '.35rem' }}>
            Personal Preferences for Today (Optional)
          </label>
          <textarea className="form-input" style={taStyle} value={prefs} onChange={e => setPrefs(e.target.value)}
            placeholder="e.g., prefer indoor activities, looking for quick meal ideas"/>
        </div>
      </div>
      <button className="btn btn-primary" onClick={run} disabled={busy}
        style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
        {busy && <Loader2 size={15} style={{ animation: 'spin-anim 1s linear infinite' }}/>}
        {busy ? 'Generating…' : 'Get Recommendations'}
      </button>
      {error && <p style={{ color: 'var(--color-danger)', fontSize: '.85rem', marginTop: '.75rem', marginBottom: 0 }}>{error}</p>}
      {result && (
        <div style={{ marginTop: '1rem', padding: '.85rem 1rem', borderRadius: 8, background: 'var(--color-bg)',
          border: '1px solid var(--color-border)', fontSize: '.88rem', whiteSpace: 'pre-wrap' }}>
          {result.recommendations}
        </div>
      )}
    </OverviewCard>
  );
}

/* ─── overview: AI health insights (experimental) ─── */
function InsightsCard() {
  const [symptoms, setSymptoms] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function run() {
    if (symptoms.trim().length < 10) {
      setError('Please describe your symptoms in a bit more detail (at least 10 characters).');
      return;
    }
    setBusy(true); setError(null); setResult(null);
    try {
      const { data } = await api.post('/personalization/analyze-symptoms', {
        symptoms_description: symptoms.trim().slice(0, 1000),
      });
      setResult(data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not analyze symptoms right now. Please try again later.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <OverviewCard icon={Sparkles} title="Alafia Health Insights (Experimental)"
      subtitle="Describe your current symptoms. Alafia will use your full health context (profile, journals, vitals, labs) to provide general insights. This is NOT a medical diagnosis.">
      <label style={{ display: 'block', fontWeight: 600, fontSize: '.88rem', marginBottom: '.35rem' }}>
        Describe your current symptoms
      </label>
      <textarea className="form-input" style={{ width: '100%', minHeight: 90, resize: 'vertical', marginBottom: '.85rem' }}
        value={symptoms} onChange={e => setSymptoms(e.target.value)}
        placeholder="e.g., I've had a persistent cough for 3 days, and a slight headache…"/>
      <button className="btn btn-primary" onClick={run} disabled={busy}
        style={{ display: 'flex', alignItems: 'center', gap: '.4rem' }}>
        {busy && <Loader2 size={15} style={{ animation: 'spin-anim 1s linear infinite' }}/>}
        {busy ? 'Analyzing…' : 'Get Alafia Insights'}
      </button>
      {error && <p style={{ color: 'var(--color-danger)', fontSize: '.85rem', marginTop: '.75rem', marginBottom: 0 }}>{error}</p>}
      {result && (
        <div style={{ marginTop: '1rem', padding: '.85rem 1rem', borderRadius: 8, background: 'var(--color-bg)',
          border: '1px solid var(--color-border)', fontSize: '.88rem', whiteSpace: 'pre-wrap' }}>
          {result.analysis}
          {result.disclaimer && (
            <p style={{ marginTop: '.75rem', marginBottom: 0, fontSize: '.78rem', fontStyle: 'italic',
              color: 'var(--color-text-secondary)' }}>{result.disclaimer}</p>
          )}
        </div>
      )}
    </OverviewCard>
  );
}

/* ─── overview: daily food idea (auto-generated, cached per day) ─── */
const FOOD_IDEA_KEY = 'alafia-daily-food-idea';

function DailyFoodIdeaCard() {
  const [state, setState] = useState({ status: 'loading', meal: null });

  useEffect(() => {
    const today = todayStr();
    try {
      const cached = JSON.parse(sessionStorage.getItem(FOOD_IDEA_KEY));
      if (cached?.date === today) {
        setState({ status: cached.meal ? 'ok' : 'error', meal: cached.meal });
        return;
      }
    } catch { /* ignore bad cache */ }

    let cancelled = false;
    api.post('/planners/meal-suggestions', { health_goals: '', count: 1 })
      .then(({ data }) => {
        if (cancelled) return;
        const meal = data.suggestions?.[0] || null;
        sessionStorage.setItem(FOOD_IDEA_KEY, JSON.stringify({ date: today, meal }));
        setState({ status: meal ? 'ok' : 'error', meal });
      })
      .catch(() => {
        if (cancelled) return;
        sessionStorage.setItem(FOOD_IDEA_KEY, JSON.stringify({ date: today, meal: null }));
        setState({ status: 'error', meal: null });
      });
    return () => { cancelled = true; };
  }, []);

  const { status, meal } = state;
  return (
    <OverviewCard icon={UtensilsCrossed} title="Daily Food Ideas"
      subtitle="An auto-generated meal suggestion based on your health data.">
      {status === 'loading' ? (
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '.9rem', margin: '0 0 .85rem 0' }}>
          Generating today's meal idea…
        </p>
      ) : status === 'error' ? (
        <p style={{ color: 'var(--color-text-secondary)', fontSize: '.95rem', margin: '0 0 .85rem 0' }}>
          Could not generate a meal idea. Try again later or visit the full planner.
        </p>
      ) : (
        <div style={{ marginBottom: '.85rem' }}>
          <div style={{ fontWeight: 700, fontSize: '1rem', textTransform: 'capitalize' }}>
            {meal.meal_type !== 'meal' ? `${meal.meal_type}: ` : ''}{meal.name}
          </div>
          {meal.description && (
            <p style={{ margin: '.35rem 0 0 0', fontSize: '.88rem', color: 'var(--color-text-secondary)' }}>{meal.description}</p>
          )}
          {meal.calories != null && (
            <p style={{ margin: '.35rem 0 0 0', fontSize: '.8rem', color: 'var(--color-text-secondary)' }}>
              ~{Math.round(meal.calories)} kcal
              {meal.protein_g != null && ` · ${Math.round(meal.protein_g)}g protein`}
              {meal.carbs_g != null && ` · ${Math.round(meal.carbs_g)}g carbs`}
              {meal.fat_g != null && ` · ${Math.round(meal.fat_g)}g fat`}
            </p>
          )}
        </div>
      )}
      <Link to="/meal-planner" style={{ color: 'var(--color-primary)', fontSize: '.9rem', fontWeight: 600 }}>
        Go to AI Meal Planner for more
      </Link>
    </OverviewCard>
  );
}

/* ─── overview: resources quick links ─── */
const RESOURCES = [
  { label: 'My Profile', to: '/profile', icon: User },
  { label: 'Chat with Alafia', to: '/ai', icon: Bot },
  { label: 'Health Journal', to: '/journal', icon: BookOpen },
  { label: 'Daily Vitals', to: '/vitals', icon: HeartPulse },
  { label: 'HD Flowsheet', to: '/hemodialysis', icon: Activity },
  { label: 'PD Report', to: '/peritoneal-dialysis', icon: Droplets },
  { label: 'Food & Meds Log', to: '/nutrition', icon: Apple },
  { label: 'Meals Diary', to: '/meals-diary', icon: UtensilsCrossed },
  { label: 'Lab Tests', to: '/labs', icon: FlaskConical },
  { label: 'Daily Calendar', to: '/calendar', icon: CalendarDays },
  { label: 'Food & Drug Recalls', to: '/fda-recalls', icon: AlertTriangle },
  { label: 'Connect Records', to: '/data-sharing', icon: Share2 },
  { label: 'CDC Health Info', href: 'https://www.cdc.gov/health-topics.html', icon: Globe },
  { label: 'WHO Wellness Tips', href: 'https://www.who.int/health-topics', icon: Globe },
];

function ResourceTile({ item }) {
  const navigate = useNavigate();
  const Icon = item.icon;
  const inner = (
    <>
      <div style={{ width: '100%', height: 100, borderRadius: 8, background: 'var(--color-bg)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '.6rem' }}>
        <Icon size={36} style={{ color: 'var(--color-primary)' }}/>
      </div>
      <div style={{ fontWeight: 600, fontSize: '.92rem', textAlign: 'center', display: 'flex',
        alignItems: 'center', justifyContent: 'center', gap: '.3rem' }}>
        {item.label}{item.href && <ExternalLink size={12} style={{ color: 'var(--color-text-secondary)' }}/>}
      </div>
    </>
  );
  const cardStyle = { cursor: 'pointer', textDecoration: 'none', color: 'inherit', display: 'block' };
  return item.href ? (
    <a className="card" style={cardStyle} href={item.href} target="_blank" rel="noopener noreferrer">{inner}</a>
  ) : (
    <div className="card" style={cardStyle} onClick={() => navigate(item.to)} role="link" tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter') navigate(item.to); }}>
      {inner}
    </div>
  );
}

function ResourcesSection() {
  return (
    <OverviewCard title="Resources" subtitle="Quick links to helpful sections and external resources.">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: '1rem' }}>
        {RESOURCES.map(item => <ResourceTile key={item.label} item={item}/>)}
      </div>
    </OverviewCard>
  );
}

/* ─── overview: page footer ─── */
function DashboardFooter() {
  return (
    <footer style={{ borderTop: '1px solid var(--color-border)', marginTop: '2rem', padding: '1.25rem 0 .5rem',
      display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '.75rem',
      color: 'var(--color-text-secondary)', fontSize: '.85rem' }}>
      <span>Alafia is a 6igma Health App.</span>
      <span style={{ display: 'flex', gap: '1.25rem' }}>
        {[
          ['About Us', '/landing'],
          ['Help', '/help'],
          ['Contact Us', '/contact'],
          ['Investors', '/investors'],
          ['Legal', '/landing'],
        ].map(([label, to]) => (
          <Link key={label} to={to} style={{ color: 'inherit' }}>{label}</Link>
        ))}
      </span>
    </footer>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
export default function Dashboard() {
  const navigate = useNavigate();
  const [selDate, setSelDate] = useState(todayStr);
  const [nutrition, setNutrition]   = useState([]);
  const [bowel, setBowel]           = useState([]);
  const [vomiting, setVomiting]     = useState([]);
  const [meds, setMeds]             = useState([]);
  const [events, setEvents]         = useState([]);
  const [mood, setMood]             = useState([]);
  /* dates that have any data — for calendar dots */
  const [dotDates, setDotDates]     = useState(new Set());

  /* load all data for selected date in parallel */
  const load = useCallback(async (d) => {
    const p = { start_date: d, end_date: d };
    const [n, b, v, mo, ev, me] = await Promise.allSettled([
      api.get('/nutrition/', { params: p }),
      api.get('/elimination/bowel', { params: p }),
      api.get('/elimination/vomiting', { params: p }),
      api.get('/mood/', { params: p }),
      api.get('/calendar/', { params: { ...p, limit: 100 } }),
      api.get('/medications/', { params: { limit: 200 } }),
    ]);
    setNutrition(n.status === 'fulfilled' ? n.value.data : []);
    setBowel(b.status === 'fulfilled' ? b.value.data : []);
    setVomiting(v.status === 'fulfilled' ? v.value.data : []);
    setMood(mo.status === 'fulfilled' ? mo.value.data : []);
    setEvents(ev.status === 'fulfilled' ? ev.value.data : []);
    /* medications: show those logged or active */
    if (me.status === 'fulfilled') {
      const medsData = me.value.data;
      /* show ones active on that date */
      const active = medsData.filter(m => m.is_active && (!m.end_date || m.end_date >= d));
      setMeds(active);
    }
  }, []);

  /* load dot dates for the visible month (all nutrition entries) */
  const loadDotDates = useCallback(async () => {
    const today = todayStr();
    const [y, mo] = today.split('-').map(Number);
    const start = `${y}-${String(mo).padStart(2,'0')}-01`;
    const end = today;
    try {
      const { data } = await api.get('/nutrition/', { params: { start_date: start, end_date: end, limit: 1000 } });
      setDotDates(new Set(data.map(n => n.log_date)));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(selDate); }, [load, selDate]);
  useEffect(() => { loadDotDates(); }, [loadDotDates]);

  /* group nutrition by meal_type */
  const mealGroups = useMemo(() => {
    const order = ['breakfast', 'lunch', 'dinner', 'snack', 'other'];
    const g = {};
    nutrition.forEach(n => {
      const k = (n.meal_type || 'other').toLowerCase();
      (g[k] = g[k] || []).push(n);
    });
    return order.filter(k => g[k]).map(k => ({ type: k, items: g[k] }));
  }, [nutrition]);

  /* combine elimination events */
  const elimEvents = useMemo(() => [
    ...bowel.map(e => ({ type: 'Bowel', time: e.time || e.log_date, note: e.stool_type || e.notes || '', ...e })),
    ...vomiting.map(e => ({ type: 'Vomiting', time: e.time || e.log_date, note: e.contents || e.notes || '', ...e })),
  ].sort((a, b) => (a.time > b.time ? 1 : -1)), [bowel, vomiting]);

  const mealEmoji = { breakfast: '🌅', lunch: '☀️', dinner: '🌙', snack: '🍎', other: '🍽️' };
  const noData = (text) => <p style={{ color: 'var(--color-text-tertiary)', fontSize: '.85rem', margin: 0 }}>{text}</p>;

  return (
    <div>

      {/* ═══ Health overview (Alafia dashboard) ═══ */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem' }}>
          <Sparkles size={28} style={{ color: 'var(--color-primary)' }}/>
          <h1 style={{ margin: 0, fontSize: '2rem', fontWeight: 800 }}>Health Dashboard</h1>
        </div>
        <p style={{ margin: '.35rem 0 0 0', color: 'var(--color-text-secondary)', fontSize: '1rem' }}>
          Your personal health overview and Alafia-powered insights.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
        <WellnessScoreCard/>
        <LatestLabsCard/>
      </div>
      <VitalsTrendCard/>
      <RecommendationsCard/>
      <InsightsCard/>
      <DailyFoodIdeaCard/>

      {/* ═══ Daily review (calendar + logged data) ═══ */}
      <h2 style={{ margin: '2rem 0 1rem 0', fontSize: '1.25rem', fontWeight: 700 }}>Daily Review</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '1.25rem', alignItems: 'start' }}>

      {/* ── LEFT: Calendar ── */}
      <div className="card" style={{ position: 'sticky', top: '1rem' }}>
        <h3 style={{ margin: '0 0 .75rem 0', fontSize: '.9rem', fontWeight: 700, color: 'var(--color-text-secondary)',
          textTransform: 'uppercase', letterSpacing: '.05em' }}>Select Date</h3>
        <MiniCalendar selected={selDate} onChange={setSelDate} dotDates={dotDates}/>
        <div style={{ marginTop: '1rem', paddingTop: '.75rem', borderTop: '1px solid var(--color-border)',
          fontSize: '.8rem', color: 'var(--color-text-secondary)', textAlign: 'center' }}>
          {fmtDateLabel(selDate)}
        </div>
      </div>

      {/* ── RIGHT: Daily sections ── */}
      <div>

        {/* Journal */}
        <Section icon={BookOpen} title={`Journal for ${fmtDateLabel(selDate)}`} accentColor="#8b5cf6">
          {mood.length > 0
            ? mood.map(m => (
                <div key={m.id} style={{ marginBottom: '.5rem' }}>
                  {m.notes && <p style={{ margin: 0, fontSize: '.88rem' }}>{m.notes}</p>}
                  {m.mood_score != null && (
                    <span style={{ fontSize: '.75rem', color: 'var(--color-text-secondary)' }}>
                      Mood score: {m.mood_score}/10
                    </span>
                  )}
                </div>
              ))
            : noData('No journal entry found for this date.')}
        </Section>

        {/* Meals & Nutrition */}
        <Section icon={Apple} title="Meals & Nutrition"
          badge={nutrition.length ? `Daily Totals (${nutrition.length} item${nutrition.length > 1 ? 's' : ''})` : null}
          link={true} linkLabel="View Full Meals Diary" onLink={() => navigate('/meals-diary')}
          accentColor="#10b981">
          {nutrition.length === 0
            ? noData('No meals logged for this date.')
            : mealGroups.map(g => (
                <div key={g.type} style={{ marginBottom: '.6rem' }}>
                  <div style={{ fontWeight: 600, fontSize: '.82rem', color: 'var(--color-text-secondary)',
                    textTransform: 'capitalize', marginBottom: '.25rem' }}>
                    {mealEmoji[g.type]} {g.type}:
                  </div>
                  {g.items.map(item => (
                    <div key={item.id} style={{ fontSize: '.85rem', padding: '.2rem 0 .2rem .75rem',
                      borderLeft: '2px solid var(--color-border)', marginBottom: '.2rem',
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ flex: 1 }}>{item.food_name}</span>
                      {item.calories > 0 && (
                        <span style={{ fontSize: '.75rem', color: 'var(--color-text-tertiary)',
                          fontFamily: 'monospace', marginLeft: '.5rem' }}>
                          {Math.round(item.calories)} kcal
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ))}
        </Section>

        {/* General Activities & Events (Elimination) */}
        <Section icon={Zap} title="General Activities & Events"
          link={elimEvents.length > 0} linkLabel="View Full Elimination Log"
          onLink={() => navigate('/elimination')} accentColor="#f59e0b">
          {elimEvents.length === 0
            ? noData('No elimination events logged for this date.')
            : (
              <div>
                <div style={{ fontWeight: 600, fontSize: '.82rem', color: 'var(--color-text-secondary)', marginBottom: '.35rem' }}>
                  Elimination Events:
                </div>
                {elimEvents.map((e, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: '.4rem',
                    fontSize: '.85rem', marginBottom: '.3rem', paddingLeft: '.5rem' }}>
                    <span style={{ color: 'var(--color-text-secondary)', minWidth: 24 }}>•</span>
                    <span>
                      <strong>{e.type}</strong>
                      {e.time && <span style={{ color: 'var(--color-text-tertiary)' }}> at {fmtTime(typeof e.time === 'string' && e.time.length <= 8 ? e.time : new Date(e.time).toTimeString().slice(0,5))}</span>}
                      {e.note && <span style={{ fontStyle: 'italic', color: 'var(--color-text-tertiary)' }}> — {e.note}</span>}
                    </span>
                  </div>
                ))}
              </div>
            )}
        </Section>

        {/* Medications Taken */}
        <Section icon={Pill} title="Medications Taken" accentColor="#ef4444">
          {meds.length === 0
            ? noData('No medications logged for this date.')
            : (
              <div>
                {meds.slice(0, 5).map(m => (
                  <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between',
                    fontSize: '.85rem', padding: '.3rem 0', borderBottom: '1px solid var(--color-border)' }}>
                    <span>{m.name || m.medication_name}</span>
                    <span style={{ color: 'var(--color-text-secondary)', fontSize: '.78rem' }}>
                      {m.dosage || ''} {m.unit || ''}
                    </span>
                  </div>
                ))}
                {meds.length > 5 && (
                  <p style={{ fontSize: '.78rem', color: 'var(--color-text-tertiary)', marginTop: '.5rem', marginBottom: 0 }}>
                    +{meds.length - 5} more
                  </p>
                )}
              </div>
            )}
        </Section>

        {/* Schedules & Appointments */}
        <Section icon={CalendarDays} title="Schedules & Appointments"
          accentColor="#3b82f6"
          badge={
            <button className="btn btn-primary btn-sm"
              onClick={e => { e.stopPropagation(); navigate('/calendar'); }}
              style={{ padding: '3px 10px', fontSize: '.75rem', display: 'flex', alignItems: 'center', gap: '.3rem' }}>
              <Plus size={12}/> Add New
            </button>
          }>
          {events.length === 0
            ? noData('No appointments or events for this date.')
            : events.map(ev => (
                <div key={ev.id} style={{ display: 'flex', alignItems: 'center', gap: '.5rem',
                  padding: '.35rem 0', borderBottom: '1px solid var(--color-border)', fontSize: '.85rem' }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: ev.color || '#3b82f6',
                    flexShrink: 0 }}/>
                  <span style={{ flex: 1 }}>{ev.title}</span>
                  {ev.start_time && (
                    <span style={{ fontSize: '.75rem', color: 'var(--color-text-tertiary)', fontFamily: 'monospace' }}>
                      {fmtTime(ev.start_time.slice(0,5))}
                    </span>
                  )}
                </div>
              ))}
        </Section>

      </div>
      </div>

      <ResourcesSection/>
      <DashboardFooter/>
    </div>
  );
}
