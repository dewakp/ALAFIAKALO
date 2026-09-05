import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Activity, TrendingUp, TrendingDown, Minus, Network, LineChart, Info } from 'lucide-react';
import BackButton from '../components/BackButton';

// Basis cornerstones #4 (relationship graphs / cause-effect) and #5 (predict
// future states). Associations are NOT causation — surfaced with that caveat.

function StrengthBar({ value }) {
  const pct = Math.min(Math.abs(value) * 100, 100);
  const positive = value >= 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 120 }}>
      <div style={{ flex: 1, height: 8, background: 'var(--surface-2, #eee)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: positive ? '#22c55e' : '#ef4444' }} />
      </div>
      <span style={{ fontSize: '.75rem', color: 'var(--text-secondary)', width: 38, textAlign: 'right' }}>
        {value > 0 ? '+' : ''}{value.toFixed(2)}
      </span>
    </div>
  );
}

function ForecastChart({ data }) {
  const hist = data.history || [];
  const fc = data.forecast || [];
  if (!hist.length) return null;

  const all = [
    ...hist.map((p) => ({ ...p, kind: 'h' })),
    ...fc.map((p) => ({ ...p, kind: 'f' })),
  ];
  const W = 560, H = 160, P = 24;
  const ys = [
    ...hist.map((p) => p.value),
    ...fc.flatMap((p) => [p.lower, p.upper]),
  ];
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const range = maxY - minY || 1;
  const x = (i) => P + (i * (W - 2 * P)) / Math.max(all.length - 1, 1);
  const y = (v) => H - P - ((v - minY) / range) * (H - 2 * P);

  const histLine = hist.map((p, i) => `${x(i)},${y(p.value)}`).join(' ');
  const fcStart = hist.length - 1;
  const fcLine = [
    `${x(fcStart)},${y(hist[hist.length - 1].value)}`,
    ...fc.map((p, i) => `${x(fcStart + 1 + i)},${y(p.value)}`),
  ].join(' ');
  const bandTop = fc.map((p, i) => `${x(fcStart + 1 + i)},${y(p.upper)}`);
  const bandBot = fc.map((p, i) => `${x(fcStart + 1 + i)},${y(p.lower)}`).reverse();
  const band = [...bandTop, ...bandBot].join(' ');

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto' }}>
      {fc.length > 0 && <polygon points={band} fill="var(--primary)" opacity="0.12" />}
      <polyline points={histLine} fill="none" stroke="var(--primary)" strokeWidth="2" />
      {fc.length > 0 && (
        <polyline points={fcLine} fill="none" stroke="var(--primary)" strokeWidth="2" strokeDasharray="5 4" />
      )}
      {hist.map((p, i) => <circle key={`h${i}`} cx={x(i)} cy={y(p.value)} r="2" fill="var(--primary)" />)}
    </svg>
  );
}

export default function HealthInsights() {
  const [rels, setRels] = useState(null);
  const [relsErr, setRelsErr] = useState('');
  const [signals, setSignals] = useState([]);
  const [selSignal, setSelSignal] = useState('');
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [{ data: r }, { data: s }] = await Promise.all([
          api.get('/insights/relationships'),
          api.get('/insights/signals'),
        ]);
        if (cancelled) return;
        setRels(r);
        const forecastable = (s.signals || []).filter((sig) => sig.sample_size >= 4);
        setSignals(forecastable);
        if (forecastable.length) setSelSignal(forecastable[0].key);
      } catch (err) {
        if (!cancelled) setRelsErr(apiErrorMessage(err, 'Could not load insights.'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const loadForecast = useCallback(async (key) => {
    if (!key) return;
    setForecast(null);
    try {
      const { data } = await api.get('/insights/forecast', { params: { signal: key } });
      setForecast(data);
    } catch (err) {
      setForecast({ error: apiErrorMessage(err, 'Could not forecast this signal.') });
    }
  }, []);

  useEffect(() => { if (selSignal) loadForecast(selSignal); }, [selSignal, loadForecast]);

  const TrendIcon = forecast?.trend === 'rising' ? TrendingUp
    : forecast?.trend === 'falling' ? TrendingDown : Minus;

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Health Insights</h1>
        </div>
      </div>

      <div className="card" style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 16, background: 'var(--primary-light, #eef6ff)' }}>
        <Info size={18} style={{ flexShrink: 0, marginTop: 2 }} />
        <div style={{ fontSize: '.85rem' }}>
          These patterns and forecasts are computed from your own logs. They show
          <strong> associations and trends, not medical cause-and-effect</strong>. Always discuss with your care team.
        </div>
      </div>

      {loading ? (
        <div className="card">Analyzing your data…</div>
      ) : (
        <>
          {/* ── Relationships ── */}
          <div className="card" style={{ marginBottom: 16 }}>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 0 }}>
              <Network size={18} /> Relationships
            </h3>
            {relsErr && <p style={{ color: 'var(--danger, #ef4444)' }}>{relsErr}</p>}
            {rels && rels.relationships.length === 0 && (
              <p style={{ color: 'var(--text-secondary)' }}>
                No clear relationships yet. Keep logging across diet, vitals, sleep, mood and symptoms —
                patterns emerge once a few weeks of overlapping data exist.
              </p>
            )}
            {rels && rels.relationships.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {rels.relationships.map((e, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: 220 }}>
                      <span style={{ fontWeight: 600 }}>{e.source_label}</span>
                      <span style={{ color: 'var(--text-secondary)', margin: '0 6px' }}>
                        {/* NOT "leads by". The banner above says these are
                            associations rather than cause and effect, and this
                            line then drew a directional arrow that says the
                            opposite. A lag is an offset that was tested, not a
                            direction of effect. */}
                        {e.direction === 'offset'
                          ? `↔ at a ${e.lag_days}-day offset`
                          : '↔ same day as'}
                      </span>
                      <span style={{ fontWeight: 600 }}>{e.target_label}</span>
                      <div style={{ fontSize: '.72rem', color: 'var(--text-secondary)' }}>
                        {e.strength > 0 ? 'positive' : 'inverse'} association · n={e.sample_size} days
                        {typeof e.p_value === 'number' && ` · p=${e.p_value < 0.001 ? '<0.001' : e.p_value.toFixed(3)}`}
                      </div>
                    </div>
                    <StrengthBar value={e.strength} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Forecast ── */}
          <div className="card">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 0 }}>
              <LineChart size={18} /> Forecast
            </h3>
            {signals.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)' }}>
                Not enough data to forecast yet. Log a signal (weight, BP, sleep…) for at least 4 days.
              </p>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
                  <label className="form-label" style={{ margin: 0 }}>Signal:</label>
                  <select className="form-input" style={{ maxWidth: 280 }}
                    value={selSignal} onChange={(e) => setSelSignal(e.target.value)}>
                    {signals.map((s) => (
                      <option key={s.key} value={s.key}>{s.label} ({s.sample_size}d)</option>
                    ))}
                  </select>
                  {forecast && !forecast.error && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '.85rem',
                      color: forecast.trend === 'rising' ? '#22c55e' : forecast.trend === 'falling' ? '#ef4444' : 'var(--text-secondary)' }}>
                      <TrendIcon size={16} /> {forecast.trend}
                    </span>
                  )}
                </div>
                {forecast?.error && <p style={{ color: 'var(--danger,#ef4444)' }}>{forecast.error}</p>}
                {forecast && !forecast.error && (
                  <>
                    <ForecastChart data={forecast} />
                    <div style={{ fontSize: '.75rem', color: 'var(--text-secondary)', marginTop: 6 }}>
                      Solid = your history · dashed = {forecast.forecast.length}-day projection · shaded = 95% range · {forecast.caveat}
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
