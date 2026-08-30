import { useState, useEffect } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import api from '../services/api';
import {
  Heart,
  TrendingUp,
  TrendingDown,
  Minus,
  Lightbulb,
  Award,
  Loader2,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Star,
  Utensils,
  Dumbbell,
  Moon,
  Smile,
  Stethoscope,
  Pill,
  Activity,
  FlaskConical,
  Sliders,
  ArrowUpRight,
  ArrowDownRight,
  Minus as MinusIcon,
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import BackButton from '../components/BackButton';

const TABS = [
  { key: 'score', label: 'Score', icon: Star },
  { key: 'omega', label: 'HEBCS Ω', icon: FlaskConical },
  { key: 'trends', label: 'Trends', icon: TrendingUp },
  { key: 'recommendations', label: 'Recs', icon: Lightbulb },
  { key: 'improvements', label: 'Improve', icon: Award },
];

const SUB_SCORE_META = {
  nutrition_score: { label: 'Nutrition', color: '#10b981', icon: Utensils },
  fitness_score: { label: 'Fitness', color: '#3b82f6', icon: Dumbbell },
  sleep_score: { label: 'Sleep', color: '#8b5cf6', icon: Moon },
  mood_score: { label: 'Mood', color: '#f59e0b', icon: Smile },
  vitals_score: { label: 'Vitals', color: '#ef4444', icon: Activity },
  medication_adherence_score: { label: 'Medication', color: '#ec4899', icon: Pill },
};

const PRIORITY_COLORS = {
  high: { bg: '#fef2f2', text: '#dc2626', border: '#fecaca' },
  medium: { bg: '#fffbeb', text: '#d97706', border: '#fde68a' },
  low: { bg: '#f0fdf4', text: '#16a34a', border: '#bbf7d0' },
};

const TREND_COLORS = {
  improving: { bg: '#f0fdf4', text: '#16a34a', icon: TrendingUp },
  stable: { bg: '#f3f4f6', text: '#6b7280', icon: Minus },
  declining: { bg: '#fef2f2', text: '#dc2626', icon: TrendingDown },
};

const STREAM_COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6'];

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function scoreColor(score) {
  if (score >= 70) return '#10b981';
  if (score >= 40) return '#f59e0b';
  return '#ef4444';
}

function CircularScore({ score, size = 160, strokeWidth = 12 }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(Math.max(score || 0, 0), 100);
  const offset = circumference - (progress / 100) * circumference;
  const color = scoreColor(score);

  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#f3f4f6"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.8s ease' }}
        />
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span style={{ fontSize: 36, fontWeight: 800, color }}>{Math.round(score || 0)}</span>
        <span style={{ fontSize: 12, color: '#9ca3af', marginTop: -2 }}>out of 100</span>
      </div>
    </div>
  );
}

function ProgressBar({ value, color, label, icon: Icon }) {
  const pct = Math.min(Math.max(value || 0, 0), 100);
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#374151', fontWeight: 500 }}>
          {Icon && <Icon size={14} style={{ color }} />}
          {label}
        </span>
        <span style={{ fontSize: 13, fontWeight: 600, color }}>{Math.round(pct)}</span>
      </div>
      <div style={{ height: 8, borderRadius: 4, background: '#f3f4f6', overflow: 'hidden' }}>
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            background: color,
            borderRadius: 4,
            transition: 'width 0.6s ease',
          }}
        />
      </div>
    </div>
  );
}

function MiniTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, padding: '6px 10px', fontSize: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}>
      <p style={{ margin: 0, color: '#6b7280' }}>{label}</p>
      <p style={{ margin: '2px 0 0', fontWeight: 600, color: '#1f2937' }}>{payload[0].value}</p>
    </div>
  );
}

function LoadingState({ message }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 60, gap: 10 }}>
      <Loader2 size={22} style={{ color: 'var(--color-primary)', animation: 'spin 1s linear infinite' }} />
      <span style={{ color: '#6b7280', fontSize: 14 }}>{message || 'Loading…'}</span>
    </div>
  );
}

function ErrorState({ message, onRetry }) {
  return (
    <div className="card" style={{ display: 'flex', alignItems: 'center', gap: 12, background: '#fef2f2', borderColor: '#fee2e2' }}>
      <AlertCircle size={20} style={{ color: 'var(--color-danger)', flexShrink: 0 }} />
      <p style={{ margin: 0, color: '#b91c1c', fontSize: 14, flex: 1 }}>{message}</p>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

/* ============================================================
   SCORE TAB
   ============================================================ */
function ScoreTab() {
  const [score, setScore] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    try {
      setLoading(true);
      setError(null);
      const [scoreRes, histRes] = await Promise.all([
        api.get('/wellness/score'),
        api.get('/wellness/score/history', { params: { days: 30 } }),
      ]);
      setScore(scoreRes.data);
      setHistory(
        (Array.isArray(histRes.data) ? histRes.data : []).map((d) => ({
          ...d,
          _date: formatDate(d.score_date || d.date),
        }))
      );
    } catch (err) {
      console.error('Failed to load wellness score:', err);
      setError(apiErrorMessage(err, 'Failed to load wellness score.'));
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <LoadingState message="Loading wellness score…" />;
  if (error) return <ErrorState message={error} onRetry={fetchData} />;
  if (!score) return <p style={{ color: '#9ca3af', textAlign: 'center', padding: 32 }}>No score data available.</p>;

  return (
    <div>
      {/* Overall score */}
      <div className="card" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 32, marginBottom: 20 }}>
        {/* null means nothing could be measured — not a score of zero. */}
        {score.overall_score == null ? (
          <div style={{ minWidth: 140, textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
            Not enough<br/>data to score
          </div>
        ) : (
          <CircularScore score={score.overall_score} />
        )}
        <div style={{ flex: 1, minWidth: 240 }}>
          <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 700, color: '#1f2937' }}>
            Overall Wellness Score
          </h3>
          {score.score_date && (
            <p style={{ margin: '0 0 16px', fontSize: 13, color: '#9ca3af' }}>
              as of {new Date(score.score_date).toLocaleDateString()}
            </p>
          )}

          {Object.entries(SUB_SCORE_META).map(([key, meta]) => {
            const val = score[key];
            if (val == null) return null;
            return <ProgressBar key={key} value={val} color={meta.color} label={meta.label} icon={meta.icon} />;
          })}
        </div>
      </div>

      {/* Explanation */}
      {score.explanation && (
        <div className="card" style={{ marginBottom: 20 }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 14, fontWeight: 600, color: '#374151' }}>Analysis</h4>
          <p style={{ margin: 0, fontSize: 14, color: '#4b5563', lineHeight: 1.6 }}>{score.explanation}</p>
        </div>
      )}

      {/* Score history */}
      {history.length > 0 && (
        <div className="card">
          <h4 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 600, color: '#374151' }}>
            Score History (Last 30 Days)
          </h4>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={history} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="_date" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} />
              <Tooltip content={<MiniTooltip />} />
              <Line
                type="monotone"
                dataKey="overall_score"
                stroke="#10b981"
                strokeWidth={2}
                dot={{ r: 3, fill: '#fff', strokeWidth: 2 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   HEBCS Ω TAB  (trapezoidal pathway scoring + What-If simulator)
   ============================================================ */

const PATHWAY_COLORS = {
  Metabolic: '#10b981',
  Hematologic: '#ef4444',
  Bone_Mineral: '#f59e0b',
  Cardiovascular: '#3b82f6',
  Nutritional: '#8b5cf6',
  Dialysis_Adequacy: '#06b6d4',
  Inflammatory: '#ec4899',
};

const WHATIF_INPUTS = [
  { field: 'Phosphorus',        label: 'Phosphorus',    unit: 'mg/dL', min: 1.5,  max: 9.0,  step: 0.1, pathway: 'Bone_Mineral' },
  { field: 'Potassium',         label: 'Potassium',     unit: 'mEq/L',min: 2.5,  max: 7.0,  step: 0.1, pathway: 'Metabolic' },
  { field: 'Albumin',           label: 'Albumin',       unit: 'g/dL', min: 1.5,  max: 5.5,  step: 0.1, pathway: 'Nutritional' },
  { field: 'Hemoglobin',        label: 'Hemoglobin',    unit: 'g/dL', min: 6.0,  max: 18.0, step: 0.1, pathway: 'Hematologic' },
  { field: 'Ferritin',          label: 'Ferritin',      unit: 'µg/L', min: 10,   max: 2000, step: 10,  pathway: 'Hematologic' },
  { field: 'KtV_Dialysis_Adequacy', label: 'KtV',      unit: '',     min: 0.5,  max: 2.5,  step: 0.05, pathway: 'Dialysis_Adequacy' },
  { field: 'PTH_Intact',        label: 'PTH',           unit: 'pg/mL',min: 15,   max: 2000, step: 10,  pathway: 'Bone_Mineral' },
  { field: 'Calcium',           label: 'Calcium',       unit: 'mg/dL',min: 6.5,  max: 12.0, step: 0.1, pathway: 'Bone_Mineral' },
];

function OmegaGauge({ omega, size = 180 }) {
  const pct = Math.max(0.001, Math.min(0.999, omega || 0.5));
  const radius = (size - 16) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - pct * circumference;
  const color = pct >= 0.65 ? '#10b981' : pct >= 0.45 ? '#f59e0b' : '#ef4444';
  const label = pct >= 0.65 ? 'Good' : pct >= 0.45 ? 'Moderate' : 'Critical';
  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={radius} fill="none" stroke="#f3f4f6" strokeWidth={14} />
        <circle cx={size/2} cy={size/2} r={radius} fill="none" stroke={color} strokeWidth={14}
          strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.8s ease, stroke 0.4s ease' }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: 32, fontWeight: 800, color }}>Ω {(pct).toFixed(3)}</span>
        <span style={{ fontSize: 12, color: '#9ca3af', marginTop: -2 }}>{label}</span>
      </div>
    </div>
  );
}

function PathwayBar({ name, score, weight }) {
  const color = PATHWAY_COLORS[name] || '#6b7280';
  const pct = score != null ? Math.round(score * 100) : null;
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 13, fontWeight: 500, color: '#374151' }}>
          {name.replace('_', ' ')}
          <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 6 }}>w={weight}</span>
        </span>
        <span style={{ fontSize: 13, fontWeight: 700, color: pct != null ? color : '#9ca3af' }}>
          {pct != null ? `${pct}%` : 'N/A'}
        </span>
      </div>
      <div style={{ height: 8, borderRadius: 4, background: '#f3f4f6', overflow: 'hidden' }}>
        {pct != null && (
          <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 4, transition: 'width 0.6s ease' }} />
        )}
      </div>
    </div>
  );
}

function HEBCSTab() {
  const [omega, setOmega] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // What-If state
  const [wiValues, setWiValues] = useState({});
  const [wiEnabled, setWiEnabled] = useState({});
  const [wiResult, setWiResult] = useState(null);
  const [wiRunning, setWiRunning] = useState(false);
  const [wiError, setWiError] = useState(null);

  useEffect(() => { fetchOmega(); }, []);

  async function fetchOmega() {
    try {
      setLoading(true); setError(null);
      const res = await api.get('/wellness/omega');
      setOmega(res.data);
      // Seed what-if sliders from current real lab values
      const seeds = {};
      const pathways = res.data.pathways || {};
      Object.values(pathways).forEach(pw => {
        (pw.biomarkers || []).forEach(b => {
          WHATIF_INPUTS.forEach(wi => {
            if (b.name === wi.label || b.name.startsWith(wi.label)) {
              if (b.value != null) seeds[wi.field] = b.value;
            }
          });
        });
      });
      setWiValues(prev => ({ ...seeds, ...prev }));
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to load HEBCS Ω score.'));
    } finally { setLoading(false); }
  }

  async function runWhatIf() {
    const payload = { scenario_name: 'custom' };
    WHATIF_INPUTS.forEach(wi => {
      if (wiEnabled[wi.field] && wiValues[wi.field] != null) {
        payload[wi.field] = parseFloat(wiValues[wi.field]);
      }
    });
    try {
      setWiRunning(true); setWiError(null);
      const res = await api.post('/wellness/whatif', payload);
      setWiResult(res.data);
    } catch (err) {
      setWiError(apiErrorMessage(err, 'What-If failed.'));
    } finally { setWiRunning(false); }
  }

  const activeOverrides = WHATIF_INPUTS.filter(wi => wiEnabled[wi.field]).length;

  if (loading) return <LoadingState message="Computing HEBCS Ω…" />;
  if (error) return <ErrorState message={error} onRetry={fetchOmega} />;
  if (!omega) return null;

  const pathways = omega.pathways || {};
  const covPct = Math.round((omega.data_coverage || 0) * 100);

  return (
    <div>
      {/* Omega gauge + meta */}
      <div className="card" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 28, marginBottom: 20 }}>
        <OmegaGauge omega={omega.omega} />
        <div style={{ flex: 1, minWidth: 220 }}>
          <h3 style={{ margin: '0 0 6px', fontSize: 18, fontWeight: 700, color: '#1f2937' }}>
            HEBCS Wellness Score
          </h3>
          <p style={{ margin: '0 0 4px', fontSize: 13, color: '#6b7280' }}>
            7-pathway trapezoidal scoring (J-BHI 2026)
          </p>
          {omega.lab_date_used && (
            <p style={{ margin: '0 0 12px', fontSize: 12, color: '#9ca3af' }}>
              Latest labs: {new Date(omega.lab_date_used).toLocaleDateString()}
            </p>
          )}
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#3b82f6' }}>{Math.round(omega.omega_pct)}%</div>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>Score (0–100)</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: covPct >= 60 ? '#10b981' : '#f59e0b' }}>{covPct}%</div>
              <div style={{ fontSize: 11, color: '#9ca3af' }}>Data coverage</div>
            </div>
          </div>
        </div>
      </div>

      {/* Interpretation */}
      {omega.interpretation && (
        <div className="card" style={{ marginBottom: 20, background: '#f0fdf4', borderColor: '#bbf7d0' }}>
          <p style={{ margin: 0, fontSize: 14, color: '#15803d', lineHeight: 1.6 }}>{omega.interpretation}</p>
        </div>
      )}

      {/* Pathway breakdown */}
      <div className="card" style={{ marginBottom: 20 }}>
        <h4 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 600, color: '#374151' }}>
          <FlaskConical size={15} style={{ marginRight: 6, verticalAlign: -2, color: '#3b82f6' }} />
          Pathway Breakdown
        </h4>
        {Object.entries(pathways).map(([name, pw]) => (
          <PathwayBar key={name} name={name} score={pw.score} weight={pw.weight} />
        ))}
      </div>

      {/* What-If simulator */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <Sliders size={16} style={{ color: '#8b5cf6' }} />
          <h4 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: '#374151' }}>What-If Simulator</h4>
        </div>
        <p style={{ margin: '0 0 18px', fontSize: 13, color: '#6b7280' }}>
          Enable sliders for any biomarkers you want to adjust, then run the simulation to see the projected Ω impact.
        </p>

        {WHATIF_INPUTS.map(wi => {
          const enabled = !!wiEnabled[wi.field];
          const val = wiValues[wi.field] ?? ((wi.min + wi.max) / 2);
          const pathColor = PATHWAY_COLORS[wi.pathway] || '#6b7280';
          return (
            <div key={wi.field} style={{ marginBottom: 16, opacity: enabled ? 1 : 0.5, transition: 'opacity 0.2s' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={e => setWiEnabled(prev => ({ ...prev, [wi.field]: e.target.checked }))}
                  style={{ width: 16, height: 16, cursor: 'pointer', accentColor: pathColor }}
                />
                <span style={{ fontSize: 13, fontWeight: 500, color: '#374151', flex: 1 }}>
                  {wi.label}
                  <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 4 }}>{wi.unit}</span>
                </span>
                <span style={{
                  fontSize: 14, fontWeight: 700,
                  color: enabled ? pathColor : '#9ca3af',
                  minWidth: 60, textAlign: 'right',
                }}>
                  {typeof val === 'number' ? val.toFixed(wi.step < 1 ? 1 : 0) : '—'}
                </span>
              </div>
              {enabled && (
                <input
                  type="range"
                  min={wi.min} max={wi.max} step={wi.step}
                  value={val}
                  onChange={e => setWiValues(prev => ({ ...prev, [wi.field]: parseFloat(e.target.value) }))}
                  style={{ width: '100%', accentColor: pathColor }}
                />
              )}
            </div>
          );
        })}

        <button
          className="btn btn-primary"
          onClick={runWhatIf}
          disabled={wiRunning || activeOverrides === 0}
          style={{ width: '100%', marginTop: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
        >
          {wiRunning ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Sliders size={16} />}
          {wiRunning ? 'Simulating…' : `Run What-If${activeOverrides > 0 ? ` (${activeOverrides} change${activeOverrides > 1 ? 's' : ''})` : ''}`}
        </button>

        {wiError && <p style={{ fontSize: 13, color: '#dc2626', marginTop: 10 }}>{wiError}</p>}

        {/* What-If results */}
        {wiResult && (
          <div style={{ marginTop: 20, paddingTop: 20, borderTop: '1px solid #f3f4f6' }}>
            <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
              {[
                { label: 'Baseline Ω', value: wiResult.baseline_omega?.toFixed(3), color: '#6b7280' },
                { label: 'Scenario Ω', value: wiResult.scenario_omega?.toFixed(3), color: wiResult.delta_omega > 0 ? '#10b981' : wiResult.delta_omega < 0 ? '#ef4444' : '#6b7280' },
                {
                  label: 'Change',
                  value: wiResult.delta_pct != null ? `${wiResult.delta_pct > 0 ? '+' : ''}${wiResult.delta_pct.toFixed(1)}pp` : '—',
                  color: wiResult.delta_omega > 0 ? '#10b981' : wiResult.delta_omega < 0 ? '#ef4444' : '#6b7280',
                },
              ].map(item => (
                <div key={item.label} style={{ flex: 1, minWidth: 100, textAlign: 'center', padding: '12px 8px', background: '#f9fafb', borderRadius: 8 }}>
                  <div style={{ fontSize: 20, fontWeight: 800, color: item.color }}>{item.value}</div>
                  <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>{item.label}</div>
                </div>
              ))}
            </div>

            {/* Pathway deltas */}
            {Object.entries(wiResult.pathway_deltas || {}).map(([name, d]) => {
              if (d.delta == null) return null;
              const color = PATHWAY_COLORS[name] || '#6b7280';
              const DeltaIcon = d.delta > 0.005 ? ArrowUpRight : d.delta < -0.005 ? ArrowDownRight : MinusIcon;
              const deltaColor = d.delta > 0.005 ? '#10b981' : d.delta < -0.005 ? '#ef4444' : '#9ca3af';
              return (
                <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, padding: '8px 12px', background: '#f9fafb', borderRadius: 6 }}>
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0 }} />
                  <span style={{ fontSize: 13, color: '#374151', flex: 1 }}>{name.replace('_', ' ')}</span>
                  <span style={{ fontSize: 12, color: '#9ca3af' }}>{d.baseline_score != null ? `${Math.round(d.baseline_score * 100)}%` : '—'}</span>
                  <DeltaIcon size={14} style={{ color: deltaColor }} />
                  <span style={{ fontSize: 12, color: '#9ca3af' }}>{d.scenario_score != null ? `${Math.round(d.scenario_score * 100)}%` : '—'}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: deltaColor, minWidth: 48, textAlign: 'right' }}>
                    {d.delta > 0 ? '+' : ''}{(d.delta * 100).toFixed(1)}pp
                  </span>
                </div>
              );
            })}

            {wiResult.interpretation && (
              <p style={{ margin: '14px 0 0', fontSize: 13, color: '#4b5563', lineHeight: 1.6, fontStyle: 'italic' }}>
                {wiResult.interpretation}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ============================================================
   TRENDS TAB
   ============================================================ */
function TrendsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get('/wellness/trends', { params: { days: 90 } });
      setData(res.data);
    } catch (err) {
      console.error('Failed to load wellness trends:', err);
      setError(apiErrorMessage(err, 'Failed to load trends.'));
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <LoadingState message="Loading trends…" />;
  if (error) return <ErrorState message={error} onRetry={fetchData} />;
  if (!data) return <p style={{ color: '#9ca3af', textAlign: 'center', padding: 32 }}>No trend data available.</p>;

  const streams = data.streams || [];

  return (
    <div>
      {/* Overall summary */}
      {data.overall_summary && (
        <div className="card" style={{ marginBottom: 20 }}>
          <p style={{ margin: 0, fontSize: 14, color: '#4b5563', lineHeight: 1.6 }}>{data.overall_summary}</p>
        </div>
      )}

      {/* Stream charts */}
      {streams.map((stream, idx) => {
        const trendInfo = TREND_COLORS[stream.trend] || TREND_COLORS.stable;
        const TrendIcon = trendInfo.icon;
        const chartData = (stream.data || []).map((d) => ({
          ...d,
          _date: formatDate(d.date),
        }));
        const color = STREAM_COLORS[idx % STREAM_COLORS.length];

        return (
          <div className="card" key={stream.name || idx} style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
              <h4 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: '#1f2937', flex: 1 }}>
                {stream.name}
              </h4>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  padding: '3px 10px',
                  borderRadius: 12,
                  background: trendInfo.bg,
                  color: trendInfo.text,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  textTransform: 'capitalize',
                }}
              >
                <TrendIcon size={13} />
                {stream.trend || 'stable'}
              </span>
            </div>
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="_date" tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} tickLine={false} />
                  <Tooltip content={<MiniTooltip />} />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke={color}
                    strokeWidth={2}
                    dot={{ r: 3, fill: '#fff', strokeWidth: 2 }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p style={{ color: '#9ca3af', fontSize: 13, textAlign: 'center', padding: 20 }}>
                No data points
              </p>
            )}
          </div>
        );
      })}

      {/* Correlations */}
      {data.correlations && data.correlations.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h4 style={{ margin: '0 0 10px', fontSize: 14, fontWeight: 600, color: '#374151' }}>Correlations</h4>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {data.correlations.map((c, i) => (
              <li key={i} style={{ fontSize: 14, color: '#4b5563', marginBottom: 6, lineHeight: 1.5 }}>
                {typeof c === 'string' ? c : c.description || JSON.stringify(c)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Suggestions */}
      {data.suggestions && data.suggestions.length > 0 && (
        <div className="card">
          <h4 style={{ margin: '0 0 10px', fontSize: 14, fontWeight: 600, color: '#374151' }}>
            <Lightbulb size={15} style={{ marginRight: 6, verticalAlign: -2, color: '#f59e0b' }} />
            Suggestions
          </h4>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {data.suggestions.map((s, i) => (
              <li key={i} style={{ fontSize: 14, color: '#4b5563', marginBottom: 6, lineHeight: 1.5 }}>
                {typeof s === 'string' ? s : s.text || s.description || JSON.stringify(s)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   RECOMMENDATIONS TAB
   ============================================================ */
function RecommendationsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get('/wellness/recommendations');
      setData(res.data);
    } catch (err) {
      console.error('Failed to load recommendations:', err);
      setError(apiErrorMessage(err, 'Failed to load recommendations.'));
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <LoadingState message="Loading recommendations…" />;
  if (error) return <ErrorState message={error} onRetry={fetchData} />;
  if (!data) return <p style={{ color: '#9ca3af', textAlign: 'center', padding: 32 }}>No recommendations available.</p>;

  // Gather all recommendation items – combine the general list with named category arrays
  const allRecs = [];
  if (data.recommendations) allRecs.push(...data.recommendations);
  ['nutrition', 'fitness', 'sleep', 'mood', 'medical', 'medication'].forEach((cat) => {
    if (Array.isArray(data[cat])) {
      data[cat].forEach((r) => allRecs.push({ ...r, category: r.category || cat }));
    }
  });

  // Group by category
  const grouped = {};
  allRecs.forEach((r) => {
    const cat = r.category || 'General';
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(r);
  });

  const CATEGORY_COLORS = {
    nutrition: '#10b981',
    fitness: '#3b82f6',
    sleep: '#8b5cf6',
    mood: '#f59e0b',
    medical: '#ef4444',
    medication: '#ec4899',
    general: '#6b7280',
  };

  return (
    <div>
      {data.date && (
        <p style={{ fontSize: 13, color: '#9ca3af', marginBottom: 16 }}>
          Generated on {new Date(data.date).toLocaleDateString()}
        </p>
      )}

      {Object.keys(grouped).length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: 40 }}>
          <Lightbulb size={36} style={{ color: '#d1d5db', marginBottom: 10 }} />
          <p style={{ margin: 0, color: '#6b7280' }}>No recommendations at this time.</p>
        </div>
      )}

      {Object.entries(grouped).map(([category, items]) => {
        const catColor = CATEGORY_COLORS[category.toLowerCase()] || '#6b7280';
        return (
          <div key={category} style={{ marginBottom: 24 }}>
            <h3
              style={{
                fontSize: 15,
                fontWeight: 700,
                color: catColor,
                textTransform: 'capitalize',
                margin: '0 0 12px',
                paddingBottom: 6,
                borderBottom: `2px solid ${catColor}22`,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              {category}
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 500,
                  background: `${catColor}15`,
                  color: catColor,
                  padding: '1px 8px',
                  borderRadius: 10,
                }}
              >
                {items.length}
              </span>
            </h3>

            <div className="card-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
              {items.map((rec, i) => {
                const pri = PRIORITY_COLORS[rec.priority?.toLowerCase()] || PRIORITY_COLORS.low;
                return (
                  <div
                    className="card"
                    key={i}
                    style={{ padding: '14px 18px', borderLeft: `3px solid ${catColor}` }}
                  >
                    <div style={{ display: 'flex', alignItems: 'start', justifyContent: 'space-between', gap: 8 }}>
                      <h4 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: '#1f2937' }}>
                        {rec.title || rec.action || 'Recommendation'}
                      </h4>
                      {rec.priority && (
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 600,
                            padding: '2px 8px',
                            borderRadius: 10,
                            background: pri.bg,
                            color: pri.text,
                            border: `1px solid ${pri.border}`,
                            textTransform: 'capitalize',
                            whiteSpace: 'nowrap',
                            flexShrink: 0,
                          }}
                        >
                          {rec.priority}
                        </span>
                      )}
                    </div>
                    {rec.description && (
                      <p style={{ margin: '8px 0 0', fontSize: 13, color: '#6b7280', lineHeight: 1.5 }}>
                        {rec.description}
                      </p>
                    )}
                    {rec.action && rec.title && (
                      <p style={{ margin: '6px 0 0', fontSize: 13, color: 'var(--color-primary)', fontWeight: 500 }}>
                        → {rec.action}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ============================================================
   IMPROVEMENTS TAB
   ============================================================ */
const IMPROVEMENT_SECTIONS = [
  { key: 'nutrition_improvements', label: 'Nutrition', icon: Utensils, color: '#10b981' },
  { key: 'fitness_improvements', label: 'Fitness', icon: Dumbbell, color: '#3b82f6' },
  { key: 'sleep_improvements', label: 'Sleep', icon: Moon, color: '#8b5cf6' },
  { key: 'mood_improvements', label: 'Mood', icon: Smile, color: '#f59e0b' },
  { key: 'medical_improvements', label: 'Medical', icon: Stethoscope, color: '#ef4444' },
];

function ImprovementsTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get('/wellness/improvements');
      setData(res.data);
      // Expand all sections by default
      const expMap = {};
      IMPROVEMENT_SECTIONS.forEach((s) => {
        if (res.data[s.key] && res.data[s.key].length > 0) expMap[s.key] = true;
      });
      setExpanded(expMap);
    } catch (err) {
      console.error('Failed to load improvements:', err);
      setError(apiErrorMessage(err, 'Failed to load improvements.'));
    } finally {
      setLoading(false);
    }
  }

  function toggleSection(key) {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  if (loading) return <LoadingState message="Loading improvements…" />;
  if (error) return <ErrorState message={error} onRetry={fetchData} />;
  if (!data) return <p style={{ color: '#9ca3af', textAlign: 'center', padding: 32 }}>No improvement data available.</p>;

  return (
    <div>
      {/* Summary + score header */}
      <div className="card" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 20, marginBottom: 20 }}>
        {data.wellness_score != null && (
          <div style={{ textAlign: 'center' }}>
            <CircularScore score={data.wellness_score} size={100} strokeWidth={8} />
          </div>
        )}
        <div style={{ flex: 1, minWidth: 200 }}>
          <h3 style={{ margin: '0 0 6px', fontSize: 16, fontWeight: 700, color: '#1f2937' }}>
            Improvement Plan
          </h3>
          {data.summary && (
            <p style={{ margin: 0, fontSize: 14, color: '#4b5563', lineHeight: 1.6 }}>{data.summary}</p>
          )}
        </div>
      </div>

      {/* Collapsible sections */}
      {IMPROVEMENT_SECTIONS.map((section) => {
        const items = data[section.key];
        if (!items || items.length === 0) return null;
        const isOpen = expanded[section.key];
        const SectionIcon = section.icon;

        return (
          <div className="card" key={section.key} style={{ marginBottom: 12, padding: 0, overflow: 'hidden' }}>
            <button
              onClick={() => toggleSection(section.key)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '14px 18px',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 8,
                  background: `${section.color}15`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <SectionIcon size={16} style={{ color: section.color }} />
              </div>
              <span style={{ flex: 1, fontSize: 15, fontWeight: 600, color: '#1f2937' }}>
                {section.label}
              </span>
              <span
                style={{
                  fontSize: 12,
                  color: '#9ca3af',
                  background: '#f3f4f6',
                  padding: '2px 8px',
                  borderRadius: 10,
                  marginRight: 8,
                }}
              >
                {items.length} item{items.length !== 1 ? 's' : ''}
              </span>
              {isOpen ? (
                <ChevronDown size={18} style={{ color: '#9ca3af' }} />
              ) : (
                <ChevronRight size={18} style={{ color: '#9ca3af' }} />
              )}
            </button>

            {isOpen && (
              <div style={{ padding: '0 18px 16px', borderTop: '1px solid #f3f4f6' }}>
                <ul style={{ margin: '12px 0 0', paddingLeft: 20, listStyle: 'none' }}>
                  {items.map((item, i) => {
                    const text =
                      typeof item === 'string'
                        ? item
                        : item.description || item.text || item.title || JSON.stringify(item);
                    return (
                      <li
                        key={i}
                        style={{
                          fontSize: 14,
                          color: '#4b5563',
                          marginBottom: 10,
                          lineHeight: 1.5,
                          position: 'relative',
                          paddingLeft: 16,
                        }}
                      >
                        <span
                          style={{
                            position: 'absolute',
                            left: 0,
                            top: 7,
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            background: section.color,
                          }}
                        />
                        {typeof item === 'object' && item.title ? (
                          <>
                            <strong style={{ color: '#1f2937' }}>{item.title}</strong>
                            {item.description && (
                              <span style={{ display: 'block', marginTop: 2 }}>{item.description}</span>
                            )}
                          </>
                        ) : (
                          text
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ============================================================
   MAIN WELLNESS PAGE
   ============================================================ */
export default function Wellness() {
  const [activeTab, setActiveTab] = useState('score');

  const ActiveComponent = {
    score: ScoreTab,
    omega: HEBCSTab,
    trends: TrendsTab,
    recommendations: RecommendationsTab,
    improvements: ImprovementsTab,
  }[activeTab];

  return (
    <div style={{ padding: '0 0 40px' }}>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Heart size={28} style={{ color: 'var(--color-primary)' }} />
            Wellness
          </h1>
        </div>
        <p style={{ color: '#6b7280', margin: '4px 0 0', fontSize: 14 }}>
          Track your overall health and wellness journey
        </p>
      </div>

      {/* Tab navigation */}
      <div
        style={{
          display: 'flex',
          gap: 4,
          marginBottom: 24,
          background: '#f3f4f6',
          borderRadius: 10,
          padding: 4,
          overflowX: 'auto',
        }}
      >
        {TABS.map((tab) => {
          const TabIcon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
                padding: '10px 16px',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 14,
                fontWeight: isActive ? 600 : 500,
                color: isActive ? '#fff' : '#6b7280',
                background: isActive ? 'var(--color-primary)' : 'transparent',
                transition: 'all 0.2s ease',
                whiteSpace: 'nowrap',
              }}
            >
              <TabIcon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Active tab content */}
      {ActiveComponent && <ActiveComponent />}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
