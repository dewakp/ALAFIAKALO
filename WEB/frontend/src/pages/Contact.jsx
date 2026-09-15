import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import MarketingPage from '../components/MarketingChrome';
import { t as translate } from '../i18n';

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
  { key: 'support', get label() { return translate('Contact.general_support'); } },
  { key: 'privacy', get label() { return translate('Contact.privacy'); } },
  { key: 'dpo', get label() { return translate('Contact.data_protection_officer'); } },
  { key: 'security', get label() { return translate('Contact.security_disclosure'); } },
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
      setError(translate('Contact.that_sum_is_not_right_please_try_again'));
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
            <h2>{translate('Contact.thank_you_we_have_it')}</h2>
            <p>
              {translate('Contact.your_message_reached_our')}{' '}
              <strong>{sentDesk || 'support'}</strong> {translate('Contact.desk_we_reply_to_the_address_you_gave_us')}
            </p>
            {reference && (
              <p>
                {translate('Contact.your_reference_is')} <strong>{reference}</strong> {translate('Contact.quote_it_if_you_follow_up')}
              </p>
            )}
          </div>
          <div className="mk-cta">
            <Link to="/help" className="btn-primary-lg">{translate('Contact.browse_help')}</Link>
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
          <h2>{translate('Contact.contact_us')}</h2>
          <p>
            {translate('Contact.tell_us_what_it_is_about_and_we_will')}
          </p>
        </div>

        <form className="contact-form" onSubmit={handleSubmit} noValidate>
          <div className="form-group">
            <label htmlFor="contact-topic">{translate('Contact.what_is_this_about')}</label>
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
              <label htmlFor="contact-name">{translate('Contact.your_name')}</label>
              <input
                id="contact-name" className="form-input" type="text"
                autoComplete="name" value={form.name} onChange={set('name')} required
              />
            </div>
            <div className="form-group">
              <label htmlFor="contact-email">{translate('Contact.email')}</label>
              <input
                id="contact-email" className="form-input" type="email"
                autoComplete="email" value={form.email} onChange={set('email')} required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="contact-org">{translate('Contact.organisation')} <span className="opt">{translate('Contact.optional')}</span></label>
              <input
                id="contact-org" className="form-input" type="text"
                autoComplete="organization" value={form.organization} onChange={set('organization')}
              />
            </div>
            <div className="form-group">
              <label htmlFor="contact-phone">{translate('Contact.phone')} <span className="opt">{translate('Contact.optional')}</span></label>
              <input
                id="contact-phone" className="form-input" type="tel"
                autoComplete="tel" value={form.phone} onChange={set('phone')}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="contact-message">{translate('Contact.how_can_we_help')}</label>
            <textarea
              id="contact-message" className="form-input" rows="6"
              value={form.message} onChange={set('message')} required minLength={10}
            />
            <p className="form-hint">
              {translate('Contact.please_do_not_include_passwords_for_your')}
            </p>
          </div>

          {/* Honeypot — off-screen rather than display:none so it is not an
              obvious tell, and hidden from assistive tech and the tab order. */}
          <div aria-hidden="true" className="hp-field">
            <label htmlFor="contact-website">{translate('Contact.leave_this_field_empty')}</label>
            <input
              id="contact-website" type="text" tabIndex={-1} autoComplete="off"
              value={form.website} onChange={set('website')}
            />
          </div>

          <div className="form-group">
            <label htmlFor="contact-captcha">
              {translate('Contact.quick_check_what_is', { a: sum.a, b: sum.b })}
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
          <strong>{translate('Contact.not_for_emergencies')}</strong> {translate('Contact.alafia_is_not_an_emergency_service_and')}
        </div>

        <div className="mk-cta">
          <p className="mk-cta-note">
            {translate('Contact.looking_for_answers_rather_than_a_person')}{' '}
            <Link to="/help">{translate('Contact.help_centre')}</Link>{translate('Contact.investment_and_partnership_enquiries')}{' '}
            <Link to="/investors">{translate('Contact.investors')}</Link> {translate('Contact.page')}
          </p>
        </div>
      </section>
    </MarketingPage>
  );
}
