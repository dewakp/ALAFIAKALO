import { Link } from 'react-router-dom';
import MarketingPage from '../components/MarketingChrome';

const START_HERE = [
  {
    icon: '✨',
    title: 'Ask ALAFIA',
    desc: 'The fastest way in. Describe what you want to log or know in plain language and ALAFIA routes it to the right place.',
    to: '/',
  },
  {
    icon: '🥗',
    title: 'Log a meal',
    desc: 'Type or photograph what you ate. Calories and nutrients are filled in for you a few seconds later.',
    to: '/nutrition',
  },
  {
    icon: '🧬',
    title: 'Add lab results',
    desc: 'Upload a PDF or enter values by hand, then watch each marker trend over time on the charts.',
    to: '/labs',
  },
  {
    icon: '🔗',
    title: 'Connect your records',
    desc: 'Link an existing patient portal so your history comes across instead of being retyped.',
    to: '/data-sharing',
  },
];

const FAQ = [
  {
    q: 'Why does my meal say “estimating…” instead of showing calories?',
    a: (
      <>
        Because it is still being worked out. Your meal is saved the moment you submit it, and the
        nutrient breakdown is estimated in the background straight afterwards — that lookup can take
        several seconds for a long meal. The entry updates itself when it lands, so there is nothing
        to re-submit. If it ends up marked as failed, edit the entry and save it again.
      </>
    ),
  },
  {
    q: 'I forgot my password.',
    a: (
      <>
        Use <Link to="/forgot-password">Forgot password</Link>. We email you a link that opens the
        reset form; the link is single-use and expires, so request a fresh one if it has been
        sitting in your inbox for a while.
      </>
    ),
  },
  {
    q: 'The verification or reset email never arrived.',
    a: (
      <>
        Check your spam and promotions folders first, and confirm the address on the account is
        spelled correctly. If it still has not appeared, email{' '}
        <a href="mailto:contact@alafia.app">contact@alafia.app</a> from the address you signed up
        with and we will sort it out manually.
      </>
    ),
  },
  {
    q: 'Who can see my health data?',
    a: (
      <>
        You, and whoever you deliberately share it with. Sharing with a clinician is something you
        switch on per recipient, and it can be switched off again. Meal photos are only kept for
        model training if you have opted in to collective insights — that setting is off unless you
        turn it on.
      </>
    ),
  },
  {
    q: 'Can I use ALAFIA on my phone?',
    a: (
      <>
        The web app works in any modern mobile browser today. Native iOS and Android apps are
        built and heading for the App Store and Play Store — see{' '}
        <a href="/landing#platforms">Platforms</a> for where each one stands.
      </>
    ),
  },
  {
    q: 'What does a membership change?',
    a: (
      <>
        Tiers and what each one unlocks are listed on the{' '}
        <Link to="/subscription">Membership</Link> page inside the app, where you can also change or
        cancel your plan.
      </>
    ),
  },
  {
    q: 'How do I delete my account and my data?',
    a: (
      <>
        Ask us and we will do it. Email{' '}
        <a href="mailto:privacy@alafia.app">privacy@alafia.app</a> from your account address; we
        confirm it is really you before anything is erased, because deletion cannot be undone.
      </>
    ),
  },
  {
    q: 'Is ALAFIA medical advice?',
    a: (
      <>
        No. ALAFIA organises your health information and points out patterns in it. It does not
        diagnose, prescribe, or replace your clinician, and it must never be used to decide whether
        an emergency needs attention.
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
          <h2>How can we help?</h2>
          <p>Start with the basics below, then check the questions we get asked most.</p>
        </div>

        <div className="features-grid">
          {START_HERE.map(s => (
            <div className="feat-card" key={s.title}>
              <span className="feat-icon">{s.icon}</span>
              <h3>{s.title}</h3>
              <p>{s.desc}</p>
              <Link className="card-link" to={s.to}>Open →</Link>
            </div>
          ))}
        </div>
      </section>

      <section className="section-wrap section-wrap--narrow" style={{ paddingTop: 0 }}>
        <div className="section-head">
          <span className="eyebrow">FREQUENTLY ASKED</span>
          <h2>Questions</h2>
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
          <strong>In an emergency, do not use ALAFIA.</strong> Call your local emergency number or
          go to the nearest emergency department.
        </div>

        <div className="mk-cta">
          <p className="mk-cta-note">Still stuck? A human will read it.</p>
          <Link to="/contact" className="btn-primary-lg">Contact Us ✦</Link>
        </div>
      </section>
    </MarketingPage>
  );
}
