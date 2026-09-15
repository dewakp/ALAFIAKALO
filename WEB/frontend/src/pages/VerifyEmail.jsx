import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { t } from '../i18n';

/**
 * The landing page for the link in the verification email.
 *
 * The email has always pointed at `/verify-email?token=…` and no such route
 * existed, so every verification link in production landed on the app's
 * catch-all. The token was valid; there was simply nothing to spend it on.
 *
 * What happens next depends on what the signup has already done, which is why
 * this asks `/signup/status` rather than assuming: someone who paid first is
 * finished the moment they click, and someone who has not paid still needs to.
 */
export default function VerifyEmail() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get('token');

  const [state, setState] = useState('checking');   // checking | done | needs-payment | error
  const [message, setMessage] = useState('');
  // React 18 mounts twice in StrictMode. A verification token is single-use, so
  // the second call would consume nothing and report failure on a link that
  // had just worked.
  const spent = useRef(false);

  useEffect(() => {
    if (!token) { setState('error'); setMessage(t('VerifyEmail.that_link_is_missing_its_token')); return; }
    if (spent.current) return;
    spent.current = true;

    (async () => {
      try {
        const { data } = await api.post('/auth/signup/verify-email', { token });
        const email = data?.email;
        if (!email) { setState('done'); return; }

        // Verified is only half the gate. Ask what is left rather than guessing.
        try {
          const { data: status } = await api.get('/auth/signup/status', { params: { email } });
          if (status.next === 'complete' || status.paid) setState('done');
          else { setState('needs-payment'); setMessage(email); }
        } catch {
          // No pending row left means the account was created — the happy end.
          setState('done');
        }
      } catch (err) {
        setState('error');
        setMessage(apiErrorMessage(err, t('VerifyEmail.that_link_could_not_be_used')));
      }
    })();
  }, [token]);

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <h1 className="auth-title">ALAFIA</h1>

        {state === 'checking' && <p className="auth-subtitle">{t('VerifyEmail.confirming_your_email')}</p>}

        {state === 'done' && (
          <>
            <p className="auth-subtitle">{t('VerifyEmail.your_email_is_confirmed_and_your_account')}</p>
            <button className="btn btn-primary btn-block" onClick={() => navigate('/login')}>
              {t('VerifyEmail.sign_in')}
            </button>
          </>
        )}

        {state === 'needs-payment' && (
          <>
            <p className="auth-subtitle">
              {t('VerifyEmail.email_confirmed_one_step_left_choose')}
            </p>
            <button className="btn btn-primary btn-block"
                    onClick={() => navigate(`/signup?email=${encodeURIComponent(message)}`)}>
              {t('VerifyEmail.continue_to_payment')}
            </button>
          </>
        )}

        {state === 'error' && (
          <>
            {/* Never "verified!" on a failure, and never a blank page: a link
                that has expired, been used, or been truncated by a mail client
                all land here and each needs a route forward. */}
            <div className="auth-error" role="alert">{message}</div>
            <p className="auth-alt">
              {t('VerifyEmail.links_expire')} <Link to="/signup">{t('VerifyEmail.start_again')}</Link> {t('VerifyEmail.and_we_will_send_a_new_one')}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
