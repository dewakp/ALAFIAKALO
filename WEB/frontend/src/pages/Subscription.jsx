import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { Sparkles, Check, CreditCard, Loader2, ShieldCheck, Smartphone } from 'lucide-react';
import BackButton from '../components/BackButton';

const MEMBERSHIP_FEATURES = [
  'Unlimited AI health-guide conversations',
  'Advanced labs & vitals trend forecasting',
  'Meal & exercise planners with AI photo analysis',
  'Priority sync across web, iOS & Android',
];

function money(v) {
  return typeof v === 'number' ? `$${v.toFixed(2)}` : '—';
}

export default function Subscription() {
  const [plans, setPlans] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');        // 'stripe' | 'paypal' | 'cancel'
  const [banner, setBanner] = useState(null);  // { type, text }
  const [interval, setBillingInterval] = useState('month'); // 'month' | 'year'
  const [params, setParams] = useSearchParams();

  const load = useCallback(async () => {
    const [{ data: p }, { data: s }] = await Promise.all([
      api.get('/subscription/plans'),
      api.get('/subscription/status'),
    ]);
    setPlans(p);
    setStatus(s);
    setLoading(false);
  }, []);

  // Finalise a redirect back from Stripe / PayPal.
  useEffect(() => {
    const outcome = params.get('status');
    const provider = params.get('provider');
    if (!outcome) { load(); return; }

    if (outcome === 'cancel') {
      setBanner({ type: 'info', text: 'Checkout canceled — no charge was made.' });
      clearReturnParams();
      load();
      return;
    }
    if (outcome === 'success' && provider) {
      const reference_id = params.get('session_id') || params.get('subscription_id') || '';
      (async () => {
        try {
          const { data } = await api.post('/subscription/confirm', { provider, reference_id });
          setStatus(data);
          setBanner({ type: 'success', text: `You're now on ${data.product_name}. Welcome aboard! 🎉` });
        } catch {
          setBanner({ type: 'error', text: 'We couldn’t confirm the payment automatically. It may take a moment — refresh in a bit.' });
        } finally {
          clearReturnParams();
          setLoading(false);
        }
      })();
      // still load plans for display
      api.get('/subscription/plans').then(({ data }) => setPlans(data));
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function clearReturnParams() {
    const next = new URLSearchParams(params);
    ['status', 'provider', 'session_id', 'subscription_id', 'token', 'ba_token'].forEach(k => next.delete(k));
    setParams(next, { replace: true });
  }

  async function startCheckout(provider) {
    setBusy(provider);
    setBanner(null);
    try {
      const { data } = await api.post('/subscription/checkout', { provider, interval });
      window.location.assign(data.checkout_url); // hand off to the hosted checkout
    } catch (e) {
      setBusy('');
      setBanner({ type: 'error', text: e?.response?.data?.detail || 'Could not start checkout.' });
    }
  }

  async function cancel() {
    if (!window.confirm('Cancel your subscription? You’ll keep access until the end of the paid period.')) return;
    setBusy('cancel');
    try {
      const { data } = await api.post('/subscription/cancel', { at_period_end: true });
      setStatus(data);
      setBanner({ type: 'info', text: 'Your subscription will not renew. Access continues until the period ends.' });
    } catch (e) {
      setBanner({ type: 'error', text: e?.response?.data?.detail || 'Could not cancel.' });
    } finally {
      setBusy('');
    }
  }

  const monthlyOpt = plans?.plans?.find(o => o.interval === 'month');
  const annualOpt = plans?.plans?.find(o => o.interval === 'year');
  const hasAnnual = !!annualOpt;
  const selectedOpt = interval === 'year' ? annualOpt : monthlyOpt;
  // web (Stripe) price for the selected interval; fall back to legacy flat rails.
  const webRail = (selectedOpt?.rails || plans?.rails)?.find(r => r.provider === 'stripe');
  // mobile stays monthly-only for now.
  const monthlyRails = monthlyOpt?.rails || plans?.rails || [];
  const androidRail = monthlyRails.find(r => r.provider === 'google_play');
  const iosRail = monthlyRails.find(r => r.provider === 'apple');
  const monthlyWeb = monthlyRails.find(r => r.provider === 'stripe')?.price_usd;
  const annualWeb = annualOpt?.rails?.find(r => r.provider === 'stripe')?.price_usd;
  // annual savings vs paying monthly for a year
  const annualSavings = (typeof monthlyWeb === 'number' && typeof annualWeb === 'number')
    ? Math.max(0, Math.round(monthlyWeb * 12 - annualWeb)) : 0;
  const perPeriod = interval === 'year' ? '/ year' : '/ month';
  const entitled = status?.entitled;

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: '1rem' }}>
      <BackButton />
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <Sparkles size={26} color="#7c4dff" />
        <h1 style={{ margin: 0 }}>{plans?.product_name || 'ALAFIA Membership'}</h1>
      </div>
      <p style={{ color: '#666', marginTop: 0 }}>
        Unlock the full ALAFIA experience across every device.
      </p>

      {banner && (
        <div style={{
          padding: '10px 14px', borderRadius: 10, marginBottom: 16, fontSize: 14,
          background: banner.type === 'success' ? '#e8f5e9' : banner.type === 'error' ? '#ffebee' : '#e3f2fd',
          color: banner.type === 'error' ? '#c62828' : '#1b5e20',
        }}>
          {banner.text}
        </div>
      )}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
          <Loader2 className="spin" size={28} />
        </div>
      ) : entitled ? (
        <div style={{ border: '1px solid #c8e6c9', background: '#f1f8f4', borderRadius: 14, padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <ShieldCheck size={22} color="#2e7d32" />
            <strong style={{ fontSize: 18 }}>You’re subscribed</strong>
            <span style={{
              marginLeft: 'auto', fontSize: 12, fontWeight: 700, textTransform: 'uppercase',
              background: '#2e7d32', color: '#fff', padding: '3px 10px', borderRadius: 20,
            }}>
              {status.status}
            </span>
          </div>
          <div style={{ fontSize: 14, color: '#333', lineHeight: 1.8 }}>
            <div>Plan: <strong>{status.product_name}</strong> · {money(status.price_usd)}{status.plan === 'plus_annual' ? '/yr' : '/mo'}</div>
            <div>Billing via: <strong>{prettyProvider(status.provider)}</strong></div>
            {status.current_period_end && (
              <div>
                {status.cancel_at_period_end ? 'Access ends' : 'Renews'} on{' '}
                <strong>{new Date(status.current_period_end).toLocaleDateString()}</strong>
              </div>
            )}
          </div>
          {(status.provider === 'stripe' || status.provider === 'paypal') && !status.cancel_at_period_end && (
            <button onClick={cancel} disabled={busy === 'cancel'} style={secondaryBtn}>
              {busy === 'cancel' ? 'Canceling…' : 'Cancel subscription'}
            </button>
          )}
          {(status.provider === 'google_play' || status.provider === 'apple') && (
            <p style={{ fontSize: 13, color: '#666', marginTop: 12 }}>
              Manage or cancel this subscription in your{' '}
              {status.provider === 'google_play' ? 'Google Play' : 'App Store'} account settings.
            </p>
          )}
        </div>
      ) : (
        <div style={{ border: '1px solid #e0e0e0', borderRadius: 14, padding: 24 }}>
          {hasAnnual && (
            <div style={billingToggle}>
              <button onClick={() => setBillingInterval('month')} style={toggleBtn(interval === 'month')}>
                Monthly
              </button>
              <button onClick={() => setBillingInterval('year')} style={toggleBtn(interval === 'year')}>
                Annual{annualSavings > 0 ? ` · save $${annualSavings}` : ''}
              </button>
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontSize: 40, fontWeight: 800 }}>{money(webRail?.price_usd)}</span>
            <span style={{ color: '#666' }}>{perPeriod}</span>
          </div>
          {interval === 'year' && typeof annualWeb === 'number' && (
            <div style={{ color: '#2e7d32', fontSize: 13, marginTop: 2 }}>
              ≈ ${(annualWeb / 12).toFixed(2)}/mo, billed yearly
              {annualSavings > 0 ? ` — save $${annualSavings} vs monthly` : ''}
            </div>
          )}
          <ul style={{ listStyle: 'none', padding: 0, margin: '18px 0' }}>
            {MEMBERSHIP_FEATURES.map(f => (
              <li key={f} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 10 }}>
                <Check size={18} color="#2e7d32" style={{ flexShrink: 0, marginTop: 2 }} />
                <span style={{ fontSize: 15 }}>{f}</span>
              </li>
            ))}
          </ul>

          <button onClick={() => startCheckout('stripe')} disabled={!!busy} style={primaryBtn}>
            {busy === 'stripe' ? <Loader2 className="spin" size={18} /> : <CreditCard size={18} />}
            Pay with card
          </button>
          <button onClick={() => startCheckout('paypal')} disabled={!!busy} style={paypalBtn}>
            {busy === 'paypal' ? <Loader2 className="spin" size={18} /> : <span style={{ fontWeight: 800, fontStyle: 'italic' }}>PayPal</span>}
            {busy !== 'paypal' && <span>Checkout</span>}
          </button>

          <p style={{ fontSize: 12, color: '#999', marginTop: 14, textAlign: 'center' }}>
            Secure checkout. Cancel anytime.
          </p>

          <div style={{ borderTop: '1px solid #eee', marginTop: 18, paddingTop: 14, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <Smartphone size={16} color="#888" style={{ marginTop: 2, flexShrink: 0 }} />
            <p style={{ fontSize: 12, color: '#888', margin: 0 }}>
              Prefer to subscribe in the app? {money(androidRail?.price_usd)}/mo on Android (Google Play)
              and {money(iosRail?.price_usd)}/mo on iOS (App Store).
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function prettyProvider(p) {
  return { stripe: 'Card (Stripe)', paypal: 'PayPal', google_play: 'Google Play', apple: 'App Store' }[p] || p;
}

const primaryBtn = {
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  width: '100%', padding: '13px', border: 'none', borderRadius: 10, cursor: 'pointer',
  background: '#7c4dff', color: '#fff', fontSize: 16, fontWeight: 600, marginBottom: 10,
};
const paypalBtn = {
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
  width: '100%', padding: '13px', border: '1px solid #ffc439', borderRadius: 10, cursor: 'pointer',
  background: '#ffc439', color: '#003087', fontSize: 16, fontWeight: 600,
};
const secondaryBtn = {
  marginTop: 16, padding: '9px 16px', border: '1px solid #ef9a9a', borderRadius: 8,
  background: 'transparent', color: '#c62828', cursor: 'pointer', fontSize: 14,
};
const billingToggle = {
  display: 'flex', gap: 6, padding: 4, background: '#f2f0fa', borderRadius: 10,
  marginBottom: 16, width: 'fit-content',
};
const toggleBtn = (active) => ({
  padding: '7px 16px', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 14,
  fontWeight: 600, background: active ? '#7c4dff' : 'transparent', color: active ? '#fff' : '#555',
});
