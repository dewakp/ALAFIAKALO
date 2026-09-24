import { useEffect, useRef, useState } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { LogIn, Mail, Phone, Loader2 } from 'lucide-react';
import PasswordInput from '../components/PasswordInput';
import LanguageSwitcher from '../components/LanguageSwitcher';
import {
  renderGoogleButton,
  signInWithApple,
  isAppleConfigured,
  oidcErrorMessage,
} from '../services/oidc';
import { t } from '../i18n';

/* Apple's glyph (lucide has no Apple logo). There is no Google glyph any more:
   Google renders its own button, so drawing one here would be dead markup. */
const AppleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8.79-.16 2.09-.86 3.63-.74 1.85.15 3.24.88 4.15 2.21-3.81 2.28-3.2 7.29.5 8.71-.7 1.44-1.6 2.86-3.36 3.99zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>
  </svg>
);

export default function Login() {
  const { login, loginWithOIDC } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState('email');           // 'email' | 'phone'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');                 // which action is in flight
  const googleBtnRef = useRef(null);

  // Google's button is rendered BY Google — it will not hand an ID token to an
  // arbitrary click. Mount it once, and report a blocked script rather than
  // leaving an empty space where a button should be: an extension or a network
  // policy can stop it loading, and silence there is indistinguishable from the
  // dead control this whole change exists to remove.
  useEffect(() => {
    let cleanup = () => {};
    if (googleBtnRef.current) {
      renderGoogleButton(
        googleBtnRef.current,
        handleGoogleToken,
        (err) => setError(oidcErrorMessage(err, t('Login.sign_in_failed'))),
      ).then((fn) => { cleanup = fn; });
    }
    return () => cleanup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function done() { navigate('/', { replace: true }); }

  async function handleEmailSubmit(e) {
    e.preventDefault();
    setError('');
    if (!email.trim()) { setError(t('Login.email_is_required')); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError(t('Login.please_enter_a_valid_email_address')); return; }
    if (password.length < 6) { setError(t('Login.password_must_be_at_least_6_characters')); return; }
    setBusy('email');
    try {
      await login(email, password);
      done();
    } catch (err) {
      setError(apiErrorMessage(err, t('Login.login_failed')));
    } finally { setBusy(''); }
  }

  async function handlePhoneSubmit(e) {
    e.preventDefault();
    setError('');
    const p = phone.trim();
    if (!/^\+?[0-9][0-9\s\-()]{6,}$/.test(p)) {
      setError(t('Login.enter_a_valid_phone_number_e_g'));
      return;
    }
    if (password.length < 6) { setError(t('Login.password_must_be_at_least_6_characters')); return; }
    setBusy('phone');
    try {
      // Phone is just another identifier for the PostgreSQL IdP (no OTP/Firebase).
      await login(p, password);
      done();
    } catch (err) {
      setError(apiErrorMessage(err, t('Login.login_failed')));
    } finally { setBusy(''); }
  }

  /* Google and Apple are NOT symmetrical, and treating them alike is how this
     breaks: Google only issues an ID token through its OWN rendered button, so
     it arrives as a callback; Apple signs in from any control.

     An error with no `.response` came from the provider in the browser; one
     with a `.response` came back from our API. They need different wording —
     "the popup was closed" and "that account is not permitted" are not the
     same event. */
  async function exchange(provider, idToken) {
    try {
      await loginWithOIDC(provider, idToken);
      done();
    } catch (err) {
      setError(apiErrorMessage(err, t('Login.login_failed')));
    } finally { setBusy(''); }
  }

  /** Google's own button hands us the credential. */
  function handleGoogleToken(idToken) {
    setError('');
    setBusy('google');
    exchange('google', idToken);
  }

  async function handleApple() {
    setError('');
    setBusy('apple');
    try {
      const idToken = await signInWithApple();
      await exchange('apple', idToken);
    } catch (err) {
      setError(oidcErrorMessage(err, t('Login.sign_in_failed')));
      setBusy('');
    }
  }

  const spinner = <Loader2 size={16} style={{ animation: 'spin-anim 1s linear infinite' }} />;
  const tabStyle = (active) => ({
    flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    padding: '10px 0', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: '.95rem',
    border: 'none',
    background: active ? 'var(--color-primary)' : 'transparent',
    color: active ? '#fff' : 'var(--color-text)',
  });
  const socialBtnStyle = {
    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
    padding: '11px 0', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: '.95rem',
    border: '1px solid var(--color-border)', background: 'var(--color-surface)', color: 'var(--color-text)',
    marginBottom: '.75rem',
  };

  return (
    <div className="auth-page">
      <div style={{ width: '100%', maxWidth: 480 }}>
        {/* ── Page header ── */}
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <h1 style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12,
            fontSize: '2.2rem', fontWeight: 800, margin: 0 }}>
            <LogIn size={32} style={{ color: 'var(--color-primary)' }} /> {t('Login.login_to_alafia')}
          </h1>
          <p style={{ color: 'var(--color-text-secondary)', marginTop: 8, fontSize: '1.05rem' }}>
            {t('Login.access_your_wellness_dashboard')}
          </p>
        </div>

        <div className="card auth-card" style={{ maxWidth: 480 }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 1.25rem' }}>{t('Login.welcome_back')}</h2>

          {/* ── Email / Phone tabs ── */}
          <div style={{ display: 'flex', gap: 8, marginBottom: '1.25rem', paddingBottom: '1.25rem',
            borderBottom: '1px solid var(--color-border)' }}>
            <button type="button" style={tabStyle(mode === 'email')}
              onClick={() => { setMode('email'); setError(''); }}>
              <Mail size={17} /> {t('Login.email')}
            </button>
            <button type="button" style={tabStyle(mode === 'phone')}
              onClick={() => { setMode('phone'); setError(''); }}>
              <Phone size={17} /> {t('Login.phone')}
            </button>
          </div>

          {error && (
            <div style={{ color: 'var(--color-danger)', textAlign: 'center', marginBottom: '1rem' }}>
              {error}
            </div>
          )}

          {/* ── Email login ── */}
          {mode === 'email' && (
            <form onSubmit={handleEmailSubmit}>
              <div className="form-group">
                <label className="form-label" htmlFor="login-email">{t('Login.email_address')}</label>
                <input id="login-email" className="form-input" type="email" placeholder="your@email.com"
                  value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="login-password">{t('Login.password')}</label>
                <PasswordInput id="login-password"
                  value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }} type="submit" disabled={!!busy}>
                {busy === 'email' ? spinner : null} {t('Login.login_with_email')}
              </button>
            </form>
          )}

          {/* ── Phone login (phone + password → PostgreSQL IdP) ── */}
          {mode === 'phone' && (
            <form onSubmit={handlePhoneSubmit}>
              <div className="form-group">
                <label className="form-label">{t('Login.phone_number')}</label>
                <input className="form-input" type="tel" placeholder="+1 555 123 4567"
                  value={phone} onChange={(e) => setPhone(e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Login.password')}</label>
                <PasswordInput
                  value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }} type="submit" disabled={!!busy}>
                {busy === 'phone' ? spinner : null} {t('Login.login_with_phone')}
              </button>
            </form>
          )}

          {/* ── Social sign-in ──
              Google renders its own button into this container; Apple signs in
              from ours. Apple is offered ONLY when a Services ID is configured:
              it was never configured as a provider at all, so the button that
              shipped could not work, and a control that cannot work is worse
              than no control (§3ar). */}
          <div style={{ margin: '1.25rem 0 0', paddingTop: '1.25rem', borderTop: '1px solid var(--color-border)' }}>
            <div ref={googleBtnRef} style={{ display: 'flex', justifyContent: 'center' }} />
            {isAppleConfigured() && (
              <button type="button" style={{ ...socialBtnStyle, marginTop: 10 }}
                disabled={!!busy} onClick={handleApple}>
                {busy === 'apple' ? spinner : <AppleIcon />} {t('Login.sign_in_with_apple')}
              </button>
            )}
          </div>

          <div className="auth-footer">
            {t('Login.don_t_have_an_account')} <Link to="/register">{t('Login.register_here')}</Link>
            <br />
            <Link to="/forgot-password">{t('Login.forgot_password')}</Link>
            <LanguageSwitcher />
          </div>
        </div>
      </div>
    </div>
  );
}
