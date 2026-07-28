import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles, X } from 'lucide-react';
import api from '../services/api';

/**
 * App-wide nudge for grandfathered users whose complimentary access is winding
 * down. A grandfather comp reads as: entitled, no payment provider, with an end
 * date. We show a countdown + CTA to subscribe. Dismissal is per-day (it comes
 * back tomorrow) so it stays gentle but present until they convert or it lapses.
 */
export default function MembershipNudge() {
  const [info, setInfo] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get('/subscription/status')
      .then(({ data }) => { if (!cancelled) setInfo(data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  if (!info) return null;
  const isComp = info.entitled && info.provider === 'none' && info.current_period_end;
  if (!isComp) return null;

  const end = new Date(info.current_period_end);
  const days = Math.ceil((end - Date.now()) / 86400000);
  if (days < 0) return null;

  const today = new Date().toISOString().slice(0, 10);
  const key = `alafia_nudge_${end.toISOString().slice(0, 10)}_${today}`;
  if (dismissed || (typeof localStorage !== 'undefined' && localStorage.getItem(key))) return null;

  return (
    <div style={wrap}>
      <Sparkles size={18} color="#7c4dff" style={{ flexShrink: 0 }} />
      <span style={{ flex: 1, fontSize: 14, lineHeight: 1.4 }}>
        Your complimentary access ends in <strong>{days} day{days === 1 ? '' : 's'}</strong>
        {' '}({end.toLocaleDateString()}). Subscribe to keep your ALAFIA Membership.
      </span>
      <Link to="/subscription" style={cta}>Choose a plan</Link>
      <button
        onClick={() => { try { localStorage.setItem(key, '1'); } catch { /* ignore */ } setDismissed(true); }}
        style={xBtn}
        aria-label="Dismiss"
      >
        <X size={16} />
      </button>
    </div>
  );
}

const wrap = {
  display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
  margin: '0 0 12px', borderRadius: 10, background: '#f3f0ff', border: '1px solid #e0d7ff',
};
const cta = {
  background: '#7c4dff', color: '#fff', padding: '7px 14px', borderRadius: 8,
  fontSize: 13, fontWeight: 600, textDecoration: 'none', whiteSpace: 'nowrap',
};
const xBtn = { background: 'transparent', border: 'none', cursor: 'pointer', color: '#888', display: 'flex' };
