import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import MarketingPage from '../components/MarketingChrome';

/**
 * Contact — a form that routes, not a wall of mailto: links.
 *
 * The previous page listed four addresses and asked the visitor to work out
 * which desk they needed. That puts the routing decision on the person least
 * able to make it, and a mailto: link is a dead end for anyone on a device with
 * no mail client configured — which on mobile is common.
 *
 * Modelled on the CRAM marketing contact page: one form, a honeypot, a math
 * check, and a thank-you state. It does NOT use FormSubmit the way that page
 * does — the Privacy and DPO desks can receive a patient's health details, and
 * relaying those through a third-party form service would disclose them to a
 * processor we have no agreement with. It posts to our own backend, which
 * sends through the Resend sender already used for account mail.
 *
 * The desk list comes from the API rather than being duplicated here, so the
 * routing table cannot drift between the site and the server.
 */

const FALLBACK_TOPICS = [
  { key: 'support', label: 'General & Support' },
  { key: 'privacy', label: 'Privacy' },
  { key: 'dpo', label: 'Data Protection Officer' },
  { key: 'security', label: 'Security Disclosure' },
];

// What each desk is for. Copy lives here because it is presentation; the
// routing itself is the server's.
const TOPIC_HELP = {
  support: 'Your account, something not behaving as it should, or anything else about using ALAFIA.',
  privacy: 'The data we hold on you — access, correction, export or deletion.',
  dpo: 'GDPR and other data-protection matters that need the DPO directly.',
  security: 'Found a vulnerability? Report it here first — please do not open a public issue.',
  billing: 'Payments, invoices, and anything about your membership.',
  clinical: 'Clinicians and care teams working with patients on ALAFIA.',
};

export default function Contact() {
  const [topics, setTopics] = useState(FALLBACK_TOPICS);
  const [form, setForm] = useState({
    topic: 'support', name: '', email: '', organization: '', phone: '',
    message: '', website: '',   // `website` is the honeypot
  });
  const [captcha, setCaptcha] = useState('');
  const [status, setStatus] = useState('idle');   // idle | sending | sent | error
  const [error, setError] = useState('');
  const [sentDesk, setSentDesk] = useState('');
  const [reference, setReference] = useState('');

  // Fresh numbers per mount, like the CRAM page.
  const sum = useMemo(() => {
    const a = Math.floor(Math.random() * 9) + 1;
    const b = Math.floor(Math.random() * 9) + 1;
    return { a, b, answer: a + b };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/v1/contact/topics')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!cancelled && d?.topics?.length) setTopics(d.topics); })
      .catch(() => { /* the fallback list is already correct */ });
    return () => { cancelled = true; };
  }, []);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  // Double-submit CSRF, the same scheme services/api.js uses. Done inline
  // rather than via the shared axios client on purpose: that client's response
  // interceptor treats a 401 as a dead session and redirects to /login, which
  // would be wrong on a public marketing page.
  function readCookie(name) {
    return document.cookie
      .split('; ')
      .find((c) => c.startsWith(`${name}=`))
      ?.split('=')[1] || '';
  }

  async function csrfToken() {
    let token = readCookie('csrf_token');
    if (token) return token;
    await fetch('/api/v1/auth/csrf-cookie', { credentials: 'same-origin' });
    return readCookie('csrf_token');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (parseInt(captcha, 10) !== sum.answer) {
      setError('That sum is not right — please try again.');
      return;
    }

    setStatus('sending');
    try {
      const res = await fetch('/api/v1/contact', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': await csrfToken(),
        },
        body: JSON.stringify(form),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        // Show the server's own sentence. A generic "something went wrong"
        // hides the one useful thing here — which address to write to instead.
        throw new Error(
          typeof data?.detail === 'string'
            ? data.detail
            : 'We could not send your message. Please try again shortly.',
        );
      }
      setSentDesk(data.desk || '');
      setReference(data.reference || '');
      setStatus('sent');
    } catch (err) {
      setStatus('error');
      setError(err.message);
    }
  }

  if (status === 'sent') {
    return (
      <MarketingPage>
        <section className="section-wrap section-wrap--top section-wrap--narrow">
          <div className="section-head">
            <span className="eyebrow">MESSAGE SENT</span>
            <h2>Thank you — we have it</h2>
            <p>
              Your message reached our{' '}
              <strong>{sentDesk || 'support'}</strong> desk. We reply to the
              address you gave us, usually within two working days.
            </p>
            {reference && (
              <p>
                Your reference is <strong>{reference}</strong> — quote it if you
                follow up.
              </p>
            )}
          </div>
          <div className="mk-cta">
            <Link to="/help" className="btn-primary-lg">Browse Help ✦</Link>
          </div>
        </section>
      </MarketingPage>
    );
  }

  return (
    <MarketingPage>
      <section className="section-wrap section-wrap--top section-wrap--narrow">
        <div className="section-head">
          <span className="eyebrow">GET IN TOUCH</span>
          <h2>Contact Us</h2>
          <p>
            Tell us what it is about and we will route it to the right desk.
            We read everything that comes in.
          </p>
        </div>

        <form className="contact-form" onSubmit={handleSubmit} noValidate>
          <div className="form-group">
            <label htmlFor="contact-topic">What is this about?</label>
            <select
              id="contact-topic" className="form-input"
              value={form.topic} onChange={set('topic')} required
            >
              {topics.map((t) => (
                <option key={t.key} value={t.key}>{t.label}</option>
              ))}
            </select>
            {TOPIC_HELP[form.topic] && (
              <p className="form-hint">{TOPIC_HELP[form.topic]}</p>
            )}
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="contact-name">Your name</label>
              <input
                id="contact-name" className="form-input" type="text"
                autoComplete="name" value={form.name} onChange={set('name')} required
              />
            </div>
            <div className="form-group">
              <label htmlFor="contact-email">Email</label>
              <input
                id="contact-email" className="form-input" type="email"
                autoComplete="email" value={form.email} onChange={set('email')} required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="contact-org">Organisation <span className="opt">(optional)</span></label>
              <input
                id="contact-org" className="form-input" type="text"
                autoComplete="organization" value={form.organization} onChange={set('organization')}
              />
            </div>
            <div className="form-group">
              <label htmlFor="contact-phone">Phone <span className="opt">(optional)</span></label>
              <input
                id="contact-phone" className="form-input" type="tel"
                autoComplete="tel" value={form.phone} onChange={set('phone')}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="contact-message">How can we help?</label>
            <textarea
              id="contact-message" className="form-input" rows="6"
              value={form.message} onChange={set('message')} required minLength={10}
            />
            <p className="form-hint">
              Please do not include passwords. For your own safety, share only
              what we need to help.
            </p>
          </div>

          {/* Honeypot — off-screen rather than display:none so it is not an
              obvious tell, and hidden from assistive tech and the tab order. */}
          <div aria-hidden="true" className="hp-field">
            <label htmlFor="contact-website">Leave this field empty</label>
            <input
              id="contact-website" type="text" tabIndex={-1} autoComplete="off"
              value={form.website} onChange={set('website')}
            />
          </div>

          <div className="form-group">
            <label htmlFor="contact-captcha">
              Quick check: what is {sum.a} + {sum.b}?
            </label>
            <input
              id="contact-captcha" className="form-input" type="text"
              inputMode="numeric" autoComplete="off"
              value={captcha} onChange={(e) => setCaptcha(e.target.value)} required
            />
          </div>

          {error && <div className="callout callout--danger">{error}</div>}

          <button type="submit" className="btn-primary-lg" disabled={status === 'sending'}>
            {status === 'sending' ? 'Sending…' : 'Send message ✦'}
          </button>
        </form>

        <div className="callout callout--danger">
          <strong>Not for emergencies.</strong> ALAFIA is not an emergency service and nobody
          monitors these inboxes around the clock. If you are having a medical emergency, call
          your local emergency number or go to the nearest emergency department.
        </div>

        <div className="mk-cta">
          <p className="mk-cta-note">
            Looking for answers rather than a person? Most questions are already covered in the{' '}
            <Link to="/help">Help centre</Link>. Investment and partnership enquiries belong on the{' '}
            <Link to="/investors">Investors</Link> page.
          </p>
        </div>
      </section>
    </MarketingPage>
  );
}
