import { Link } from 'react-router-dom';
import MarketingPage from '../components/MarketingChrome';

const CHANNELS = [
  {
    icon: '✉️',
    title: 'General & Support',
    desc: 'Questions about your account, a feature that is not behaving, or anything else about using ALAFIA.',
    email: 'contact@alafia.app',
  },
  {
    icon: '🔒',
    title: 'Privacy',
    desc: 'Requests about the data we hold on you — access, correction, export or deletion.',
    email: 'privacy@alafia.app',
  },
  {
    icon: '🛡️',
    title: 'Data Protection Officer',
    desc: 'GDPR and other data-protection matters that need the DPO directly.',
    email: 'dpo@alafia.app',
  },
  {
    icon: '🐛',
    title: 'Security Disclosure',
    desc: 'Found a vulnerability? Report it here first — please do not open a public issue.',
    email: 'security@alafia.app',
  },
];

export default function Contact() {
  return (
    <MarketingPage>
      <section className="section-wrap section-wrap--top section-wrap--narrow">
        <div className="section-head">
          <span className="eyebrow">GET IN TOUCH</span>
          <h2>Contact Us</h2>
          <p>Reach the right desk directly. We read everything that comes in.</p>
        </div>

        <div className="features-grid">
          {CHANNELS.map(c => (
            <div className="feat-card" key={c.email}>
              <span className="feat-icon">{c.icon}</span>
              <h3>{c.title}</h3>
              <p>{c.desc}</p>
              <a className="card-link" href={`mailto:${c.email}`}>{c.email}</a>
            </div>
          ))}
        </div>

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
          <Link to="/help" className="btn-primary-lg">Browse Help ✦</Link>
        </div>
      </section>
    </MarketingPage>
  );
}
