import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import PasswordInput from '../components/PasswordInput';
import { apiErrorMessage } from '../utils/apiError';

/**
 * Two-step signup: account details → payment → verified account.
 *
 * The backend has had these four endpoints all along and NOTHING called them.
 * `TWO_STEP_SIGNUP_REQUIRED` could not be turned on because turning it on would
 * have closed registration entirely — there was no client for the flow it
 * requires. Meanwhile the old one-step form created unpaid, loginable accounts
 * and told the user nothing, which is how an account reached production having
 * "gone through" with neither an email nor a payment.
 *
 * The order is deliberate and matches what was asked for: details are taken,
 * the verification email goes out, and the app moves STRAIGHT to payment
 * without waiting for the click. Payment and verification are independent —
 * whichever finishes second creates the account. So a card that clears while
 * the email sits unread is money we hold and an account the person can finish
 * from their inbox, not a dead end.
 */

const STEPS = ['details', 'payment', 'done'];

export default function SignupFlow() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();

  // Stripe's success URL carries `session_id` and NOT the email — it is built
  // server-side before a customer exists. So the address is parked here before
  // leaving and read back on return. sessionStorage, not localStorage: it is
  // one signup in one tab, and it should not outlive the tab.
  const PARKED = 'alafia.signup.email';

  const [step, setStep] = useState('details');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [dateOfBirth, setDateOfBirth] = useState('');
  const [interval, setInterval] = useState('month');
  const [status, setStatus] = useState(null);

  // Stripe returns to /signup/complete?provider=stripe&session_id=…
  const sessionId = params.get('session_id');
  const returning = location.pathname.endsWith('/complete') && !!sessionId;
  const cancelled = params.get('status') === 'cancel';

  useEffect(() => {
    if (cancelled) {
      // Backing out of Stripe is not a failure. The signup is still pending
      // and the card page is one tap away — saying "payment failed" here would
      // be false and would read as money lost.
      setStep('payment');
      setEmail(sessionStorage.getItem(PARKED) || '');
      setNotice('No payment was taken. You can pick a plan whenever you are ready.');
    }
  }, [cancelled]);

  useEffect(() => {
    if (!returning) return;
    const parked = sessionStorage.getItem(PARKED);
    if (!parked) {
      // The tab was closed, or payment finished somewhere else. The money is
      // taken either way, so this must not dead-end: ask for the address and
      // finish, rather than showing a blank success page.
      setStep('recover');
      return;
    }
    (async () => {
      setBusy(true);
      try {
        const { data } = await api.post('/auth/signup/complete', {
          email: parked, provider: 'stripe', reference_id: sessionId,
        });
        setEmail(parked);
        setStatus(data);
        sessionStorage.removeItem(PARKED);
        setStep('done');
      } catch (err) {
        setError(apiErrorMessage(err, 'We could not confirm that payment.'));
        setEmail(parked);
        setStep('payment');
      } finally {
        setBusy(false);
      }
    })();
  }, [returning, sessionId]);

  async function completeWith(address) {
    setError('');
    setBusy(true);
    try {
      const { data } = await api.post('/auth/signup/complete', {
        email: address.trim(), provider: 'stripe', reference_id: sessionId,
      });
      setEmail(address.trim());
      setStatus(data);
      setStep('done');
    } catch (err) {
      setError(apiErrorMessage(err, 'We could not confirm that payment.'));
    } finally {
      setBusy(false);
    }
  }

  async function submitDetails(e) {
    e.preventDefault();
    setError('');
    if (firstName.trim().length < 3) { setError('First name must be at least 3 characters'); return; }
    if (lastName.trim().length < 3) { setError('Last name must be at least 3 characters'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('Please enter a valid email address'); return; }
    if (password.length < 8) { setError('Password must be at least 8 characters'); return; }
    if (!dateOfBirth) { setError('Date of birth is required'); return; }
    if (busy) return;

    setBusy(true);
    try {
      await api.post('/auth/signup/start', {
        email: email.trim(),
        password,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        date_of_birth: dateOfBirth,
        country: Intl.DateTimeFormat().resolvedOptions().locale?.split('-')[1] || null,
      });
      setNotice(`We've emailed a verification link to ${email.trim()}. `
                + 'You can set up payment now — the link will still be waiting.');
      setStep('payment');
    } catch (err) {
      setError(apiErrorMessage(err, 'We could not start your signup.'));
    } finally {
      setBusy(false);
    }
  }

  async function goToPayment() {
    setError('');
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post('/auth/signup/checkout', {
        email: email.trim(), provider: 'stripe', interval,
      });
      // Park the address BEFORE leaving: Stripe's return carries only a
      // session id, and without this the completion has no account to attach
      // the payment to.
      sessionStorage.setItem(PARKED, email.trim());
      // Leaving the app entirely — Stripe hosts the card form so no card
      // number ever touches this origin.
      window.location.href = data.checkout_url;
    } catch (err) {
      setError(apiErrorMessage(err, 'We could not open the payment page.'));
      setBusy(false);
    }
  }

  async function resend() {
    setError(''); setNotice('');
    try {
      await api.post('/auth/signup/resend', { email: email.trim() });
      setNotice('Sent. Check your inbox, and your spam folder.');
    } catch (err) {
      setError(apiErrorMessage(err, 'We could not resend that email.'));
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <h1 className="auth-title">ALAFIA</h1>
        <p className="auth-subtitle">
          {step === 'details' && 'Create your account'}
          {step === 'payment' && 'Choose your membership'}
          {step === 'recover' && 'Finish your signup'}
          {step === 'done' && 'Almost there'}
        </p>

        <ol className="signup-steps" aria-label="Signup progress">
          {STEPS.map((s, i) => (
            <li key={s}
                className={STEPS.indexOf(step) >= i ? 'is-done' : ''}
                aria-current={step === s ? 'step' : undefined}>
              {['Your details', 'Payment', 'Finish'][i]}
            </li>
          ))}
        </ol>

        {error && <div className="auth-error" role="alert">{error}</div>}
        {notice && <div className="auth-notice">{notice}</div>}

        {step === 'details' && (
          <form onSubmit={submitDetails}>
            <div className="name-row">
              <div className="form-group">
                <label className="form-label" htmlFor="su-first">First Name</label>
                <input id="su-first" className="form-input" autoComplete="given-name"
                       minLength={3} value={firstName}
                       onChange={(e) => setFirstName(e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="su-last">Last Name</label>
                <input id="su-last" className="form-input" autoComplete="family-name"
                       minLength={3} value={lastName}
                       onChange={(e) => setLastName(e.target.value)} required />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="su-email">Email</label>
              <input id="su-email" className="form-input" type="email" autoComplete="email"
                     value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="su-dob">Date of Birth</label>
              <input id="su-dob" className="form-input" type="date" value={dateOfBirth}
                     onChange={(e) => setDateOfBirth(e.target.value)} required />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="su-password">Password</label>
              <PasswordInput id="su-password" value={password}
                             onChange={(e) => setPassword(e.target.value)} required />
            </div>
            <button className="btn btn-primary btn-block" disabled={busy}>
              {busy ? 'Creating…' : 'Continue'}
            </button>
          </form>
        )}

        {step === 'payment' && (
          <div>
            <fieldset className="plan-choice">
              <legend className="form-label">Billing</legend>
              {[['month', 'Monthly'], ['year', 'Yearly']].map(([value, label]) => (
                <label key={value} className={interval === value ? 'is-selected' : ''}>
                  <input type="radio" name="interval" value={value}
                         checked={interval === value}
                         onChange={() => setInterval(value)} />
                  {label}
                </label>
              ))}
            </fieldset>
            <button className="btn btn-primary btn-block" onClick={goToPayment} disabled={busy}>
              {busy ? 'Opening payment…' : 'Continue to payment'}
            </button>
            <button type="button" className="btn-link" onClick={resend}>
              Resend the verification email
            </button>
          </div>
        )}

        {step === 'recover' && (
          <form onSubmit={(e) => { e.preventDefault(); completeWith(email); }}>
            <p className="auth-notice">
              Your payment went through. Confirm the email address you signed up
              with and we will finish setting up your account.
            </p>
            <div className="form-group">
              <label className="form-label" htmlFor="su-recover">Email</label>
              <input id="su-recover" className="form-input" type="email" required
                     value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <button className="btn btn-primary btn-block" disabled={busy}>
              {busy ? 'Finishing…' : 'Finish setting up'}
            </button>
          </form>
        )}

        {step === 'done' && (
          <div>
            {status?.email_verified ? (
              <>
                <p>Your membership is active and your account is ready.</p>
                <button className="btn btn-primary btn-block" onClick={() => navigate('/login')}>
                  Sign in
                </button>
              </>
            ) : (
              <>
                {/* Paid but unverified is a REAL state, not an error: the card
                    cleared and the email is still unread. Saying "payment
                    failed" here would be false, and saying nothing is how
                    someone concludes their money vanished. */}
                <p>
                  <strong>Payment received.</strong> One step left — open the
                  verification link we emailed to {status?.email || email} and
                  your account will be created.
                </p>
                <button type="button" className="btn-link" onClick={resend}>
                  Resend the verification email
                </button>
              </>
            )}
          </div>
        )}

        <p className="auth-alt">
          Already have an account? <Link to="/login">Sign In</Link>
        </p>
      </div>
    </div>
  );
}
