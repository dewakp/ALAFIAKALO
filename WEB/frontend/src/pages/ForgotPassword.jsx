import PasswordInput from '../components/PasswordInput';
import { useState } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Serves two routes:
 *   /forgot-password              — ask for the email, we send a link
 *   /reset-password?token=…       — the link's destination, set the new password
 *
 * The reset token is never displayed or typed. It used to be a visible field
 * because the API returned it in the request response (DEBUG only) and the email
 * printed it as a "code" to transcribe — a ~200-character JWT. Both are gone: the
 * token now travels only in the emailed link and is read from the query string.
 */
export default function ForgotPassword() {
  const { requestPasswordReset, confirmPasswordReset } = useAuth();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';

  // A token in the URL means we arrived from the email; go straight to the form.
  const [step, setStep] = useState(token ? 'confirm' : 'request');
  const [email, setEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleRequest(e) {
    e.preventDefault();
    setError('');
    if (!email.trim()) { setError('Email is required'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('Please enter a valid email address'); return; }
    setBusy(true);
    try {
      const data = await requestPasswordReset(email);
      setMessage(data.message);
      setStep('sent');
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to request reset'));
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm(e) {
    e.preventDefault();
    setError('');
    if (!token) { setError('This reset link is missing its token. Request a new link below.'); return; }
    if (newPassword.length < 6) { setError('Password must be at least 6 characters'); return; }
    if (newPassword !== confirmPw) { setError('Passwords do not match'); return; }
    setBusy(true);
    try {
      await confirmPasswordReset(token, newPassword);
      setStep('done');
    } catch (err) {
      setError(apiErrorMessage(err, 'This reset link is invalid or has expired. Request a new one.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <h1 className="auth-title">Reset Password</h1>

        {error && (
          <div style={{ color: 'var(--color-danger)', textAlign: 'center', marginBottom: '1rem' }}>
            {error}
          </div>
        )}

        {step === 'request' && (
          <>
            <p className="auth-subtitle">Enter your email and we'll send you a reset link.</p>
            <form onSubmit={handleRequest}>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input
                  className="form-input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }} type="submit" disabled={busy}>
                {busy ? 'Sending…' : 'Send Reset Link'}
              </button>
            </form>
          </>
        )}

        {step === 'sent' && (
          <>
            <p className="auth-subtitle">{message}</p>
            <p className="auth-subtitle" style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
              Open the link in that email to choose a new password. It expires shortly,
              and your current password keeps working until you do.
            </p>
          </>
        )}

        {step === 'confirm' && (
          <>
            <p className="auth-subtitle">Choose a new password for your account.</p>
            <form onSubmit={handleConfirm}>
              <div className="form-group">
                <label className="form-label">New Password</label>
                <PasswordInput
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  minLength={6}
                  autoComplete="new-password"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Confirm Password</label>
                <PasswordInput
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  required
                  minLength={6}
                  autoComplete="new-password"
                />
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }} type="submit" disabled={busy}>
                {busy ? 'Resetting…' : 'Reset Password'}
              </button>
            </form>
          </>
        )}

        {step === 'done' && (
          <>
            <p className="auth-subtitle" style={{ color: 'var(--color-success)' }}>
              Password reset successfully!
            </p>
            <Link to="/login">
              <button className="btn btn-primary" style={{ width: '100%' }}>
                Back to Login
              </button>
            </Link>
          </>
        )}

        <div className="auth-footer">
          {step === 'confirm' || step === 'sent' ? (
            <Link to="/forgot-password">Request a new link</Link>
          ) : (
            <Link to="/login">Back to Sign In</Link>
          )}
        </div>
      </div>
    </div>
  );
}
