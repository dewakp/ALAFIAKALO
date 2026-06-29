import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { Radar, RefreshCw, MapPin, Globe, Activity, ExternalLink, X } from 'lucide-react';
import BackButton from '../components/BackButton';
import ChoroplethMap, { LEVEL_COLORS, LEVEL_LABELS } from '../components/ChoroplethMap';
import USCoverageMap from '../components/USCoverageMap';
import { flagEmoji, A2_TO_NAME } from '../data/isoCountries';

const WHO_REGIONS = ['Africa', 'Americas', 'Eastern Mediterranean', 'Europe', 'South-East Asia', 'Western Pacific'];
const VIEWS = [
  { id: 'both', label: 'Both', icon: Radar },
  { id: 'outward', label: 'Outward (WHO/CDC)', icon: Globe },
  { id: 'inward', label: 'Inward (patients)', icon: Activity },
];

function fmt(n) {
  if (n == null) return '—';
  return n >= 1000 ? Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }) : `${n}`;
}

/** Tiny inline sparkline for a WHO yearly series. */
function Sparkline({ series }) {
  if (!series || series.length < 2) return null;
  const w = 240, h = 48, pad = 4;
  const vals = series.map((p) => p.value);
  const max = Math.max(...vals), min = Math.min(...vals);
  const span = max - min || 1;
  const pts = series.map((p, i) => {
    const x = pad + (i / (series.length - 1)) * (w - 2 * pad);
    const y = h - pad - ((p.value - min) / span) * (h - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg width={w} height={h} style={{ maxWidth: '100%' }} aria-label="Trend">
      <polyline points={pts} fill="none" stroke="#dc2626" strokeWidth="2" />
    </svg>
  );
}

export default function DiseaseSurveillance() {
  const [diseases, setDiseases] = useState([]);
  const [disease, setDisease] = useState('cholera');
  const [view, setView] = useState('both');
  const [region, setRegion] = useState('');
  const [days, setDays] = useState(90);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);     // iso2
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    api.get('/surveillance/diseases').then(({ data }) => setDiseases(data)).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/surveillance/global', {
        params: { disease, view, days, ...(region ? { region } : {}) },
      });
      setData(data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [disease, view, region, days]);

  useEffect(() => { load(); }, [load]);

  const loadDetail = useCallback(async (iso2) => {
    setSelected(iso2);
    setDetail(null);
    setDetailLoading(true);
    try {
      const { data } = await api.get(`/surveillance/country/${iso2}`, { params: { disease, days } });
      setDetail(data);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, [disease, days]);

  // Build the choropleth lookup from the global response.
  const mapData = {};
  (data?.countries || []).forEach((c) => {
    mapData[c.iso2] = { level: c.level, label: c.value_label, name: c.name, hasInward: c.inward > 0 };
  });

  const activeDisease = diseases.find((d) => d.id === disease);

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title"><Radar size={20} style={{ verticalAlign: -3, marginRight: 6 }} />Disease Surveillance</h1>
        </div>
        <button className="btn btn-secondary" onClick={load} disabled={loading}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      <p style={{ color: 'var(--color-text-secondary)', marginBottom: '1rem', maxWidth: 760 }}>
        Looking <strong>outward</strong> to authoritative sources (WHO globally, CDC for the US,
        Africa via WHO's African region) and <strong>inward</strong> to de-identified ALAFIA patient
        symptom reports. Click any shaded country to drill down.
      </p>

      {/* Disease selector */}
      <div style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap', marginBottom: '.75rem' }}>
        {diseases.map((d) => (
          <button key={d.id} className={`btn btn-sm ${disease === d.id ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setDisease(d.id)} title={`${d.category} · ${d.who_unit}`}>
            {d.icon} {d.label}
          </button>
        ))}
      </div>

      {/* View / region / window controls */}
      <div className="card" style={{ padding: '1rem', marginBottom: '1rem', display: 'flex', gap: '1.25rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div>
          <div style={{ fontSize: '.75rem', fontWeight: 600, marginBottom: '.35rem', color: 'var(--color-text-secondary)' }}>Lens</div>
          <div style={{ display: 'flex', gap: '.35rem' }}>
            {VIEWS.map((v) => (
              <button key={v.id} className={`btn btn-sm ${view === v.id ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setView(v.id)}><v.icon size={14} /> {v.label}</button>
            ))}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '.75rem', fontWeight: 600, marginBottom: '.35rem', color: 'var(--color-text-secondary)' }}>WHO region</div>
          <select className="form-input" value={region} onChange={(e) => setRegion(e.target.value)} style={{ height: 34, padding: '0 .5rem' }}>
            <option value="">All regions</option>
            {WHO_REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: '.75rem', fontWeight: 600, marginBottom: '.35rem', color: 'var(--color-text-secondary)' }}>Inward window</div>
          <select className="form-input" value={days} onChange={(e) => setDays(Number(e.target.value))} style={{ height: 34, padding: '0 .5rem' }}>
            {[30, 90, 180, 365].map((d) => <option key={d} value={d}>Last {d} days</option>)}
          </select>
        </div>
        {data && (
          <div style={{ marginLeft: 'auto', fontSize: '.82rem', color: 'var(--color-text-secondary)', textAlign: 'right' }}>
            <div><strong>{data.outward_country_count}</strong> countries with outward data</div>
            <div><strong>{data.inward_total}</strong> patient reports ({days}d)</div>
          </div>
        )}
      </div>

      {/* Map + drill-down */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.6fr) minmax(280px, 1fr)', gap: '1rem', alignItems: 'start' }}>
        <div className="card" style={{ padding: '1.25rem' }}>
          {loading
            ? <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-tertiary)' }}>Loading surveillance data…</div>
            : <ChoroplethMap data={mapData} selected={selected} onSelect={loadDetail} />}
          <div style={{ fontSize: '.74rem', color: 'var(--color-text-tertiary)', marginTop: '.6rem' }}>
            Sources: WHO Global Health Observatory · CDC NNDSS · ALAFIA patient reports.
            {activeDisease && <> Outward metric: <em>{activeDisease.who_unit}</em>.</>}
          </div>
        </div>

        <div className="card" style={{ padding: '1.25rem', minHeight: 200 }}>
          {!selected && (
            <div style={{ color: 'var(--color-text-secondary)' }}>
              <h4 style={{ marginTop: 0 }}><MapPin size={16} style={{ verticalAlign: -3 }} /> Highest burden</h4>
              {(data?.countries || []).slice(0, 10).map((c) => (
                <button key={c.iso2} onClick={() => loadDetail(c.iso2)}
                  style={{ display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'center',
                    padding: '.4rem .5rem', border: 'none', background: 'none', cursor: 'pointer', borderRadius: 6,
                    borderBottom: '1px solid var(--color-border)' }}>
                  <span>{flagEmoji(c.iso2)} {c.name}</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: '.78rem', color: 'var(--color-text-tertiary)' }}>{fmt(c.outward)}</span>
                    <span style={{ width: 11, height: 11, borderRadius: 3, background: LEVEL_COLORS[c.level], display: 'inline-block' }} />
                  </span>
                </button>
              ))}
              {!data?.countries?.length && !loading && <p>No data for this selection.</p>}
            </div>
          )}

          {selected && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <h3 style={{ margin: 0 }}>{flagEmoji(selected)} {detail?.name || A2_TO_NAME[selected] || selected}</h3>
                <button className="btn btn-sm btn-secondary" onClick={() => { setSelected(null); setDetail(null); }}><X size={14} /></button>
              </div>
              {detail?.region && <div style={{ fontSize: '.78rem', color: 'var(--color-text-tertiary)', marginBottom: '.5rem' }}>{detail.region} · {detail.disease.icon} {detail.disease.label}</div>}

              {detailLoading && <p style={{ color: 'var(--color-text-tertiary)' }}>Loading…</p>}

              {detail && !detailLoading && (
                <>
                  {/* Outward */}
                  <section style={{ marginTop: '.75rem' }}>
                    <h4 style={{ margin: '0 0 .3rem' }}><Globe size={15} style={{ verticalAlign: -2 }} /> Outward</h4>
                    {detail.outward.value != null ? (
                      <>
                        <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{fmt(detail.outward.value)}</div>
                        <div style={{ fontSize: '.8rem', color: 'var(--color-text-secondary)' }}>
                          {detail.outward.unit} · {detail.outward.year} · {detail.outward.source}
                        </div>
                        <Sparkline series={detail.outward.series} />
                      </>
                    ) : <p style={{ fontSize: '.85rem', color: 'var(--color-text-tertiary)' }}>No WHO data reported.</p>}

                    {detail.cdc_us && (
                      <div style={{ marginTop: '.6rem', paddingTop: '.6rem', borderTop: '1px solid var(--color-border)' }}>
                        <div style={{ fontSize: '.82rem', fontWeight: 600 }}>
                          CDC NNDSS: {fmt(detail.cdc_us.total)} YTD cases ({detail.cdc_us.year} wk {detail.cdc_us.week})
                        </div>
                        <div style={{ marginTop: '.4rem' }}>
                          <USCoverageMap covered={Object.entries(detail.cdc_us.states).filter(([, n]) => n > 0).map(([s]) => s)} />
                        </div>
                      </div>
                    )}
                  </section>

                  {/* Inward */}
                  <section style={{ marginTop: '.9rem' }}>
                    <h4 style={{ margin: '0 0 .3rem' }}><Activity size={15} style={{ verticalAlign: -2 }} /> Inward (patients)</h4>
                    <div style={{ fontSize: '.82rem', color: 'var(--color-text-secondary)' }}>
                      {detail.inward.symptom_log_count} symptom logs · {detail.inward.report_count} community reports
                      {detail.inward.affected ? ` · ${detail.inward.affected} affected` : ''}
                    </div>
                    {detail.inward.clusters.length > 0 ? (
                      <div style={{ marginTop: '.5rem' }}>
                        {detail.inward.clusters.map((c) => {
                          const max = detail.inward.clusters[0].count || 1;
                          return (
                            <div key={c.name} style={{ marginBottom: '.3rem' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.76rem' }}>
                                <span>{c.name}</span><span>{c.count}</span>
                              </div>
                              <div style={{ height: 6, background: 'var(--color-border)', borderRadius: 3 }}>
                                <div style={{ width: `${(c.count / max) * 100}%`, height: '100%', background: '#6366f1', borderRadius: 3 }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : <p style={{ fontSize: '.8rem', color: 'var(--color-text-tertiary)', margin: '.3rem 0 0' }}>No patient symptom activity in this window.</p>}
                  </section>

                  {/* Alerts */}
                  {detail.alerts.length > 0 && (
                    <section style={{ marginTop: '.9rem' }}>
                      <h4 style={{ margin: '0 0 .3rem' }}>Active alerts</h4>
                      {detail.alerts.map((a, i) => (
                        <div key={i} style={{ fontSize: '.8rem', marginBottom: '.35rem' }}>
                          <span style={{ fontWeight: 600 }}>{a.title}</span>
                          <span style={{ color: 'var(--color-text-tertiary)' }}> · {a.source}{a.issued_date ? ` · ${a.issued_date}` : ''}</span>
                          {a.source_url && <a href={a.source_url} target="_blank" rel="noopener noreferrer" style={{ marginLeft: 6 }}><ExternalLink size={12} style={{ verticalAlign: -1 }} /></a>}
                        </div>
                      ))}
                    </section>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
