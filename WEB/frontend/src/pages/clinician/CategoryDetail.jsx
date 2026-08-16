import { useEffect, useMemo, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import api from '../../services/api';
import { ArrowLeft } from 'lucide-react';
import { colorAt, CHART_INK } from './chartPalette';
import TherapyReport from './TherapyReport';

// Mirrors the patient's own period control. "All" was 1825 days, which on the
// reference record returned 1048 of 2005 sessions — history starts 2013-05-21 —
// so the physician pressed "All" and was shown half the chart with nothing
// saying so. A window labelled All must not have a horizon.
const WINDOWS = [
  { days: 30, label: '30 days' },
  { days: 90, label: '90 days' },
  { days: 180, label: '180 days' },
  { days: 365, label: '1 year' },
  { days: 36500, label: 'All' },
];

const fmtDate = (s) => {
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
};

function useDarkMode() {
  const [dark, setDark] = useState(
    () => window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
  );
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!mq) return undefined;
    const onChange = (e) => setDark(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return dark;
}

// Above this many series, one plot per measure (small multiples) instead of
// grouping by unit. Six is the validated palette width: a seventh series would
// have to reuse a hue, and identity by colour would be gone. It is also the
// clinically right call for labs — BUN and cholesterol share mg/dL and nothing
// else, so putting them on one axis says nothing a clinician can use.
const MAX_SERIES_PER_CHART = 6;

export default function CategoryDetail({ patientId, categoryKey, onBack }) {
  const [days, setDays] = useState(90);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [picked, setPicked] = useState(null);   // series labels, when picking
  const isDark = useDarkMode();

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api.get(`/clinician-dashboard/patient/${patientId}/category/${categoryKey}`, { params: { days } })
      .then(({ data: d }) => {
        if (cancelled) return;
        setData(d);
        // Backend sorts by point count, so the default selection is the
        // measures with the most history — the ones that actually trend.
        setPicked((d.series || []).length > MAX_SERIES_PER_CHART
          ? (d.series || []).slice(0, 4).map(x => x.label)
          : null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.response?.data?.detail || 'Could not load this category.');
      });
    return () => { cancelled = true; };
  }, [patientId, categoryKey, days]);

  // Series that share a unit share an axis; different units get their own
  // chart. Never a second y-axis — two scales on one plot is the mistake that
  // makes a chart say whatever the axis ranges were set to.
  const manySeries = (data?.series?.length || 0) > MAX_SERIES_PER_CHART;

  const groups = useMemo(() => {
    if (!data?.series?.length) return [];

    // Many measures → one chart each, limited to what the clinician picked.
    if (manySeries) {
      const chosen = new Set(picked || []);
      return data.series.filter(s => chosen.has(s.label))
        .map(s => ({ unit: s.unit || '', series: [s] }));
    }

    const byUnit = new Map();
    data.series.forEach((s) => {
      const unit = s.unit || '';
      if (!byUnit.has(unit)) byUnit.set(unit, []);
      byUnit.get(unit).push(s);
    });
    // A unit group can still exceed the palette; split rather than cycle hues.
    const out = [];
    byUnit.forEach((series, unit) => {
      for (let i = 0; i < series.length; i += MAX_SERIES_PER_CHART) {
        out.push({ unit, series: series.slice(i, i + MAX_SERIES_PER_CHART) });
      }
    });
    return out;
  }, [data, manySeries, picked]);

  if (error) {
    return (
      <div>
        <Header onBack={onBack} title="Category" />
        <div className="card" style={{ padding: '2rem', color: 'var(--color-danger)' }}>{error}</div>
      </div>
    );
  }
  if (!data) return <div className="loading">Loading…</div>;

  return (
    <div>
      <Header
        onBack={onBack}
        title={`${data.label} — ${data.patient.full_name}`}
      />

      {/* Filters in one row above the charts. */}
      <div style={{ display: 'flex', gap: 6, marginBottom: '1rem', flexWrap: 'wrap' }}>
        {WINDOWS.map(w => (
          <button
            key={w.days}
            onClick={() => setDays(w.days)}
            aria-pressed={days === w.days}
            className="btn btn-sm"
            style={{
              background: days === w.days ? 'var(--color-primary)' : 'transparent',
              color: days === w.days ? '#fff' : 'var(--color-text-secondary)',
              border: '1px solid var(--color-border)',
            }}
          >
            {w.label}
          </button>
        ))}
        {categoryKey === 'labs' && (
          <span style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)', alignSelf: 'center' }}>
            Labs show the most recent results across all history — they are drawn
            in panels, not daily, so a short window shows no trend.
          </span>
        )}
      </div>

      {manySeries && (
        <div style={{ marginBottom: '1rem' }}>
          <div style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)', marginBottom: 6 }}>
            {data.series.length} measures have enough history to trend — pick the ones to plot:
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {data.series.map((s2) => {
              const on = (picked || []).includes(s2.label);
              return (
                <button
                  key={s2.label}
                  onClick={() => setPicked(p => (on ? p.filter(x => x !== s2.label) : [...p, s2.label]))}
                  aria-pressed={on}
                  style={{
                    padding: '3px 10px', borderRadius: 14, fontSize: 12, cursor: 'pointer',
                    border: '1px solid var(--color-border)',
                    background: on ? 'var(--color-primary)' : 'transparent',
                    color: on ? '#fff' : 'var(--color-text-secondary)',
                  }}
                >
                  {s2.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {groups.map((g, gi) => (
        // Key on the series names: in small-multiples mode several charts share
        // a unit, so the unit alone collides.
        <TrendChart key={g.series.map(s2 => s2.label).join('|') || gi} group={g} isDark={isDark} />
      ))}

      {groups.length === 0 && (
        <div className="card" style={{ padding: '1.25rem', color: 'var(--color-text-secondary)', marginBottom: '1rem' }}>
          No trend to plot for this period — the table below has the records.
        </div>
      )}

      {/* Therapies is not a generic table: a dialysis session is a document a
          clinician opens, reads a curve from, and signs. The flat renderer
          showed its Detail and Session columns as em-dashes. */}
      {categoryKey === 'dialysis'
        ? <TherapyReport patientId={patientId} rows={data.rows} days={days} />
        : <DataTable columns={data.columns} rows={data.rows} label={data.label} />}
    </div>
  );
}

function Header({ onBack, title }) {
  return (
    <div className="page-header">
      <div className="page-header-left">
        <button className="btn btn-secondary btn-sm" onClick={onBack}>
          <ArrowLeft size={16} /> Back
        </button>
        <h1 className="page-title">{title}</h1>
      </div>
    </div>
  );
}

function TrendChart({ group, isDark }) {
  // Merge the group's series onto a shared date axis.
  const rows = useMemo(() => {
    const byDate = new Map();
    group.series.forEach((s) => {
      s.points.forEach((p) => {
        if (!byDate.has(p.date)) byDate.set(p.date, { date: p.date });
        byDate.get(p.date)[s.label] = p.value;
      });
    });
    return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [group]);

  const single = group.series.length === 1;
  const title = single
    ? `${group.series[0].label}${group.unit ? ` (${group.unit})` : ''}`
    : `${group.series.map(s => s.label).join(' · ')}${group.unit ? ` (${group.unit})` : ''}`;

  return (
    <div className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
      {/* The title names the measure, so a single series needs no legend box. */}
      <h4 style={{ marginBottom: '0.75rem', fontSize: '0.9rem' }}>{title}</h4>
      <div style={{ width: '100%', height: 240 }}>
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke={CHART_INK.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="date" tickFormatter={fmtDate}
              tick={{ fontSize: 11, fill: CHART_INK.axis }}
              stroke={CHART_INK.grid} minTickGap={24}
            />
            <YAxis
              tick={{ fontSize: 11, fill: CHART_INK.axis }}
              stroke={CHART_INK.grid} width={48}
            />
            <Tooltip
              labelFormatter={fmtDate}
              contentStyle={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 8, fontSize: 12,
              }}
              itemStyle={{ color: 'var(--color-text-primary, inherit)' }}
              labelStyle={{ color: 'var(--color-text-secondary)' }}
            />
            {!single && <Legend wrapperStyle={{ fontSize: 12 }} />}
            {group.series.map((s, i) => (
              <Line
                key={s.label}
                type="monotone"
                dataKey={s.label}
                stroke={colorAt(i, isDark)}
                strokeWidth={2}
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function DataTable({ columns, rows, label }) {
  if (!rows?.length) {
    return (
      <div className="card" style={{ padding: '1.25rem', color: 'var(--color-text-secondary)' }}>
        No {label.toLowerCase()} records in this period.
      </div>
    );
  }
  return (
    <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
        <thead>
          <tr>
            {columns.map(c => (
              <th key={c.key} style={{
                textAlign: 'left', padding: '0.6rem 0.9rem',
                borderBottom: '1px solid var(--color-border)',
                color: 'var(--color-text-secondary)', fontWeight: 600, whiteSpace: 'nowrap',
              }}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ color: r.danger ? 'var(--color-danger)' : 'inherit' }}>
              {columns.map(c => (
                <td key={c.key} style={{
                  padding: '0.55rem 0.9rem',
                  borderBottom: '1px solid var(--color-border)',
                  verticalAlign: 'top',
                }}>
                  {r[c.key] == null || r[c.key] === '' ? '—' : String(r[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
