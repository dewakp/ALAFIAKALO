import { Link } from 'react-router-dom';
import MarketingPage from '../components/MarketingChrome';
import { t as translate } from '../i18n';

const THESIS = [
  {
    icon: '📐',
    get title() { return translate('Investors.a_modelled_wellness_score'); },
    get desc() { return translate('Investors.most_platforms_aggregate_metrics_alafia'); },
  },
  {
    icon: '🩺',
    get title() { return translate('Investors.physician_sharing_is_the_wedge'); },
    get desc() { return translate('Investors.data_sharing_plugs_into_clinical'); },
  },
  {
    icon: '🧭',
    get title() { return translate('Investors.a_companion_not_a_tracker'); },
    get desc() { return translate('Investors.ai_medical_personas_and_the_unified'); },
  },
  {
    icon: '🌍',
    get title() { return translate('Investors.holistic_by_construction'); },
    get desc() { return translate('Investors.nutrients_medications_labs_fitness'); },
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
          <h2>{translate('Investors.why_alafia')}</h2>
          <p>{translate('Investors.an_intelligent_health_platform_built_for')}</p>
        </div>

        <div className="prose">
          <p>
            {translate('Investors.alafia_is_a_6igma_health_platform_it')}
          </p>
          <p>
            {translate('Investors.the_entry_point_is_chronic_disease_esrd')}
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
          <h2>{translate('Investors.who_alafia_serves')}</h2>
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
          <h3>{translate('Investors.market')}</h3>
          <p>
            {translate('Investors.global_spanning_wellness_health_fitness')}
          </p>
          <h3>{translate('Investors.talking_to_us')}</h3>
          <p>
            {translate('Investors.we_share_the_deck_the_technical_detail')}
          </p>
        </div>

        <div className="mk-cta">
          <p className="mk-cta-note">
            {translate('Investors.investment_partnership_and_enterprise')}{' '}
            <a href="mailto:contact@alafia.app">contact@alafia.app</a>
          </p>
          <Link to="/contact" className="btn-primary-lg">{translate('Investors.request_the_deck')}</Link>
        </div>
      </section>
    </MarketingPage>
  );
}
