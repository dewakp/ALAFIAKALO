import { useState, useEffect, useMemo } from 'react';
import api from '../services/api';
import {
  BarChart3,
  Loader2,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  Minus,
  Settings2,
  Plus,
  X,
  Info,
} from 'lucide-react';
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  ScatterChart, Scatter, PieChart, Pie, Cell,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ComposedChart,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';
import BackButton from '../components/BackButton';

/* ── colour palette ──────────────────────────────────────── */
const PALETTE = [
  '#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#14b8a6', '#f97316', '#6366f1', '#84cc16',
];

const CHART_TYPES = [
  { key: 'line',    label: 'Line' },
  { key: 'bar',     label: 'Bar' },
  { key: 'area',    label: 'Area' },
  { key: 'scatter', label: 'Scatter' },
  { key: 'pie',     label: 'Pie' },
  { key: 'radar',   label: 'Radar' },
  { key: 'composed',label: 'Composed' },
];

const AGG_OPTIONS = [
  { key: 'daily',   label: 'Daily' },
  { key: 'weekly',  label: 'Weekly' },
  { key: 'monthly', label: 'Monthly' },
];

const DAY_OPTIONS = [
  { key: 30,  label: '30 days' },
  { key: 90,  label: '90 days' },
  { key: 180, label: '6 months' },
  { key: 365, label: '1 year' },
  { key: 730, label: '2 years' },
];

/* ── helpers ─────────────────────────────────────────────── */
function fmtDate(d) {
  if (!d) return '';
  const dt = new Date(d);
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function trendIcon(trend) {
  if (trend === 'increasing') return <TrendingUp size={14} style={{ color: '#10b981' }} />;
  if (trend === 'decreasing') return <TrendingDown size={14} style={{ color: '#ef4444' }} />;
  return <Minus size={14} style={{ color: '#9ca3af' }} />;
}

/* ── Custom Tooltip ──────────────────────────────────────── */
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8,
      padding: '10px 14px', boxShadow: '0 4px 12px rgba(0,0,0,0.08)', fontSize: 13,
    }}>
      <p style={{ margin: 0, fontWeight: 600, marginBottom: 6, color: '#374151' }}>{label}</p>
      {payload.map((e, i) => (
        <p key={i} style={{ margin: '3px 0', color: e.color || e.fill }}>
          {e.name}: <strong>{e.value}</strong>
        </p>
      ))}
    </div>
  );
}

/* ── Main Component ──────────────────────────────────────── */
export default function ChartDashboard() {
  const [datasets, setDatasets] = useState(null);       // domain → [{key,label,unit}]
  const [selected, setSelected] = useState([]);          // ['calories','steps',…]
  const [chartType, setChartType] = useState('line');
  const [agg, setAgg] = useState('daily');
  const [days, setDays] = useState(90);
  const [chartData, setChartData] = useState(null);      // { key: {label,unit,domain,points} }
  const [summaries, setSummaries] = useState({});         // key→summary
  const [correlateData, setCorrelateData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [showPicker, setShowPicker] = useState(false);

  /* Load available datasets on mount */
  useEffect(() => {
    api.get('/chart-dashboard/datasets').then(r => setDatasets(r.data)).catch(() => {});
  }, []);

  /* Fetch chart data whenever selection or params change */
  useEffect(() => {
    if (!selected.length) { setChartData(null); setCorrelateData(null); setSummaries({}); return; }
    setLoading(true);
    setErr('');
    const keys = selected.join(',');
    const promises = [
      api.get('/chart-dashboard/data', { params: { datasets: keys, days, aggregation: agg } }),
      ...selected.map(k => api.get('/chart-dashboard/summary', { params: { dataset: k, days } }).catch(() => null)),
    ];
    if (selected.length === 2 && chartType === 'scatter') {
      promises.push(api.get('/chart-dashboard/correlate', { params: { dataset_a: selected[0], dataset_b: selected[1], days } }).catch(() => null));
    }
    Promise.all(promises).then(results => {
      setChartData(results[0].data);
      const sums = {};
      selected.forEach((k, i) => {
        const r = results[i + 1];
        if (r?.data) sums[k] = r.data;
      });
      setSummaries(sums);
      if (results.length > selected.length + 1 && results[results.length - 1]?.data) {
        setCorrelateData(results[results.length - 1].data);
      } else {
        setCorrelateData(null);
      }
    }).catch(e => setErr(e.response?.data?.detail || 'Failed to load chart data'))
      .finally(() => setLoading(false));
  }, [selected, days, agg, chartType]);

  /* Merge time-series into Recharts-friendly rows */
  const mergedData = useMemo(() => {
    if (!chartData) return [];
    const byDate = {};
    for (const [key, ds] of Object.entries(chartData)) {
      for (const pt of ds.points) {
        if (!byDate[pt.date]) byDate[pt.date] = { date: pt.date, _label: fmtDate(pt.date) };
        byDate[pt.date][key] = pt.value;
      }
    }
    return Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date));
  }, [chartData]);

  /* Pie/radar aggregation: average each selected dataset */
  const pieData = useMemo(() => {
    if (!chartData) return [];
    return selected.map((key, i) => {
      const pts = chartData[key]?.points || [];
      const avg = pts.length ? pts.reduce((s, p) => s + (p.value || 0), 0) / pts.length : 0;
      return { name: chartData[key]?.label || key, value: Math.round(avg * 100) / 100, fill: PALETTE[i % PALETTE.length] };
    });
  }, [chartData, selected]);

  const radarData = useMemo(() => {
    if (!chartData || !selected.length) return [];
    // Normalize each dataset 0-100 for radar comparison
    const normed = {};
    for (const key of selected) {
      const pts = chartData[key]?.points || [];
      const vals = pts.map(p => p.value).filter(Boolean);
      const mn = Math.min(...vals), mx = Math.max(...vals);
      const range = mx - mn || 1;
      normed[key] = {
        avg: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0,
        min: mn,
        max: mx,
        range,
      };
    }
    return ['Average', 'Min', 'Max'].map(metric => {
      const row = { metric };
      selected.forEach(key => {
        const n = normed[key];
        const raw = metric === 'Average' ? n.avg : metric === 'Min' ? n.min : n.max;
        row[key] = Math.round(((raw - n.min) / n.range) * 100);
      });
      return row;
    });
  }, [chartData, selected]);

  /* Toggle dataset selection */
  const toggle = (key) => {
    setSelected(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
  };

  /* ── Render ─────────────────────────────────────────────── */
  return (
    <div className="page-container">
      <div className="page-header">
        <div className="page-header-text">
          <div className="page-header">
            <div className="page-header-left">
              <BackButton />
              <h1 className="page-title"><BarChart3 size={28} /> Chart Dashboard</h1>
            </div>
          </div>
          <p className="page-subtitle">Visualize &amp; compare any health metric across your data</p>
        </div>
      </div>

      {/* ── Controls Bar ───────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16, alignItems: 'center' }}>
        <button className="btn btn-primary btn-sm" onClick={() => setShowPicker(p => !p)}>
          <Plus size={14} /> {showPicker ? 'Hide' : 'Add'} Datasets
        </button>

        {/* Chart type pills */}
        <div style={{ display: 'flex', gap: 4 }}>
          {CHART_TYPES.map(ct => (
            <button key={ct.key}
              className={`btn btn-sm ${chartType === ct.key ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setChartType(ct.key)}
            >{ct.label}</button>
          ))}
        </div>

        {/* Aggregation */}
        <select className="form-select" style={{ width: 120 }}
          value={agg} onChange={e => setAgg(e.target.value)}>
          {AGG_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>

        {/* Time range */}
        <select className="form-select" style={{ width: 120 }}
          value={days} onChange={e => setDays(Number(e.target.value))}>
          {DAY_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
      </div>

      {/* ── Dataset Picker ─────────────────────────────────── */}
      {showPicker && datasets && (
        <div className="card" style={{ marginBottom: 16, padding: 16 }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 15 }}>Available Datasets</h3>
          {Object.entries(datasets).map(([domain, items]) => (
            <div key={domain} style={{ marginBottom: 12 }}>
              <div style={{ fontWeight: 600, textTransform: 'capitalize', fontSize: 13, color: '#6b7280', marginBottom: 4 }}>{domain}</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {items.map(ds => {
                  const active = selected.includes(ds.key);
                  return (
                    <button key={ds.key}
                      onClick={() => toggle(ds.key)}
                      style={{
                        padding: '4px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                        border: active ? '2px solid #3b82f6' : '1px solid #d1d5db',
                        background: active ? '#eff6ff' : '#fff', color: active ? '#1d4ed8' : '#374151',
                        fontWeight: active ? 600 : 400,
                      }}
                    >
                      {ds.label} {ds.unit ? `(${ds.unit})` : ''}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Selected Tags */}
      {selected.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          {selected.map((key, i) => {
            const info = chartData?.[key] || {};
            return (
              <span key={key} style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600,
                background: PALETTE[i % PALETTE.length] + '22',
                color: PALETTE[i % PALETTE.length],
                border: `1px solid ${PALETTE[i % PALETTE.length]}44`,
              }}>
                <span style={{ width: 8, height: 8, borderRadius: 4, background: PALETTE[i % PALETTE.length] }} />
                {info.label || key}
                <button onClick={() => toggle(key)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'inherit', display: 'flex' }}>
                  <X size={12} />
                </button>
              </span>
            );
          })}
        </div>
      )}

      {/* ── Loading / Error ────────────────────────────────── */}
      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#6b7280' }}>
          <Loader2 size={28} className="spin" /> Loading chart data…
        </div>
      )}
      {err && (
        <div className="card" style={{ padding: 16, background: '#fef2f2', color: '#dc2626' }}>
          <AlertCircle size={16} style={{ verticalAlign: 'middle' }} /> {err}
        </div>
      )}

      {/* ── Empty State ────────────────────────────────────── */}
      {!loading && !err && !selected.length && (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
          <BarChart3 size={48} style={{ marginBottom: 12, opacity: 0.4 }} />
          <p style={{ fontSize: 16, fontWeight: 500 }}>Select one or more datasets to start charting</p>
          <p style={{ fontSize: 13 }}>Use the <strong>Add Datasets</strong> button above to pick from Nutrition, Fitness, Mood, Vitals, and Lifestyle metrics</p>
        </div>
      )}

      {/* ── Chart Area ─────────────────────────────────────── */}
      {!loading && chartData && selected.length > 0 && (
        <div className="card" style={{ padding: 20, marginBottom: 16 }}>
          <ResponsiveContainer width="100%" height={420}>
            {renderChart(chartType, mergedData, selected, chartData, pieData, radarData, correlateData)}
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Summary Cards ──────────────────────────────────── */}
      {Object.keys(summaries).length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12, marginBottom: 16 }}>
          {selected.map((key, i) => {
            const s = summaries[key];
            if (!s) return null;
            return (
              <div key={key} className="card" style={{ padding: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <span style={{ width: 10, height: 10, borderRadius: 5, background: PALETTE[i % PALETTE.length] }} />
                  <strong style={{ fontSize: 14 }}>{s.label}</strong>
                  <span style={{ fontSize: 12, color: '#9ca3af' }}>{s.unit}</span>
                  <span style={{ marginLeft: 'auto' }}>{trendIcon(s.trend)}</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 13 }}>
                  <div>Avg: <strong>{s.avg ?? '–'}</strong></div>
                  <div>Std: <strong>{s.stddev ?? '–'}</strong></div>
                  <div>Min: <strong>{s.min ?? '–'}</strong></div>
                  <div>Max: <strong>{s.max ?? '–'}</strong></div>
                  <div>Points: <strong>{s.count}</strong></div>
                  <div style={{ textTransform: 'capitalize' }}>Trend: <strong>{s.trend}</strong></div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Correlation info (scatter only) */}
      {correlateData && chartType === 'scatter' && (
        <div className="card" style={{ padding: 16 }}>
          <h3 style={{ fontSize: 14, marginBottom: 8 }}>
            <Info size={14} style={{ verticalAlign: 'middle' }} /> Correlation: {correlateData.x.label} vs {correlateData.y.label}
          </h3>
          <p style={{ fontSize: 13, color: '#6b7280' }}>
            {correlateData.points.length} matched data points found across {days} days.
          </p>
        </div>
      )}
    </div>
  );
}

/* ── Chart rendering helper ──────────────────────────────── */
function renderChart(type, merged, selected, chartData, pieData, radarData, correlateData) {
  const commonProps = {
    data: merged,
    margin: { top: 5, right: 20, bottom: 5, left: 0 },
  };

  switch (type) {
    case 'line':
      return (
        <LineChart {...commonProps}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="_label" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip content={<ChartTooltip />} />
          <Legend />
          {selected.map((key, i) => (
            <Line key={key} type="monotone" dataKey={key} name={chartData[key]?.label || key}
              stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} dot={{ r: 2 }} connectNulls />
          ))}
        </LineChart>
      );

    case 'bar':
      return (
        <BarChart {...commonProps}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="_label" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip content={<ChartTooltip />} />
          <Legend />
          {selected.map((key, i) => (
            <Bar key={key} dataKey={key} name={chartData[key]?.label || key}
              fill={PALETTE[i % PALETTE.length]} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      );

    case 'area':
      return (
        <AreaChart {...commonProps}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="_label" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip content={<ChartTooltip />} />
          <Legend />
          {selected.map((key, i) => (
            <Area key={key} type="monotone" dataKey={key} name={chartData[key]?.label || key}
              stroke={PALETTE[i % PALETTE.length]} fill={PALETTE[i % PALETTE.length] + '33'}
              strokeWidth={2} connectNulls />
          ))}
        </AreaChart>
      );

    case 'scatter':
      if (correlateData && selected.length === 2) {
        return (
          <ScatterChart margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <XAxis type="number" dataKey="x" name={correlateData.x.label} unit={correlateData.x.unit} tick={{ fontSize: 11 }} />
            <YAxis type="number" dataKey="y" name={correlateData.y.label} unit={correlateData.y.unit} tick={{ fontSize: 11 }} />
            <Tooltip cursor={{ strokeDasharray: '3 3' }} />
            <Legend />
            <Scatter name={`${correlateData.x.label} vs ${correlateData.y.label}`}
              data={correlateData.points} fill={PALETTE[0]} />
          </ScatterChart>
        );
      }
      // Fall through to line for single dataset scatter
      return (
        <ScatterChart margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="_label" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip content={<ChartTooltip />} />
          <Legend />
          {selected.map((key, i) => (
            <Scatter key={key} name={chartData[key]?.label || key}
              data={merged.filter(r => r[key] != null).map(r => ({ _label: r._label, [key]: r[key] }))}
              fill={PALETTE[i % PALETTE.length]} />
          ))}
        </ScatterChart>
      );

    case 'pie':
      return (
        <PieChart>
          <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%"
            outerRadius={150} innerRadius={60} label={({ name, value }) => `${name}: ${value}`}
            labelLine={{ stroke: '#9ca3af' }}>
            {pieData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      );

    case 'radar':
      return (
        <RadarChart cx="50%" cy="50%" outerRadius={140} data={radarData}>
          <PolarGrid />
          <PolarAngleAxis dataKey="metric" tick={{ fontSize: 12 }} />
          <PolarRadiusAxis tick={{ fontSize: 10 }} />
          {selected.map((key, i) => (
            <Radar key={key} name={chartData[key]?.label || key} dataKey={key}
              stroke={PALETTE[i % PALETTE.length]} fill={PALETTE[i % PALETTE.length] + '33'}
              fillOpacity={0.3} />
          ))}
          <Legend />
          <Tooltip />
        </RadarChart>
      );

    case 'composed':
      return (
        <ComposedChart {...commonProps}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="_label" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip content={<ChartTooltip />} />
          <Legend />
          {selected.map((key, i) => {
            // Alternate between Line, Bar, Area for composed
            const mod = i % 3;
            if (mod === 0)
              return <Line key={key} type="monotone" dataKey={key} name={chartData[key]?.label || key}
                stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} dot={{ r: 2 }} connectNulls />;
            if (mod === 1)
              return <Bar key={key} dataKey={key} name={chartData[key]?.label || key}
                fill={PALETTE[i % PALETTE.length]} radius={[4, 4, 0, 0]} barSize={20} />;
            return <Area key={key} type="monotone" dataKey={key} name={chartData[key]?.label || key}
              stroke={PALETTE[i % PALETTE.length]} fill={PALETTE[i % PALETTE.length] + '22'}
              strokeWidth={2} connectNulls />;
          })}
        </ComposedChart>
      );

    default:
      return <LineChart {...commonProps}><CartesianGrid /><XAxis dataKey="_label" /><YAxis /><Tooltip /></LineChart>;
  }
}
