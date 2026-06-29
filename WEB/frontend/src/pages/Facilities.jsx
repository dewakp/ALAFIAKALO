import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { Building2, Search, MapPin, Users, X, ChevronRight, Phone, BadgeCheck } from 'lucide-react';
import BackButton from '../components/BackButton';

const PAGE_SIZE = 10;
const TYPES = [
  ['', 'All types'], ['facility', 'Practices / other'], ['hospital', 'Hospitals'],
  ['clinic', 'Clinics'], ['pharmacy', 'Pharmacies'], ['dental', 'Dental'],
  ['doctors_office', "Doctor's offices"],
];

export default function Facilities() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState('');
  const [ftype, setFtype] = useState('');
  const [city, setCity] = useState('');
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);

  const [selected, setSelected] = useState(null);
  const [roster, setRoster] = useState(null);
  const [rosterLoading, setRosterLoading] = useState(false);

  const load = useCallback(async (pg = 0) => {
    setLoading(true);
    try {
      const params = { limit: PAGE_SIZE, offset: pg * PAGE_SIZE };
      if (q) params.q = q;
      if (ftype) params.facility_type = ftype;
      if (city) params.city = city;
      const { data } = await api.get('/facilities/', { params });
      setItems(data);
      setHasMore(data.length === PAGE_SIZE);
      setPage(pg);
    } catch { setItems([]); } finally { setLoading(false); }
  }, [q, ftype, city]);

  useEffect(() => { load(0); /* eslint-disable-next-line */ }, []);

  async function openFacility(f) {
    setSelected(f); setRoster(null); setRosterLoading(true);
    try {
      const { data } = await api.get(`/facilities/${f.id}/clinicians`);
      setRoster(data);
    } catch { setRoster([]); } finally { setRosterLoading(false); }
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title"><Building2 size={20} style={{ verticalAlign: -3, marginRight: 6 }} />Facility Directory</h1>
        </div>
      </div>
      <p style={{ color: 'var(--color-text-secondary)', marginBottom: '1rem', maxWidth: 720 }}>
        Healthcare <strong>places</strong> — hospitals, clinics, pharmacies, and practice
        locations. Click a facility to see the clinicians who practice there.
      </p>

      <div className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <input className="form-input" style={{ flex: 1, minWidth: 200 }} placeholder="Search by name…"
            value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && load(0)} />
          <input className="form-input" style={{ width: 160 }} placeholder="City"
            value={city} onChange={e => setCity(e.target.value)} onKeyDown={e => e.key === 'Enter' && load(0)} />
          <select className="form-input" style={{ width: 180 }} value={ftype} onChange={e => setFtype(e.target.value)}>
            {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button className="btn btn-primary" onClick={() => load(0)} disabled={loading}>
            <Search size={16} /> Search
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(280px, 1fr)', gap: '1rem', alignItems: 'start' }}>
        {/* List */}
        <div>
          {loading ? <div className="card" style={{ padding: '2rem', textAlign: 'center', color: '#999' }}>Loading…</div>
            : items.length === 0 ? <div className="card" style={{ padding: '2rem', textAlign: 'center', color: '#888' }}>No facilities found.</div>
            : (
              <div style={{ display: 'grid', gap: '0.6rem' }}>
                {items.map(f => (
                  <div key={f.id} className="card" style={{ padding: '0.9rem', cursor: 'pointer', borderLeft: selected?.id === f.id ? '3px solid var(--color-primary, #f97316)' : '3px solid transparent' }}
                    onClick={() => openFacility(f)}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
                      <div>
                        <h4 style={{ margin: 0 }}>{f.name}</h4>
                        <div style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)', marginTop: 2, textTransform: 'capitalize' }}>
                          {f.facility_type?.replace('_', ' ')}
                          {(f.city || f.state_province) && <> · <MapPin size={12} style={{ verticalAlign: -1 }} /> {[f.city, f.state_province].filter(Boolean).join(', ')}</>}
                        </div>
                      </div>
                      <ChevronRight size={16} style={{ color: '#bbb', flexShrink: 0 }} />
                    </div>
                  </div>
                ))}
              </div>
            )}

          {(page > 0 || hasMore) && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', alignItems: 'center', marginTop: '1rem' }}>
              <button className="btn btn-secondary btn-sm" disabled={page === 0 || loading} onClick={() => load(page - 1)}>
                <ChevronRight size={14} style={{ transform: 'rotate(180deg)' }} /> Prev
              </button>
              <span style={{ fontSize: '0.85rem', color: '#666' }}>Page {page + 1}</span>
              <button className="btn btn-secondary btn-sm" disabled={!hasMore || loading} onClick={() => load(page + 1)}>
                Next <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>

        {/* Roster panel */}
        <div className="card" style={{ padding: '1.25rem', minHeight: 200 }}>
          {!selected ? (
            <div style={{ color: 'var(--color-text-secondary)', textAlign: 'center', paddingTop: '2rem' }}>
              <Users size={40} style={{ opacity: 0.3 }} />
              <p>Select a facility to see its clinicians.</p>
            </div>
          ) : (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <h3 style={{ margin: 0 }}>{selected.name}</h3>
                <button className="btn btn-sm btn-secondary" onClick={() => { setSelected(null); setRoster(null); }}><X size={14} /></button>
              </div>
              <div style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)', margin: '0.25rem 0 0.75rem' }}>
                {[selected.address_line1, selected.city, selected.state_province, selected.postal_code].filter(Boolean).join(', ')}
                {selected.phone && <><br /><Phone size={12} style={{ verticalAlign: -1 }} /> {selected.phone}</>}
                {selected.location_precision && <> · <span title="map location precision">{selected.location_precision === 'exact' ? '📍 exact location' : '≈ approx location'}</span></>}
              </div>
              <h4 style={{ margin: '0 0 0.4rem' }}><Users size={15} style={{ verticalAlign: -2 }} /> Clinicians who practice here</h4>
              {rosterLoading && <p style={{ color: '#999' }}>Loading…</p>}
              {roster && roster.length === 0 && !rosterLoading && <p style={{ color: '#999', fontSize: '0.85rem' }}>No clinicians linked to this facility.</p>}
              {roster && roster.map(c => (
                <div key={c.id} style={{ padding: '0.45rem 0', borderBottom: '1px solid var(--color-border, #eee)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem' }}>
                    <strong style={{ fontSize: '0.9rem' }}>{c.full_name}{c.credentials ? `, ${c.credentials}` : ''}</strong>
                    {c.credential_verified && <BadgeCheck size={15} style={{ color: '#22c55e', flexShrink: 0 }} title="Verified" />}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                    {c.specialty || c.clinician_role}
                  </div>
                </div>
              ))}
              {roster && roster.length > 0 && (
                <div style={{ fontSize: '0.78rem', color: '#999', marginTop: '0.6rem' }}>{roster.length} clinician{roster.length !== 1 ? 's' : ''}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
