import { useState, useEffect } from 'react';
import api from '../services/api';
import { Search, AlertTriangle, Clock, RefreshCw } from 'lucide-react';
import BackButton from '../components/BackButton';

const classColors = {
  'Class I': { bg: '#fee2e2', color: '#ef4444', label: 'Class I — Dangerous' },
  'Class II': { bg: '#fef3c7', color: '#f59e0b', label: 'Class II — May Cause Harm' },
  'Class III': { bg: '#dbeafe', color: '#3b82f6', label: 'Class III — Minor Violations' },
};

export default function FDARecalls() {
  const [form, setForm] = useState({ search_term: '', days: 30, limit: 10 });
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSearch(e) {
    e.preventDefault();
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (form.search_term) params.append('search_term', form.search_term);
      params.append('days', form.days);
      params.append('limit', form.limit);
      const { data } = await api.get(`/fda-recalls/?${params}`);
      setResults(data);
    } catch (err) {
      alert('Error searching FDA recalls');
    } finally {
      setLoading(false);
    }
  }

  async function loadRecent() {
    setLoading(true);
    try {
      const { data } = await api.get('/fda-recalls/recent');
      setResults(data);
      setForm(p => ({ ...p, search_term: '', days: 7 }));
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
          <h1 className="page-title">FDA Food Recalls</h1>
        </div>
        <button className="btn btn-secondary" onClick={loadRecent} disabled={loading}>
          <Clock size={16} /> Recent (7 days)
        </button>
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

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {results.results?.map((item, i) => {
              const cls = classColors[item.classification] || classColors['Class III'];
              return (
                <div key={i} className="card" style={{ padding: '1.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', marginBottom: '0.75rem' }}>
                    <h4 style={{ flex: 1 }}>{item.product_description}</h4>
                    <span style={{
                      padding: '2px 10px', borderRadius: 12, fontSize: '0.75rem', fontWeight: 600,
                      background: cls.bg, color: cls.color, whiteSpace: 'nowrap',
                    }}>
                      {cls.label}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', marginBottom: '0.75rem' }}>
                    <AlertTriangle size={16} color="var(--color-warning)" style={{ flexShrink: 0, marginTop: 2 }} />
                    <p style={{ fontSize: '0.9rem' }}>{item.reason}</p>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
                    {item.recalling_firm && <div><strong>Firm:</strong> {item.recalling_firm}</div>}
                    {(item.city || item.state) && <div><strong>Location:</strong> {[item.city, item.state, item.country].filter(Boolean).join(', ')}</div>}
                    {item.recall_date && <div><strong>Date:</strong> {item.recall_date}</div>}
                    {item.status && <div><strong>Status:</strong> {item.status}</div>}
                    {item.recall_number && <div><strong>Recall #:</strong> {item.recall_number}</div>}
                    {item.voluntary_mandated && <div><strong>Type:</strong> {item.voluntary_mandated}</div>}
                  </div>

                  {item.distribution_pattern && (
                    <details style={{ marginTop: '0.75rem' }}>
                      <summary style={{ cursor: 'pointer', fontSize: '0.85rem', color: 'var(--color-info)' }}>
                        Distribution Pattern
                      </summary>
                      <p style={{ marginTop: '0.25rem', fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
                        {item.distribution_pattern}
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
