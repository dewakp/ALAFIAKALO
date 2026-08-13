import { Link } from 'react-router-dom';
import MarketingPage from '../components/MarketingChrome';

const THESIS = [
  {
    icon: '📐',
    title: 'A modelled wellness score',
    desc: 'Most platforms aggregate metrics. ALAFIA models wellness as a mathematical system with a stable manifold and a distance function.',
  },
  {
    icon: '🩺',
    title: 'Physician sharing is the wedge',
    desc: 'Data sharing plugs into clinical workflows instead of living beside them. That is what turns a consumer app into something a health system or an insurer buys.',
  },
  {
    icon: '🧭',
    title: 'A companion, not a tracker',
    desc: 'AI medical personas and the unified score act on the data in real time, and sharing closes the loop back to actual care.',
  },
  {
    icon: '🌍',
    title: 'Holistic by construction',
    desc: 'Nutrients, medications, labs, fitness, environment and mental health feed one view of a person — a 360° picture with no gap.',
  },
];

const SEGMENTS = [
  { n: '01', who: 'People managing their health', why: 'Led by chronic-disease management.' },
  { n: '02', who: 'Providers', why: 'Clinicians receiving shared records inside their existing workflow.' },
  { n: '03', who: 'Payers & employers', why: 'Insurers and administrators who carry the cost of chronic care.' },
];

export default function Investors() {
  return (
    <MarketingPage>
      <section className="section-wrap section-wrap--top section-wrap--narrow">
        <div className="section-head">
          <span className="eyebrow">INVESTORS</span>
          <h2>Why ALAFIA</h2>
          <p>An intelligent health platform built for the patients who cost the system the most.</p>
        </div>

        <div className="prose">
          <p>
            ALAFIA is a 6igma health platform. It unifies labs, medications, nutrition, fitness,
            mental health and clinical care into a single model of a person, and puts an intelligent
            agent on top of that model rather than beside it.
          </p>
          <p>
            The entry point is chronic disease — ESRD and dialysis, diabetes, and anyone whose
            condition has to be managed daily rather than occasionally. That cohort needs the
            “distance from a stable operating manifold” framing every day, is the most expensive
            population in the system, and is where the return is clearest to patients, clinicians,
            administrators and insurers alike.
          </p>
        </div>

        <div className="features-grid" style={{ marginTop: '3rem' }}>
          {THESIS.map(t => (
            <div className="feat-card" key={t.title}>
              <span className="feat-icon">{t.icon}</span>
              <h3>{t.title}</h3>
              <p>{t.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section-wrap section-wrap--narrow" style={{ paddingTop: 0 }}>
        <div className="section-head">
          <span className="eyebrow">GO TO MARKET</span>
          <h2>Who ALAFIA serves</h2>
        </div>

        <ol className="segment-list">
          {SEGMENTS.map(s => (
            <li className="segment-row" key={s.n}>
              <span className="segment-num">{s.n}</span>
              <div>
                <h3>{s.who}</h3>
                <p>{s.why}</p>
              </div>
            </li>
          ))}
        </ol>

        <div className="prose" style={{ marginTop: '3rem' }}>
          <h3>Market</h3>
          <p>
            Global, spanning wellness, health, fitness, nutrition and public health.
          </p>
          <h3>Talking to us</h3>
          <p>
            We share the deck, the technical detail behind the wellness model, and current status
            on request. There is no public offering here — this page is an overview, not a
            solicitation, and nothing on it is a projection or a promise of returns.
          </p>
        </div>

        <div className="mk-cta">
          <p className="mk-cta-note">
            Investment, partnership and enterprise pilots:{' '}
            <a href="mailto:contact@alafia.app">contact@alafia.app</a>
          </p>
          <Link to="/contact" className="btn-primary-lg">Request the Deck ✦</Link>
        </div>
      </section>
    </MarketingPage>
  );
}
