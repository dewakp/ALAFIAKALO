import { Link } from 'react-router-dom';
import MarketingPage from '../components/MarketingChrome';

/**
 * Public privacy policy. Also the Privacy Policy URL required by App Store
 * Connect and Google Play.
 *
 * Every statement here is meant to describe what the software actually does —
 * the collected-data list is the same one declared in the iOS privacy manifest
 * (IOS/ALAFIA/Resources/PrivacyInfo.xcprivacy), so the two cannot drift into
 * contradicting each other. If you change what the app collects, change both.
 */

const LAST_UPDATED = '13 August 2026';

const COLLECTED = [
  {
    icon: '❤️',
    title: 'Health and fitness',
    desc: 'Meals, nutrients, vitals, lab results, medications, symptoms, conditions, dialysis and chemotherapy records, mood, sleep and activity — including data you choose to sync from Apple Health.',
  },
  {
    icon: '👤',
    title: 'Account details',
    desc: 'Your name, email address, phone number if you provide one, and profile facts such as date of birth, sex, blood type and insurance details.',
  },
  {
    icon: '📷',
    title: 'Photos you attach',
    desc: 'Meal photos you add so ALAFIA can estimate nutrition, and any documents you upload such as lab reports. A meal photo is read first by ALAFIA\'s own vision model; if that is unavailable it is sent to a third-party vision provider with nothing attached to it — no name, no account, no notes.',
  },
  {
    icon: '📝',
    title: 'What you write',
    desc: 'Journal entries, notes and the messages you send to the AI assistant.',
  },
];

const NEVER = [
  'We do not sell your data. Not to anyone, for any purpose.',
  'We do not use your data for advertising, and there are no advertising SDKs in our apps.',
  'We do not track you across other companies’ apps or websites. ALAFIA contains no tracking SDK and requests no advertising identifier.',
  'We do not use your health data to train third-party AI models.',
];

export default function Privacy() {
  return (
    <MarketingPage>
      <section className="section-wrap section-wrap--top section-wrap--narrow">
        <div className="section-head">
          <span className="eyebrow">YOUR DATA</span>
          <h2>Privacy</h2>
          <p>
            ALAFIA holds some of the most sensitive information a person has. This page explains
            plainly what we collect, why, who can see it, and how to get it back or delete it.
          </p>
        </div>

        <p className="mk-cta-note">Last updated {LAST_UPDATED}.</p>

        <h3>What we collect</h3>
        <p>
          Only what the app needs to work. Everything below is tied to your account — you cannot
          have a health record without somewhere to put it.
        </p>
        <div className="features-grid">
          {COLLECTED.map(c => (
            <div className="feat-card" key={c.title}>
              <span className="feat-icon">{c.icon}</span>
              <h3>{c.title}</h3>
              <p>{c.desc}</p>
            </div>
          ))}
        </div>

        <h3>What we never do</h3>
        <ul className="mk-list">
          {NEVER.map(n => <li key={n}>{n}</li>)}
        </ul>

        <h3>Where your data goes</h3>
        <p>
          ALAFIA runs on Google Cloud in the United States, and your records are stored in an
          encrypted database there. Data travels over encrypted connections (HTTPS/TLS).
        </p>
        <p>
          <strong>You are never identified to an AI provider.</strong> ALAFIA's AI
          features are answered by established model providers we work with. Before a
          request leaves ALAFIA it is de-identified at a single point that every AI
          call passes through: your name, email address, phone number, date of birth,
          record numbers and the names of clinicians you mention are removed, and you
          are represented by a token we issue — something like
          <code>alafia-ba9e8bb2f9077c6e</code>, which means nothing outside ALAFIA and
          cannot be linked back to you by the provider.
        </p>
        <p>
          What the provider receives is the health detail needed to answer your
          question — a lab value, a medication and its dose — attached to that token
          rather than to you. Providers are used under terms that do not permit
          training on submitted data, and <strong>your data is never used to train
          anyone's models.</strong> You choose whether to enable AI features at all,
          and can turn them off at any time.
        </p>
        <p>
          A small number of service providers process narrow slices of data strictly on our behalf,
          and none of them receive your health records:
        </p>
        <ul className="mk-list">
          <li><strong>Payments</strong> — Stripe handles web subscriptions, and the App Store or Google Play handles in-app ones. They receive your billing details; we never see or store your full card number.</li>
          <li><strong>Email</strong> — Resend delivers account email such as password resets and address verification, and occasional product announcements. It receives your email address. Every announcement carries a one-click unsubscribe; account email is essential to your account and cannot be turned off while it is open.</li>
          <li><strong>Nutrition reference data</strong> — we look food up in the USDA FoodData Central database. We send the food name, never anything about you.</li>
        </ul>

        <h3>Your rights</h3>
        <p>
          Wherever you live, you can exercise all of these — we do not limit them by region:
        </p>
        <ul className="mk-list">
          <li><strong>See it</strong> — every record is visible in the app.</li>
          <li><strong>Export it</strong> — request a machine-readable copy of everything we hold.</li>
          <li><strong>Correct it</strong> — edit your records directly, with a few fields locked after signup for clinical-safety reasons.</li>
          <li><strong>Delete it</strong> — request deletion of your account and its data.</li>
          <li><strong>Withdraw consent</strong> — optional data uses are off unless you turn them on, and can be turned back off at any time in Privacy Settings.</li>
        </ul>
        <p>
          Signed in, these live under <strong>Privacy Settings</strong>. Otherwise email{' '}
          <a className="card-link" href="mailto:privacy@alafia.app">privacy@alafia.app</a> and we
          will action it.
        </p>

        <h3>Improving ALAFIA</h3>
        <p>
          A meal photo you take is kept with that meal, so you — and any clinician you have chosen
          to share with — can open the entry later and see what was actually eaten. That is part of
          your own record.
        </p>
        <p>
          Using those photos to <strong>train a shared model</strong> is a separate question, and it
          is <strong>off by default</strong>. Your photos and corrections only help ALAFIA get
          better at recognising food for everyone if you explicitly turn on collective insights in
          Privacy Settings, and turning it off stops it.
        </p>

        <h3>Children and families</h3>
        <p>
          ALAFIA has no age limit. Health is a lifelong concern, and a parent tracking a child's
          condition is a case we build for deliberately rather than one we exclude.
        </p>
        <p>
          An account for a child should be created and managed by a parent or legal guardian, who
          is responsible for what is added to it and can export or delete it at any time.
        </p>

        <h3>How long we keep it</h3>
        <p>
          Your records are kept while your account is open, because a health history is only useful
          over time. When you delete your account we remove your personal data, retaining only what
          the law requires us to keep — such as payment records for tax purposes.
        </p>

        <h3>Changes</h3>
        <p>
          If we make a material change to this policy we will tell you in the app or by email rather
          than quietly editing this page.
        </p>

        <div className="callout callout--danger">
          <strong>Not medical advice, and not an emergency service.</strong> ALAFIA helps you
          organise and understand your health information. It does not replace your clinician. In an
          emergency, call your local emergency number.
        </div>

        <div className="mk-cta">
          <p className="mk-cta-note">
            Questions about any of this go to{' '}
            <a className="card-link" href="mailto:privacy@alafia.app">privacy@alafia.app</a>, or the
            Data Protection Officer at{' '}
            <a className="card-link" href="mailto:dpo@alafia.app">dpo@alafia.app</a>. Other enquiries
            belong on the <Link to="/contact">Contact</Link> page.
          </p>
          <Link to="/contact" className="btn-primary-lg">Contact Us ✦</Link>
        </div>
      </section>
    </MarketingPage>
  );
}
