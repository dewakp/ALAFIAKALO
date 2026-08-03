/**
 * ALAFIA admin console — served at minister.alafia.com.
 *
 * Single operator (dew@6igma.com). Authorization is enforced server-side by
 * `require_admin` on every /admin/* endpoint; this page hiding itself is not
 * the security boundary. A non-admin who loads it simply gets 404s from the API
 * and the "not authorised" panel below.
 */
import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { fmtDateTime } from '../utils/datetime';
import {
  Users, Activity, Cpu, RefreshCw, Search, ShieldAlert, ChevronLeft, ChevronRight,
} from 'lucide-react';

const PAGE = 25;

/* Relative time — "3h ago" reads faster than a timestamp when scanning a table. */
function ago(iso) {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const s = Math.max(0, (Date.now() - then.getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 2592000) return `${Math.floor(s / 86400)}d ago`;
  return `${Math.floor(s / 2592000)}mo ago`;
}

const num = (n) => (n ?? 0).toLocaleString();

function Stat({ label, value, sub, tone }) {
  return (
    <div style={{
      background: 'var(--color-bg-secondary)', borderRadius: 10, padding: '.85rem 1rem',
      border: '1px solid var(--color-border)', minWidth: 150, flex: 1,
    }}>
      <div style={{ fontSize: '.7rem', textTransform: 'uppercase', letterSpacing: '.04em',
        color: 'var(--color-text-tertiary)' }}>{label}</div>
      <div style={{ fontSize: '1.6rem', fontWeight: 700, color: tone || 'var(--color-text-primary)' }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: '.72rem', color: 'var(--color-text-tertiary)' }}>{sub}</div>}
    </div>
  );
}

export default function Admin() {
  const [tab, setTab] = useState('overview');
  const [overview, setOverview] = useState(null);
  const [health, setHealth] = useState(null);
  const [usage, setUsage] = useState(null);
  const [users, setUsers] = useState(null);
  const [q, setQ] = useState('');
  const [sort, setSort] = useState('last_login');
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [denied, setDenied] = useState(false);
  const [loading, setLoading] = useState(false);

  const call = useCallback(async (path) => {
    const { data } = await api.get(path);
    return data;
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      if (tab === 'overview') setOverview(await call('/admin/overview'));
      if (tab === 'health') setHealth(await call('/admin/health'));
      if (tab === 'usage') setUsage(await call('/admin/token-usage?days=30'));
      if (tab === 'users') {
        const params = new URLSearchParams({ limit: PAGE, offset, sort, order: 'desc' });
        if (q.trim()) params.set('q', q.trim());
        setUsers(await call(`/admin/users?${params}`));
      }
    } catch (err) {
      // require_admin returns 404 to non-admins so the console's existence is
      // not confirmed to a logged-in prober.
      if (err?.response?.status === 404) setDenied(true);
      else setError(apiErrorMessage(err, 'Could not load admin data.'));
    } finally { setLoading(false); }
  }, [tab, q, sort, offset, call]);

  useEffect(() => { load(); }, [load]);

  if (denied) {
    return (
      <div style={{ maxWidth: 560, margin: '12vh auto', textAlign: 'center' }}>
        <ShieldAlert size={40} style={{ color: '#ef4444' }} />
        <h2 style={{ marginTop: '1rem' }}>Not authorised</h2>
        <p style={{ color: 'var(--color-text-secondary)' }}>
          This console is restricted to the ALAFIA administrator.
        </p>
      </div>
    );
  }

  const TABS = [
    ['overview', 'Overview', Activity],
    ['users', 'Users', Users],
    ['health', 'App health', RefreshCw],
    ['usage', 'Token usage', Cpu],
  ];

  return (
    <div style={{ maxWidth: 1180, margin: '0 auto', padding: '1.25rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '.75rem', marginBottom: '1rem' }}>
        <h1 style={{ fontSize: '1.45rem', margin: 0 }}>ALAFIA Admin</h1>
        <span style={{ fontSize: '.7rem', padding: '.15rem .5rem', borderRadius: 4,
          background: '#fee2e2', color: '#991b1b', fontWeight: 600 }}>RESTRICTED</span>
        <div style={{ flex: 1 }} />
        <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={13}/> {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      <div style={{ display: 'flex', gap: '.4rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        {TABS.map(([key, label, Icon]) => (
          <button key={key} className={`btn btn-sm ${tab === key ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => { setTab(key); setOffset(0); }}>
            <Icon size={13}/> {label}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ background: '#fef2f2', color: '#991b1b', padding: '.6rem .8rem',
          borderRadius: 6, marginBottom: '1rem', fontSize: '.82rem' }}>{error}</div>
      )}

      {/* ── Overview ── */}
      {tab === 'overview' && overview && (
        <>
          <div style={{ display: 'flex', gap: '.6rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
            <Stat label="Registered users" value={num(overview.users.total)}
              sub={`${num(overview.users.signups_30d)} new in 30d`} />
            <Stat label="Active 24h" value={num(overview.users.logged_in_24h)}
              sub={`${num(overview.users.logged_in_7d)} in 7d · ${num(overview.users.logged_in_30d)} in 30d`} />
            <Stat label="Never signed in" value={num(overview.users.never_logged_in)}
              sub="since last-login tracking began"
              tone={overview.users.never_logged_in ? '#b45309' : undefined} />
            <Stat label="AI interactions 30d" value={num(overview.ai.interactions_30d)}
              sub={`${num(overview.ai.tokens_30d)} tokens`} />
          </div>
          <div className="card" style={{ padding: '.9rem' }}>
            <h3 style={{ marginTop: 0, fontSize: '.9rem' }}>Subscriptions</h3>
            {Object.keys(overview.subscriptions_by_status || {}).length === 0
              ? <div style={{ color: 'var(--color-text-tertiary)', fontSize: '.82rem' }}>None recorded.</div>
              : Object.entries(overview.subscriptions_by_status).map(([status, n]) => (
                <div key={status} style={{ display: 'flex', justifyContent: 'space-between',
                  fontSize: '.85rem', padding: '.2rem 0' }}>
                  <span>{status}</span><strong>{num(n)}</strong>
                </div>
              ))}
          </div>
          <div style={{ fontSize: '.7rem', color: 'var(--color-text-tertiary)', marginTop: '.6rem' }}>
            Generated {fmtDateTime(overview.generated_at)}
          </div>
        </>
      )}

      {/* ── Users ── */}
      {tab === 'users' && (
        <>
          <div style={{ display: 'flex', gap: '.5rem', marginBottom: '.7rem', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: 1, minWidth: 220 }}>
              <Search size={13} style={{ position: 'absolute', left: 9, top: 10,
                color: 'var(--color-text-tertiary)' }}/>
              <input className="form-input" style={{ paddingLeft: 28 }}
                placeholder="Search email or name…" value={q}
                onChange={(e) => { setQ(e.target.value); setOffset(0); }}/>
            </div>
            <select className="form-input" style={{ width: 170 }} value={sort}
              onChange={(e) => { setSort(e.target.value); setOffset(0); }}>
              <option value="last_login">Sort: last login</option>
              <option value="created_at">Sort: signed up</option>
              <option value="tokens">Sort: token usage</option>
              <option value="email">Sort: email</option>
            </select>
          </div>

          {users && (
            <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '.82rem' }}>
                <thead>
                  <tr style={{ textAlign: 'left', color: 'var(--color-text-tertiary)',
                    fontSize: '.7rem', textTransform: 'uppercase' }}>
                    <th style={{ padding: '.6rem .7rem' }}>User</th>
                    <th style={{ padding: '.6rem .7rem' }}>Signed up</th>
                    <th style={{ padding: '.6rem .7rem' }}>Last login</th>
                    <th style={{ padding: '.6rem .7rem' }}>Subscription</th>
                    <th style={{ padding: '.6rem .7rem', textAlign: 'right' }}>Tokens</th>
                    <th style={{ padding: '.6rem .7rem', textAlign: 'right' }}>AI calls</th>
                  </tr>
                </thead>
                <tbody>
                  {users.users.map((u) => (
                    <tr key={u.id} style={{ borderTop: '1px solid var(--color-border)' }}>
                      <td style={{ padding: '.55rem .7rem' }}>
                        <div style={{ fontWeight: 600 }}>{u.full_name || '—'}</div>
                        <div style={{ color: 'var(--color-text-tertiary)', fontSize: '.75rem' }}>
                          {u.email}
                          {!u.is_active && <span style={{ color: '#ef4444' }}> · inactive</span>}
                        </div>
                      </td>
                      <td style={{ padding: '.55rem .7rem', whiteSpace: 'nowrap' }}>{ago(u.created_at) || '—'}</td>
                      <td style={{ padding: '.55rem .7rem', whiteSpace: 'nowrap' }}>
                        {u.last_login
                          ? ago(u.last_login)
                          : <span style={{ color: 'var(--color-text-tertiary)' }}>never</span>}
                      </td>
                      <td style={{ padding: '.55rem .7rem' }}>{u.subscription_status || '—'}</td>
                      <td style={{ padding: '.55rem .7rem', textAlign: 'right' }}>{num(u.tokens_used)}</td>
                      <td style={{ padding: '.55rem .7rem', textAlign: 'right' }}>{num(u.ai_interactions)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem',
                padding: '.6rem .7rem', fontSize: '.78rem' }}>
                <span style={{ color: 'var(--color-text-tertiary)' }}>
                  {offset + 1}–{Math.min(offset + PAGE, users.total)} of {num(users.total)}
                </span>
                <div style={{ flex: 1 }} />
                <button className="btn btn-secondary btn-sm" disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE))}><ChevronLeft size={13}/></button>
                <button className="btn btn-secondary btn-sm" disabled={offset + PAGE >= users.total}
                  onClick={() => setOffset(offset + PAGE)}><ChevronRight size={13}/></button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Health ── */}
      {tab === 'health' && health && (
        <div className="card" style={{ padding: '.9rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem', marginBottom: '.8rem' }}>
            <span style={{
              padding: '.2rem .6rem', borderRadius: 999, fontSize: '.75rem', fontWeight: 700,
              background: health.status === 'ok' ? '#dcfce7' : '#fee2e2',
              color: health.status === 'ok' ? '#166534' : '#991b1b',
            }}>{health.status.toUpperCase()}</span>
            <span style={{ fontSize: '.8rem', color: 'var(--color-text-secondary)' }}>
              {health.app} · {health.version}
            </span>
          </div>
          {health.checks.map((c) => (
            <div key={c.name} style={{ display: 'flex', alignItems: 'baseline', gap: '.6rem',
              padding: '.42rem 0', borderTop: '1px solid var(--color-border)' }}>
              <span style={{ width: 8, height: 8, borderRadius: 999, flexShrink: 0,
                background: c.status === 'ok' ? '#22c55e' : '#ef4444' }}/>
              <strong style={{ fontSize: '.82rem', width: 160 }}>{c.name}</strong>
              <span style={{ fontSize: '.78rem', color: 'var(--color-text-secondary)', flex: 1 }}>
                {String(c.detail)}
              </span>
              <span style={{ fontSize: '.72rem', color: 'var(--color-text-tertiary)' }}>{c.latency_ms} ms</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Token usage ── */}
      {tab === 'usage' && usage && (
        <>
          <div style={{ display: 'flex', gap: '.6rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <Stat label={`Tokens (${usage.window_days}d)`} value={num(usage.totals.tokens)} />
            <Stat label="Interactions" value={num(usage.totals.interactions)} />
          </div>
          <div className="card" style={{ padding: '.9rem', marginBottom: '1rem' }}>
            <h3 style={{ marginTop: 0, fontSize: '.9rem' }}>By model</h3>
            {usage.by_model.length === 0
              ? <div style={{ color: 'var(--color-text-tertiary)', fontSize: '.82rem' }}>No usage in window.</div>
              : usage.by_model.map((m, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between',
                  fontSize: '.82rem', padding: '.25rem 0' }}>
                  <span>{m.provider} · {m.model}</span>
                  <span>{num(m.tokens)} tokens · {num(m.interactions)} calls</span>
                </div>
              ))}
          </div>
          <div className="card" style={{ padding: '.9rem' }}>
            <h3 style={{ marginTop: 0, fontSize: '.9rem' }}>Top users</h3>
            {usage.top_users.length === 0
              ? <div style={{ color: 'var(--color-text-tertiary)', fontSize: '.82rem' }}>No usage in window.</div>
              : usage.top_users.map((u) => (
                <div key={u.user_id} style={{ display: 'flex', justifyContent: 'space-between',
                  fontSize: '.82rem', padding: '.25rem 0' }}>
                  <span>{u.email}</span>
                  <span>{num(u.tokens)} tokens · {num(u.interactions)} calls</span>
                </div>
              ))}
          </div>
          <div style={{ fontSize: '.7rem', color: 'var(--color-text-tertiary)', marginTop: '.6rem' }}>
            {usage.note}
          </div>
        </>
      )}
    </div>
  );
}
