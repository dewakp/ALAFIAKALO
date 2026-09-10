import PasswordInput from '../components/PasswordInput';
import { useState } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Register() {
  const { register } = useAuth();
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [dateOfBirth, setDateOfBirth] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    // Client-side validation
    // The API enforces the same 3-character rule; this is only the kinder,
    // faster version of it. Naming the field that is wrong matters — a single
    // "name is required" leaves the user guessing which of two boxes.
    if (firstName.trim().length < 3) { setError('First name must be at least 3 characters'); return; }
    if (lastName.trim().length < 3) { setError('Last name must be at least 3 characters'); return; }
    if (!email.trim()) { setError('Email is required'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('Please enter a valid email address'); return; }
    if (password.length < 6) { setError('Password must be at least 6 characters'); return; }
    // Checked here for a fast, kind error; the API enforces it regardless —
    // clients are UX, not enforcement.
    if (!dateOfBirth) { setError('Date of birth is required'); return; }
    if (new Date(dateOfBirth) > new Date()) { setError('Date of birth cannot be in the future'); return; }
    // One click, one account. Without this the button fires a POST per click:
    // production logs show four register requests inside 300ms, the first
    // creating the account and the rest racing the unique index, then the
    // retries tripping the auth rate limiter into 429s.
    if (submitting) return;
    setSubmitting(true);
    try {
      await register(email, password,
                     { firstName: firstName.trim(), lastName: lastName.trim() },
                     phone, dateOfBirth,
                     Intl.DateTimeFormat().resolvedOptions().locale?.split('-')[1] || null);
    } catch (err) {
      setError(apiErrorMessage(err, 'Registration failed'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <h1 className="auth-title">ALAFIA</h1>
        <p className="auth-subtitle">Create your account</p>
        {/* §3ad: a page needs BOTH a route and a link. /register is where
            people land, so the two-step flow is reachable from here rather
            than only from a URL somebody has to know. */}
        <p className="auth-alt" style={{ marginTop: 0, marginBottom: '1rem' }}>
          Joining as a member? <Link to="/signup">Start here</Link>
        </p>
        {error && (
          <div style={{ color: 'var(--color-danger)', textAlign: 'center', marginBottom: '1rem' }}>
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <div className="name-row">
            <div className="form-group">
              <label className="form-label" htmlFor="register-first">First Name</label>
              <input
                id="register-first"
                className="form-input"
                type="text"
                autoComplete="given-name"
                minLength={3}
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="register-last">Last Name</label>
              <input
                id="register-last"
                className="form-input"
                type="text"
                autoComplete="family-name"
                minLength={3}
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="register-email">Email</label>
            <input
              id="register-email"
              className="form-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="register-dob">Date of Birth</label>
            <input
              id="register-dob"
              className="form-input"
              type="date"
              value={dateOfBirth}
              onChange={(e) => setDateOfBirth(e.target.value)}
              max={new Date().toISOString().slice(0, 10)}
              required
            />
            <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginTop: 4 }}>
              An account holder must be an adult. A child is tracked as a
              dependent profile under a parent or guardian's account.
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Phone Number <span style={{ color: 'var(--color-text-secondary)', fontWeight: 400 }}>(optional — enables phone login)</span></label>
            <input
              className="form-input"
              type="tel"
              placeholder="+1 555 123 4567"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="register-password">Password</label>
            <PasswordInput
              id="register-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              autoComplete="new-password"
            />
          </div>
          <button className="btn btn-primary" style={{ width: '100%' }} type="submit"
                  disabled={submitting}>
            {submitting ? 'Creating your account…' : 'Create Account'}
          </button>
        </form>
        <div className="auth-footer">
          Already have an account? <Link to="/login">Sign In</Link>
        </div>
      </div>
    </div>
  );
}
