import PasswordInput from '../components/PasswordInput';
import { useState } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { t } from '../i18n';

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
    if (!email.trim()) { setError(t('ForgotPassword.email_is_required')); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError(t('ForgotPassword.please_enter_a_valid_email_address')); return; }
    setBusy(true);
    try {
      const data = await requestPasswordReset(email);
      setMessage(data.message);
      setStep('sent');
    } catch (err) {
      setError(apiErrorMessage(err, t('ForgotPassword.failed_to_request_reset')));
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm(e) {
    e.preventDefault();
    setError('');
    if (!token) { setError(t('ForgotPassword.this_reset_link_is_missing_its_token')); return; }
    if (newPassword.length < 6) { setError(t('ForgotPassword.password_must_be_at_least_6_characters')); return; }
    if (newPassword !== confirmPw) { setError(t('ForgotPassword.passwords_do_not_match')); return; }
    setBusy(true);
    try {
      await confirmPasswordReset(token, newPassword);
      setStep('done');
    } catch (err) {
      setError(apiErrorMessage(err, t('ForgotPassword.this_reset_link_is_invalid_or_has')));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <h1 className="auth-title">{t('ForgotPassword.reset_password')}</h1>

        {error && (
          <div style={{ color: 'var(--color-danger)', textAlign: 'center', marginBottom: '1rem' }}>
            {error}
          </div>
        )}

        {step === 'request' && (
          <>
            <p className="auth-subtitle">{t('ForgotPassword.enter_your_email_and_we_ll_send_you_a')}</p>
            <form onSubmit={handleRequest}>
              <div className="form-group">
                <label className="form-label">{t('ForgotPassword.email')}</label>
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
              {t('ForgotPassword.open_the_link_in_that_email_to_choose_a')}
            </p>
          </>
        )}

        {step === 'confirm' && (
          <>
            <p className="auth-subtitle">{t('ForgotPassword.choose_a_new_password_for_your_account')}</p>
            <form onSubmit={handleConfirm}>
              <div className="form-group">
                <label className="form-label">{t('ForgotPassword.new_password')}</label>
                <PasswordInput
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  minLength={6}
                  autoComplete="new-password"
                />
              </div>
              <div className="form-group">
                <label className="form-label">{t('ForgotPassword.confirm_password')}</label>
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
              {t('ForgotPassword.password_reset_successfully')}
            </p>
            <Link to="/login">
              <button className="btn btn-primary" style={{ width: '100%' }}>
                {t('ForgotPassword.back_to_login')}
              </button>
            </Link>
          </>
        )}

        <div className="auth-footer">
          {step === 'confirm' || step === 'sent' ? (
            <Link to="/forgot-password">{t('ForgotPassword.request_a_new_link')}</Link>
          ) : (
            <Link to="/login">{t('ForgotPassword.back_to_sign_in')}</Link>
          )}
        </div>
      </div>
    </div>
  );
}
