import { useState } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { LogIn, Mail, Phone, Loader2 } from 'lucide-react';
import PasswordInput from '../components/PasswordInput';
import {
  signInWithGoogle,
  signInWithApple,
  firebaseErrorMessage,
} from '../services/firebase';

/* Simple brand glyphs (lucide has no Google/Apple logos) */
const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z"/>
    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z"/>
    <path fill="#FBBC05" d="M5.84 14.1A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.44.34-2.1V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z"/>
    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.16-3.16A11 11 0 0 0 2.18 7.06L5.84 9.9C6.71 7.31 9.14 5.38 12 5.38z"/>
  </svg>
);
const AppleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M17.05 20.28c-.98.95-2.05.8-3.08.35-1.09-.46-2.09-.48-3.24 0-1.44.62-2.2.44-3.06-.35C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8.79-.16 2.09-.86 3.63-.74 1.85.15 3.24.88 4.15 2.21-3.81 2.28-3.2 7.29.5 8.71-.7 1.44-1.6 2.86-3.36 3.99zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z"/>
  </svg>
);

export default function Login() {
  const { login, loginWithFirebase } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState('email');           // 'email' | 'phone'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');                 // which action is in flight

  function done() { navigate('/', { replace: true }); }

  async function handleEmailSubmit(e) {
    e.preventDefault();
    setError('');
    if (!email.trim()) { setError('Email is required'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('Please enter a valid email address'); return; }
    if (password.length < 6) { setError('Password must be at least 6 characters'); return; }
    setBusy('email');
    try {
      await login(email, password);
      done();
    } catch (err) {
      setError(apiErrorMessage(err, 'Login failed'));
    } finally { setBusy(''); }
  }

  async function handlePhoneSubmit(e) {
    e.preventDefault();
    setError('');
    const p = phone.trim();
    if (!/^\+?[0-9][0-9\s\-()]{6,}$/.test(p)) {
      setError('Enter a valid phone number, e.g. +15551234567');
      return;
    }
    if (password.length < 6) { setError('Password must be at least 6 characters'); return; }
    setBusy('phone');
    try {
      // Phone is just another identifier for the PostgreSQL IdP (no OTP/Firebase).
      await login(p, password);
      done();
    } catch (err) {
      setError(apiErrorMessage(err, 'Login failed'));
    } finally { setBusy(''); }
  }

  async function handleSocial(providerName) {
    setError('');
    setBusy(providerName);
    try {
      const idToken = providerName === 'google' ? await signInWithGoogle() : await signInWithApple();
      await loginWithFirebase(idToken);
      done();
    } catch (err) {
      setError(err?.code ? firebaseErrorMessage(err, 'Sign-in failed.') : apiErrorMessage(err, 'Login failed'));
    } finally { setBusy(''); }
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
            <LogIn size={32} style={{ color: 'var(--color-primary)' }} /> Login to Alafia
          </h1>
          <p style={{ color: 'var(--color-text-secondary)', marginTop: 8, fontSize: '1.05rem' }}>
            Access your wellness dashboard.
          </p>
        </div>

        <div className="card auth-card" style={{ maxWidth: 480 }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0 0 1.25rem' }}>Welcome Back</h2>

          {/* ── Email / Phone tabs ── */}
          <div style={{ display: 'flex', gap: 8, marginBottom: '1.25rem', paddingBottom: '1.25rem',
            borderBottom: '1px solid var(--color-border)' }}>
            <button type="button" style={tabStyle(mode === 'email')}
              onClick={() => { setMode('email'); setError(''); }}>
              <Mail size={17} /> Email
            </button>
            <button type="button" style={tabStyle(mode === 'phone')}
              onClick={() => { setMode('phone'); setError(''); }}>
              <Phone size={17} /> Phone
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
                <label className="form-label" htmlFor="login-email">Email Address</label>
                <input id="login-email" className="form-input" type="email" placeholder="your@email.com"
                  value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="login-password">Password</label>
                <PasswordInput id="login-password"
                  value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }} type="submit" disabled={!!busy}>
                {busy === 'email' ? spinner : null} Login with Email
              </button>
            </form>
          )}

          {/* ── Phone login (phone + password → PostgreSQL IdP) ── */}
          {mode === 'phone' && (
            <form onSubmit={handlePhoneSubmit}>
              <div className="form-group">
                <label className="form-label">Phone Number</label>
                <input className="form-input" type="tel" placeholder="+1 555 123 4567"
                  value={phone} onChange={(e) => setPhone(e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">Password</label>
                <PasswordInput
                  value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }} type="submit" disabled={!!busy}>
                {busy === 'phone' ? spinner : null} Login with Phone
              </button>
            </form>
          )}

          {/* ── Social sign-in ── */}
          <div style={{ margin: '1.25rem 0 0', paddingTop: '1.25rem', borderTop: '1px solid var(--color-border)' }}>
            <button type="button" style={socialBtnStyle} disabled={!!busy} onClick={() => handleSocial('google')}>
              {busy === 'google' ? spinner : <GoogleIcon />} Sign in with Google
            </button>
            <button type="button" style={socialBtnStyle} disabled={!!busy} onClick={() => handleSocial('apple')}>
              {busy === 'apple' ? spinner : <AppleIcon />} Sign in with Apple
            </button>
          </div>

          <div className="auth-footer">
            Don't have an account? <Link to="/register">Register here</Link>
            <br />
            <Link to="/forgot-password">Forgot Password?</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
