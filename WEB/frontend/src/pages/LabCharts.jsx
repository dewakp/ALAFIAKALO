import { useState, useEffect } from 'react';
import api from '../services/api';
import {
  Activity,
  FlaskConical,
  Loader2,
  AlertCircle,
  TrendingUp,
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceArea,
  ReferenceLine,
} from 'recharts';
import BackButton from '../components/BackButton';

const LINE_COLORS = [
  '#10b981',
  '#3b82f6',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#ec4899',
  '#14b8a6',
];

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div
      style={{
        background: '#fff',
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        padding: '10px 14px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
        fontSize: 13,
      }}
    >
      <p style={{ margin: 0, fontWeight: 600, marginBottom: 6, color: '#374151' }}>{label}</p>
      {payload.map((entry, i) => (
        <p key={i} style={{ margin: '3px 0', color: entry.color }}>
          {entry.name}: <strong>{entry.value}</strong>
        </p>
      ))}
    </div>
  );
}

function GroupChart({ group }) {
  // Merge all series data into unified date-keyed rows
  const dateMap = {};
  let globalRefLow = null;
  let globalRefHigh = null;
  let unit = '';

  group.series.forEach((s) => {
    if (!unit && s.unit) unit = s.unit;
    s.data.forEach((pt) => {
      const key = pt.date;
      if (!dateMap[key]) dateMap[key] = { date: pt.date, _formatted: formatDate(pt.date) };
      dateMap[key][s.test_name] = pt.value;

      // Track reference ranges (use widest range across all series)
      if (pt.reference_low != null) {
        if (globalRefLow == null || pt.reference_low < globalRefLow) globalRefLow = pt.reference_low;
      }
      if (pt.reference_high != null) {
        if (globalRefHigh == null || pt.reference_high > globalRefHigh) globalRefHigh = pt.reference_high;
      }
    });
  });

  const chartData = Object.values(dateMap).sort((a, b) => a.date.localeCompare(b.date));

  // Compute Y-axis domain
  let allValues = [];
  group.series.forEach((s) => s.data.forEach((pt) => allValues.push(pt.value)));
  if (globalRefLow != null) allValues.push(globalRefLow);
  if (globalRefHigh != null) allValues.push(globalRefHigh);
  const minVal = Math.min(...allValues);
  const maxVal = Math.max(...allValues);
  const padding = (maxVal - minVal) * 0.15 || 10;
  const yMin = Math.floor(minVal - padding);
  const yMax = Math.ceil(maxVal + padding);

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <FlaskConical size={20} style={{ color: 'var(--color-primary)' }} />
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1f2937' }}>
          {group.group_name || group.name}
        </h3>
        {unit && (
          <span
            style={{
              fontSize: 12,
              color: '#6b7280',
              background: '#f3f4f6',
              padding: '2px 8px',
              borderRadius: 12,
            }}
          >
            {unit}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 13, color: '#6b7280' }}>
          {group.series.length} test{group.series.length !== 1 ? 's' : ''} &middot;{' '}
          {chartData.length} data point{chartData.length !== 1 ? 's' : ''}
        </span>
      </div>

      {chartData.length === 0 ? (
        <p style={{ color: '#9ca3af', textAlign: 'center', padding: 24 }}>
          No data points available for this group.
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="_formatted"
              tick={{ fontSize: 12, fill: '#6b7280' }}
              tickLine={false}
              axisLine={{ stroke: '#e5e7eb' }}
            />
            <YAxis
              domain={[yMin, yMax]}
              tick={{ fontSize: 12, fill: '#6b7280' }}
              tickLine={false}
              axisLine={{ stroke: '#e5e7eb' }}
              label={
                unit
                  ? { value: unit, angle: -90, position: 'insideLeft', style: { fontSize: 12, fill: '#9ca3af' } }
                  : undefined
              }
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 13, paddingTop: 8 }}
              iconType="circle"
              iconSize={8}
            />

            {/* Reference range shading */}
            {globalRefLow != null && globalRefHigh != null && (
              <ReferenceArea
                y1={globalRefLow}
                y2={globalRefHigh}
                fill="#10b981"
                fillOpacity={0.06}
                stroke="none"
                label={{
                  value: 'Normal Range',
                  position: 'insideTopRight',
                  style: { fontSize: 10, fill: '#10b981' },
                }}
              />
            )}
            {globalRefLow != null && globalRefHigh == null && (
              <ReferenceLine
                y={globalRefLow}
                stroke="#10b981"
                strokeDasharray="4 4"
                strokeOpacity={0.6}
                label={{ value: 'Low', position: 'right', style: { fontSize: 10, fill: '#10b981' } }}
              />
            )}
            {globalRefHigh != null && globalRefLow == null && (
              <ReferenceLine
                y={globalRefHigh}
                stroke="#ef4444"
                strokeDasharray="4 4"
                strokeOpacity={0.6}
                label={{ value: 'High', position: 'right', style: { fontSize: 10, fill: '#ef4444' } }}
              />
            )}

            {group.series.map((s, idx) => (
              <Line
                key={s.test_name}
                type="monotone"
                dataKey={s.test_name}
                stroke={LINE_COLORS[idx % LINE_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 4, strokeWidth: 2, fill: '#fff' }}
                activeDot={{ r: 6 }}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export default function LabCharts() {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchGroups();
  }, []);

  async function fetchGroups() {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get('/lab-charts/groups');
      setGroups(Array.isArray(res.data) ? res.data : res.data.groups || []);
    } catch (err) {
      console.error('Failed to load lab chart groups:', err);
      setError(err.response?.data?.detail || 'Failed to load lab chart data.');
    } finally {
      setLoading(false);
    }
  }

  const totalTests = groups.reduce((sum, g) => sum + (g.series?.length || 0), 0);

  return (
    <div style={{ padding: '0 0 40px' }}>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Activity size={28} style={{ color: 'var(--color-primary)' }} />
            Lab Charts
          </h1>
        </div>
        <p style={{ color: '#6b7280', margin: '4px 0 0', fontSize: 14 }}>
          Interactive visualizations of your lab results over time
        </p>
      </div>

      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 60, gap: 10 }}>
          <Loader2 size={24} style={{ color: 'var(--color-primary)', animation: 'spin 1s linear infinite' }} />
          <span style={{ color: '#6b7280', fontSize: 15 }}>Loading lab charts…</span>
        </div>
      )}

      {error && !loading && (
        <div
          className="card"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            background: '#fef2f2',
            borderColor: '#fee2e2',
          }}
        >
          <AlertCircle size={20} style={{ color: 'var(--color-danger)', flexShrink: 0 }} />
          <div>
            <p style={{ margin: 0, fontWeight: 600, color: '#991b1b' }}>Error loading data</p>
            <p style={{ margin: '4px 0 0', color: '#b91c1c', fontSize: 14 }}>{error}</p>
          </div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={fetchGroups}
            style={{ marginLeft: 'auto' }}
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && groups.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: 48 }}>
          <FlaskConical size={40} style={{ color: '#d1d5db', marginBottom: 12 }} />
          <p style={{ color: '#6b7280', fontSize: 15, margin: 0 }}>
            No lab results available yet. Your lab charts will appear here once results are recorded.
          </p>
        </div>
      )}

      {!loading && !error && groups.length > 0 && (
        <>
          <div
            className="stats-grid"
            style={{ marginBottom: 24, display: 'flex', gap: 16 }}
          >
            <div
              className="card"
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '16px 20px',
              }}
            >
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 10,
                  background: 'rgba(16,185,129,0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <FlaskConical size={20} style={{ color: 'var(--color-primary)' }} />
              </div>
              <div>
                <p style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#1f2937' }}>
                  {groups.length}
                </p>
                <p style={{ margin: 0, fontSize: 13, color: '#6b7280' }}>
                  Test Group{groups.length !== 1 ? 's' : ''}
                </p>
              </div>
            </div>
            <div
              className="card"
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '16px 20px',
              }}
            >
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 10,
                  background: 'rgba(59,130,246,0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <TrendingUp size={20} style={{ color: 'var(--color-info)' }} />
              </div>
              <div>
                <p style={{ margin: 0, fontSize: 22, fontWeight: 700, color: '#1f2937' }}>
                  {totalTests}
                </p>
                <p style={{ margin: 0, fontSize: 13, color: '#6b7280' }}>
                  Total Test{totalTests !== 1 ? 's' : ''}
                </p>
              </div>
            </div>
          </div>

          {groups.map((group, idx) => (
            <GroupChart key={group.group_name || group.name || idx} group={group} />
          ))}
        </>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
