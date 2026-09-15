import { Link } from 'react-router-dom';
import MarketingPage from '../components/MarketingChrome';
import { t } from '../i18n';

const START_HERE = [
  {
    icon: '✨',
    get title() { return t('Help.ask_alafia'); },
    get desc() { return t('Help.the_fastest_way_in_describe_what_you'); },
    to: '/',
  },
  {
    icon: '🥗',
    get title() { return t('Help.log_a_meal'); },
    get desc() { return t('Help.type_or_photograph_what_you_ate_calories'); },
    to: '/nutrition',
  },
  {
    icon: '🧬',
    get title() { return t('Help.add_lab_results'); },
    get desc() { return t('Help.upload_a_pdf_or_enter_values_by_hand'); },
    to: '/labs',
  },
  {
    icon: '🔗',
    get title() { return t('Help.connect_your_records'); },
    get desc() { return t('Help.link_an_existing_patient_portal_so_your'); },
    to: '/data-sharing',
  },
];

const FAQ = [
  {
    q: 'Why does my meal say “estimating…” instead of showing calories?',
    a: (
      <>
        {t('Help.because_it_is_still_being_worked_out')}
      </>
    ),
  },
  {
    q: 'I forgot my password.',
    a: (
      <>
        {t('Help.use')} <Link to="/forgot-password">{t('Help.forgot_password')}</Link>{t('Help.we_email_you_a_link_that_opens_the_reset')}
      </>
    ),
  },
  {
    q: 'The verification or reset email never arrived.',
    a: (
      <>
        {t('Help.check_your_spam_and_promotions_folders')}{' '}
        <a href="mailto:contact@alafia.app">contact@alafia.app</a> {t('Help.from_the_address_you_signed_up_with_and')}
      </>
    ),
  },
  {
    q: 'Who can see my health data?',
    a: (
      <>
        {t('Help.you_and_whoever_you_deliberately_share')}
      </>
    ),
  },
  {
    q: 'Can I use ALAFIA on my phone?',
    a: (
      <>
        {t('Help.the_web_app_works_in_any_modern_mobile')}{' '}
        <a href="/landing#platforms">{t('Help.platforms')}</a> {t('Help.for_where_each_one_stands')}
      </>
    ),
  },
  {
    q: 'What does a membership change?',
    a: (
      <>
        {t('Help.tiers_and_what_each_one_unlocks_are')}{' '}
        <Link to="/subscription">{t('Help.membership')}</Link> {t('Help.page_inside_the_app_where_you_can_also')}
      </>
    ),
  },
  {
    q: 'How do I delete my account and my data?',
    a: (
      <>
        {t('Help.ask_us_and_we_will_do_it_email')}{' '}
        <a href="mailto:privacy@alafia.app">privacy@alafia.app</a> {t('Help.from_your_account_address_we_confirm_it')}
      </>
    ),
  },
  {
    q: 'Is ALAFIA medical advice?',
    a: (
      <>
        {t('Help.no_alafia_organises_your_health')}
      </>
    ),
  },
];

export default function Help() {
  return (
    <MarketingPage>
      <section className="section-wrap section-wrap--top">
        <div className="section-head">
          <span className="eyebrow">HELP CENTRE</span>
          <h2>{t('Help.how_can_we_help')}</h2>
          <p>{t('Help.start_with_the_basics_below_then_check')}</p>
        </div>

        <div className="features-grid">
          {START_HERE.map(s => (
            <div className="feat-card" key={s.title}>
              <span className="feat-icon">{s.icon}</span>
              <h3>{s.title}</h3>
              <p>{s.desc}</p>
              <Link className="card-link" to={s.to}>{t('Help.open')}</Link>
            </div>
          ))}
        </div>
      </section>

      <section className="section-wrap section-wrap--narrow" style={{ paddingTop: 0 }}>
        <div className="section-head">
          <span className="eyebrow">FREQUENTLY ASKED</span>
          <h2>{t('Help.questions')}</h2>
        </div>

        <div className="faq-list">
          {FAQ.map(item => (
            <details className="faq-item" key={item.q}>
              <summary>{item.q}</summary>
              <div className="faq-answer">{item.a}</div>
            </details>
          ))}
        </div>

        <div className="callout callout--danger">
          <strong>{t('Help.in_an_emergency_do_not_use_alafia')}</strong> {t('Help.call_your_local_emergency_number_or_go')}
        </div>

        <div className="mk-cta">
          <p className="mk-cta-note">{t('Help.still_stuck_a_human_will_read_it')}</p>
          <Link to="/contact" className="btn-primary-lg">{t('Help.contact_us')}</Link>
        </div>
      </section>
    </MarketingPage>
  );
}
