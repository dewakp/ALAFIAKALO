import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';

/* OAuth redirect target for MyChart (SMART on FHIR) sign-ins.
   The portal sends ?code&state here; we finish the exchange server-side. */
export default function EHRCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const ran = useRef(false);
  const [status, setStatus] = useState({ phase: 'working', text: 'Completing the connection to your portal…' });

  useEffect(() => {
    if (ran.current) return;   // StrictMode double-mount guard — codes are single-use
    ran.current = true;

    const code = params.get('code');
    const state = params.get('state');
    const error = params.get('error');

    if (error || !code || !state) {
      setStatus({
        phase: 'error',
        text: error === 'access_denied'
          ? 'You declined the connection on the portal. No records were shared.'
          : 'The portal did not return a valid sign-in — please try connecting again.',
      });
      return;
    }

    api.post('/ehr/exchange', { code, state })
      .then(({ data }) => {
        setStatus({ phase: 'done', text: `Connected to ${data.org_name || 'your portal'}. Redirecting…` });
        setTimeout(() => navigate('/data-sharing', { replace: true }), 1500);
      })
      .catch(err => setStatus({ phase: 'error', text: apiErrorMessage(err, 'Could not complete the connection.') }));
  }, [params, navigate]);

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
      <div className="card" style={{ maxWidth: 440, textAlign: 'center', padding: '2rem' }}>
        {status.phase === 'working' && <Loader2 size={36} style={{ animation: 'spin-anim 1s linear infinite', color: 'var(--color-primary)' }} />}
        {status.phase === 'done' && <CheckCircle2 size={36} style={{ color: '#10b981' }} />}
        {status.phase === 'error' && <AlertCircle size={36} style={{ color: 'var(--color-danger)' }} />}
        <p style={{ marginTop: '1rem', fontSize: '.95rem' }}>{status.text}</p>
        {status.phase === 'error' && (
          <button className="btn btn-primary" style={{ marginTop: '.5rem' }}
            onClick={() => navigate('/data-sharing')}>
            Back to Connect Records
          </button>
        )}
      </div>
    </div>
  );
}
