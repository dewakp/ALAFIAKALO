import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Hospital, Search, Link2, RefreshCw, Trash2, CheckCircle2, Loader2 } from 'lucide-react';

/* Patient-portal (MyChart / SMART on FHIR) connections: search any Epic-hosted
   organization (Kaiser Permanente, Trinity Health, …), sign in on the portal's
   own page, then pull labs/vitals/medications/conditions into ALAFIA. */
export default function EHRPortals() {
  const [query, setQuery] = useState('');
  const [orgs, setOrgs] = useState([]);
  const [searching, setSearching] = useState(false);
  const [connections, setConnections] = useState([]);
  const [busyId, setBusyId] = useState(null);       // org/connection id in flight
  const [message, setMessage] = useState(null);      // {type, text}

  const loadConnections = useCallback(async () => {
    try {
      const { data } = await api.get('/ehr/connections');
      setConnections(data.filter(c => c.status === 'connected' || c.org_name));
    } catch { /* section stays empty */ }
  }, []);

  useEffect(() => { loadConnections(); }, [loadConnections]);

  async function search(e) {
    e?.preventDefault();
    setSearching(true); setMessage(null);
    try {
      const { data } = await api.get('/ehr/organizations', { params: { search: query } });
      setOrgs(data);
      if (!data.length) setMessage({ type: 'info', text: 'No organizations matched — try a different name (e.g. "Kaiser", "Trinity").' });
    } catch (err) {
      setMessage({ type: 'error', text: apiErrorMessage(err, 'Search failed') });
    } finally { setSearching(false); }
  }

  async function connect(org) {
    setBusyId(`org-${org.id}`); setMessage(null);
    try {
      const { data } = await api.post('/ehr/connect', { endpoint_id: org.id });
      // Off to the portal's own MyChart sign-in page.
      window.location.href = data.authorize_url;
    } catch (err) {
      setMessage({ type: 'error', text: apiErrorMessage(err, 'Could not start the connection') });
      setBusyId(null);
    }
  }

  async function syncNow(conn) {
    setBusyId(`conn-${conn.id}`); setMessage(null);
    try {
      const { data } = await api.post(`/ehr/connections/${conn.id}/sync`);
      const s = data.synced;
      setMessage({
        type: 'success',
        text: `Synced from ${data.org_name}: ${s.labs} labs, ${s.vitals} vitals, ${s.medications} medications, ${s.conditions} conditions.`,
      });
      loadConnections();
    } catch (err) {
      setMessage({ type: 'error', text: apiErrorMessage(err, 'Sync failed') });
    } finally { setBusyId(null); }
  }

  async function disconnect(conn) {
    if (!confirm(`Disconnect ${conn.org_name || conn.provider}?`)) return;
    await api.delete(`/ehr/connections/${conn.id}`);
    loadConnections();
  }

  const spinner = <Loader2 size={14} style={{ animation: 'spin-anim 1s linear infinite' }} />;

  return (
    <div className="card" style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.25rem' }}>
        <Hospital size={20} style={{ color: 'var(--color-primary)' }} />
        <h2 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 700 }}>Patient Portals (MyChart)</h2>
      </div>
      <p style={{ margin: '0 0 1rem', color: 'var(--color-text-secondary)', fontSize: '.9rem' }}>
        Connect any MyChart portal — Kaiser Permanente, Trinity Health, and hundreds more. You sign in on
        your portal's own page; ALAFIA never sees your portal password.
      </p>

      {message && (
        <div style={{
          padding: '.6rem .9rem', borderRadius: 8, marginBottom: '1rem', fontSize: '.88rem',
          background: message.type === 'error' ? 'rgba(239,68,68,.1)' : message.type === 'success' ? 'rgba(16,185,129,.12)' : 'var(--color-bg)',
          color: message.type === 'error' ? 'var(--color-danger)' : 'inherit',
        }}>
          {message.type === 'success' && <CheckCircle2 size={14} style={{ verticalAlign: '-2px', marginRight: 6, color: '#10b981' }} />}
          {message.text}
        </div>
      )}

      {/* Connected portals */}
      {connections.length > 0 && (
        <div style={{ marginBottom: '1.25rem' }}>
          {connections.map(conn => (
            <div key={conn.id} style={{
              display: 'flex', alignItems: 'center', gap: '.75rem', padding: '.7rem .9rem',
              border: '1px solid var(--color-border)', borderRadius: 8, marginBottom: '.5rem',
            }}>
              <CheckCircle2 size={18} style={{ color: '#10b981', flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: '.92rem' }}>{conn.org_name || conn.provider}</div>
                <div style={{ fontSize: '.78rem', color: 'var(--color-text-secondary)' }}>
                  {conn.last_sync_at
                    ? `Last synced ${new Date(conn.last_sync_at).toLocaleString()}`
                    : 'Connected — not synced yet'}
                </div>
              </div>
              <button className="btn btn-primary btn-sm" disabled={busyId === `conn-${conn.id}`}
                onClick={() => syncNow(conn)}
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {busyId === `conn-${conn.id}` ? spinner : <RefreshCw size={13} />} Sync
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => disconnect(conn)}>
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Organization search */}
      <form onSubmit={search} style={{ display: 'flex', gap: '.5rem', marginBottom: '.75rem' }}>
        <input className="form-input" style={{ flex: 1 }} value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Find your healthcare organization — e.g. Kaiser, Trinity…" />
        <button className="btn btn-primary" type="submit" disabled={searching}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {searching ? spinner : <Search size={15} />} Search
        </button>
      </form>

      {orgs.length > 0 && (
        <div style={{ maxHeight: 320, overflowY: 'auto' }}>
          {orgs.map(org => (
            <div key={org.id} style={{
              display: 'flex', alignItems: 'center', gap: '.75rem',
              padding: '.55rem .75rem', borderBottom: '1px solid var(--color-border)', fontSize: '.9rem',
            }}>
              <span style={{ flex: 1 }}>
                {org.name}
                {org.vendor === 'sandbox' && (
                  <span style={{ marginLeft: 8, fontSize: '.72rem', padding: '1px 8px', borderRadius: 10,
                    background: 'var(--color-bg-secondary, var(--color-bg))', color: 'var(--color-text-secondary)' }}>
                    test portal
                  </span>
                )}
              </span>
              <button className="btn btn-secondary btn-sm" disabled={busyId === `org-${org.id}`}
                onClick={() => connect(org)}
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {busyId === `org-${org.id}` ? spinner : <Link2 size={13} />} Connect
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
