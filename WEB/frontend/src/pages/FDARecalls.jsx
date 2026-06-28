import { useState, useEffect } from 'react';
import api from '../services/api';
import { Search, AlertTriangle, Clock, RefreshCw, MapPin } from 'lucide-react';
import BackButton from '../components/BackButton';
import USCoverageMap from '../components/USCoverageMap';
import WorldCoverageMap, { flagEmoji, COUNTRY_NAMES } from '../components/WorldCoverageMap';

const classColors = {
  'Class I': { bg: '#fee2e2', color: '#ef4444', label: 'Class I — Dangerous' },
  'Class II': { bg: '#fef3c7', color: '#f59e0b', label: 'Class II — May Cause Harm' },
  'Class III': { bg: '#dbeafe', color: '#3b82f6', label: 'Class III — Minor Violations' },
};

/** openFDA dates are "YYYYMMDD" → "YYYY-MM-DD". */
function fmtDate(s) {
  if (!s) return s;
  return /^\d{8}$/.test(s) ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}` : s;
}

export default function FDARecalls() {
  const [form, setForm] = useState({ search_term: '', days: 30, limit: 10 });
  const [kind, setKind] = useState('both');      // food | drug | both
  const [mapMode, setMapMode] = useState('aggregate');  // aggregate | per
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSearch(e) {
    e.preventDefault();
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (form.search_term) params.append('search', form.search_term);
      params.append('days', form.days);
      params.append('limit', form.limit);
      params.append('kind', kind);
      const { data } = await api.get(`/fda-recalls/?${params}`);
      setResults(data);
    } catch (err) {
      alert('Error searching FDA recalls');
    } finally {
      setLoading(false);
    }
  }

  // Show recent recalls on first load instead of an empty page.
  useEffect(() => { loadRecent(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  async function loadRecent() {
    setLoading(true);
    try {
      const { data } = await api.get(`/fda-recalls/recent?kind=${kind}`);
      setResults(data);
      setForm(p => ({ ...p, search_term: '', days: 90 }));
    } catch (err) {
      alert('Error loading recent recalls');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">FDA Food &amp; Drug Recalls</h1>
        </div>
        <button className="btn btn-secondary" onClick={loadRecent} disabled={loading}>
          <Clock size={16} /> Recent (90 days)
        </button>
      </div>

      {/* Food / Drug / Both toggle */}
      <div style={{ display: 'flex', gap: '.4rem', marginBottom: '1rem' }}>
        {['both', 'food', 'drug'].map((k) => (
          <button key={k} className={`btn btn-sm ${kind === k ? 'btn-primary' : 'btn-secondary'}`}
            style={{ textTransform: 'capitalize' }}
            onClick={() => setKind(k)}>
            {k === 'both' ? 'Food + Drug' : k}
          </button>
        ))}
      </div>

      <div className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ flex: 2, minWidth: 200 }}>
            <label className="form-label">Search Term</label>
            <input className="form-input" placeholder="e.g. peanut, salmonella..." value={form.search_term}
              onChange={e => setForm(p => ({ ...p, search_term: e.target.value }))} />
          </div>
          <div className="form-group" style={{ flex: 0.5, minWidth: 100 }}>
            <label className="form-label">Days</label>
            <input type="number" className="form-input" min={1} max={365} value={form.days}
              onChange={e => setForm(p => ({ ...p, days: e.target.value }))} />
          </div>
          <div className="form-group" style={{ flex: 0.5, minWidth: 80 }}>
            <label className="form-label">Limit</label>
            <input type="number" className="form-input" min={1} max={100} value={form.limit}
              onChange={e => setForm(p => ({ ...p, limit: e.target.value }))} />
          </div>
          <button className="btn btn-primary" disabled={loading} style={{ height: 42 }}>
            <Search size={16} /> {loading ? 'Searching...' : 'Search'}
          </button>
        </form>
      </div>

      {results && (
        <div>
          <p style={{ marginBottom: '1rem', color: 'var(--color-text-secondary)' }}>
            <strong>{results.total}</strong> recall{results.total !== 1 ? 's' : ''} found
          </p>

          {results.results?.length === 0 && (
            <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
              No recalls found for the given criteria.
            </div>
          )}

          {/* Regions-covered map — toggle between aggregate and per-recall */}
          {results.results?.length > 0 && (() => {
            const states = new Set();
            const countries = new Set();
            let nationwide = false;
            results.results.forEach((r) => {
              const cc = (r.countries && r.countries.length) ? r.countries : (r.country ? [r.country] : []);
              cc.forEach((c) => countries.add(c));
              if (r.nationwide) nationwide = true;
              (r.states || []).forEach((s) => states.add(s));
            });
            const usCovered = countries.has('US');
            return (
              <div className="card" style={{ padding: '1.25rem', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '.5rem', marginBottom: '.75rem' }}>
                  <h4 style={{ display: 'flex', alignItems: 'center', gap: '.4rem', margin: 0 }}>
                    <MapPin size={16} /> Regions covered
                  </h4>
                  <div style={{ display: 'flex', gap: '.35rem' }}>
                    <button className={`btn btn-sm ${mapMode === 'aggregate' ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => setMapMode('aggregate')}>Aggregate</button>
                    <button className={`btn btn-sm ${mapMode === 'per' ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => setMapMode('per')}>Per recall</button>
                  </div>
                </div>
                {mapMode === 'aggregate' ? (
                  <>
                    <div style={{ fontSize: '.82rem', color: 'var(--color-text-secondary)', marginBottom: '.5rem' }}>
                      {[...countries].map((c) => `${flagEmoji(c)} ${COUNTRY_NAMES[c] || c}`).join(' · ') || '—'}
                      {' '}— {results.results.length} recall{results.results.length !== 1 ? 's' : ''}
                    </div>
                    <WorldCoverageMap covered={[...countries]} />
                    {usCovered && (states.size > 0 || nationwide) && (
                      <div style={{ marginTop: '1rem' }}>
                        <div style={{ fontSize: '.8rem', fontWeight: 600, marginBottom: '.4rem' }}>
                          🇺🇸 United States — {nationwide ? 'Nationwide' : `${states.size} state${states.size !== 1 ? 's' : ''}`}
                        </div>
                        <USCoverageMap covered={[...states]} nationwide={nationwide} />
                      </div>
                    )}
                  </>
                ) : (
                  <div style={{ fontSize: '.82rem', color: 'var(--color-text-secondary)' }}>
                    Showing each recall's coverage on its card below.
                  </div>
                )}
              </div>
            );
          })()}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {results.results?.map((item, i) => {
              const cls = classColors[item.classification] || classColors['Class III'];
              return (
                <div key={i} className="card" style={{ padding: '1.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', marginBottom: '0.75rem' }}>
                    <h4 style={{ flex: 1 }}>{item.product_description}</h4>
                    <div style={{ display: 'flex', gap: '.4rem', flexShrink: 0, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                      <span style={{
                        padding: '2px 10px', borderRadius: 12, fontSize: '0.72rem', fontWeight: 700, whiteSpace: 'nowrap',
                        background: item.product_type === 'drug' ? '#ede9fe' : '#dcfce7',
                        color: item.product_type === 'drug' ? '#7c3aed' : '#16a34a',
                      }}>
                        {item.product_type === 'drug' ? '💊 Drug' : '🍽 Food'}
                      </span>
                      <span style={{
                        padding: '2px 10px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 600,
                        background: cls.bg, color: cls.color, whiteSpace: 'nowrap',
                      }}>
                        {cls.label}
                      </span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', marginBottom: '0.75rem' }}>
                    <AlertTriangle size={16} color="var(--color-warning)" style={{ flexShrink: 0, marginTop: 2 }} />
                    <p style={{ fontSize: '0.9rem' }}>{item.reason}</p>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
                    <div><strong>Source:</strong> {flagEmoji(item.country)} {item.source}</div>
                    {item.recalling_firm && <div><strong>Firm:</strong> {item.recalling_firm}</div>}
                    {(item.city || item.state) && <div><strong>Location:</strong> {[item.city, item.state].filter(Boolean).join(', ')}</div>}
                    {(item.recall_initiation_date || item.report_date) && <div><strong>Date:</strong> {fmtDate(item.recall_initiation_date || item.report_date)}</div>}
                    {(item.nationwide || item.states?.length > 0) && (
                      <div><strong>Coverage:</strong> {item.nationwide ? 'Nationwide' : item.states.join(', ')}</div>
                    )}
                    {item.status && <div><strong>Status:</strong> {item.status}</div>}
                    {item.recall_number && <div><strong>Recall #:</strong> {item.recall_number}</div>}
                    {item.voluntary_mandated && <div><strong>Type:</strong> {item.voluntary_mandated}</div>}
                  </div>

                  {mapMode === 'per' && (() => {
                    const cc = (item.countries && item.countries.length) ? item.countries : (item.country ? [item.country] : []);
                    const showUS = item.country === 'US' && (item.nationwide || item.states?.length > 0);
                    if (!showUS && cc.length === 0) return null;
                    return (
                      <div style={{ marginTop: '.75rem' }}>
                        {showUS && <USCoverageMap covered={item.states || []} nationwide={item.nationwide} />}
                        {cc.length > 0 && (
                          <div style={{ marginTop: showUS ? '.5rem' : 0, fontSize: '.85rem' }}>
                            <strong>Countries:</strong> {cc.map((c) => `${flagEmoji(c)} ${COUNTRY_NAMES[c] || c}`).join('  ·  ')}
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {item.url && (
                    <a href={item.url} target="_blank" rel="noopener noreferrer"
                       style={{ display: 'inline-block', marginTop: '.6rem', fontSize: '.82rem', color: 'var(--color-info)', fontWeight: 600 }}>
                      Official notice ↗
                    </a>
                  )}

                  {item.distribution && (
                    <details style={{ marginTop: '0.75rem' }}>
                      <summary style={{ cursor: 'pointer', fontSize: '0.85rem', color: 'var(--color-info)' }}>
                        Distribution Pattern
                      </summary>
                      <p style={{ marginTop: '0.25rem', fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
                        {item.distribution}
                      </p>
                    </details>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
