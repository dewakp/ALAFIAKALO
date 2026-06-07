import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function ForgotPassword() {
  const { requestPasswordReset, confirmPasswordReset } = useAuth();
  const [step, setStep] = useState('request'); // 'request' | 'confirm' | 'done'
  const [email, setEmail] = useState('');
  const [token, setToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function handleRequest(e) {
    e.preventDefault();
    setError('');
    if (!email.trim()) { setError('Email is required'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('Please enter a valid email address'); return; }
    try {
      const data = await requestPasswordReset(email);
      setMessage(data.message);
      // In dev mode the token is returned directly
      if (data.reset_token) setToken(data.reset_token);
      setStep('confirm');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to request reset');
    }
  }

  async function handleConfirm(e) {
    e.preventDefault();
    setError('');
    if (!token.trim()) { setError('Reset token is required'); return; }
    if (newPassword.length < 6) { setError('Password must be at least 6 characters'); return; }
    if (newPassword !== confirmPw) {
      setError('Passwords do not match');
      return;
    }
    try {
      await confirmPasswordReset(token, newPassword);
      setStep('done');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to reset password');
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
            <p className="auth-subtitle">Enter your email to receive a reset link.</p>
            <form onSubmit={handleRequest}>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input
                  className="form-input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }} type="submit">
                Send Reset Link
              </button>
            </form>
          </>
        )}

        {step === 'confirm' && (
          <>
            <p className="auth-subtitle">{message}</p>
            <form onSubmit={handleConfirm}>
              <div className="form-group">
                <label className="form-label">Reset Token</label>
                <input
                  className="form-input"
                  type="text"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">New Password</label>
                <input
                  className="form-input"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  minLength={6}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Confirm Password</label>
                <input
                  className="form-input"
                  type="password"
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  required
                  minLength={6}
                />
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }} type="submit">
                Reset Password
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
          <Link to="/login">Back to Sign In</Link>
        </div>
      </div>
    </div>
  );
}
