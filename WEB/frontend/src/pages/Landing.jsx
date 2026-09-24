import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Angel, MarketingFooter, MarketingNav, Orb, SnowCanvas } from '../components/MarketingChrome';
import './Landing.css';
import { t } from '../i18n';

// ── Feature Card ──────────────────────────────────────────────────────────────
function FeatureCard({ icon, title, desc, delay = 0 }) {
  return (
    <div className="feat-card" style={{ animationDelay: `${delay}ms` }}>
      <span className="feat-icon">{icon}</span>
      <h3>{title}</h3>
      <p>{desc}</p>
    </div>
  );
}

// ── Stat ──────────────────────────────────────────────────────────────────────
function Stat({ value, label }) {
  return (
    <div className="hero-stat">
      <span className="stat-val">{value}</span>
      <span className="stat-lbl">{label}</span>
    </div>
  );
}

// ── iOS beta request ──────────────────────────────────────────────────────────
/* The iPhone card used to end in an inert grey "Coming to App Store" label.
   There IS a build — it just is not on the store yet — so the card now offers
   the thing that exists.

   It posts to /api/v1/contact with the `beta_ios` TOPIC. The client sends a
   key and never an address, so no field here can point the form at a recipient
   of someone else's choosing; the server resolves the desk. Same endpoint,
   same honeypot, same rate limit, and the row is written before any mail is
   attempted — alafia.app has no MX records, so a version that only emailed
   would bounce where nobody looks (CLAUDE.md §3d).

   Subscription status is COLLECTED, never checked. Verifying a typed address
   against the subscriber table from a public unauthenticated form is an
   account-existence oracle (§3e); the check belongs at TestFlight invite time,
   where a person does it. */
function BetaRequest({ onClose }) {
  const [form, setForm] = useState({ name: '', email: '', notes: '', website: '' });
  const [status, setStatus] = useState('idle');   // idle | sending | sent | error
  const [error, setError] = useState('');
  const [reference, setReference] = useState('');

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  function readCookie(name) {
    return document.cookie.split('; ').find((c) => c.startsWith(`${name}=`))?.split('=')[1] || '';
  }

  async function csrfToken() {
    const token = readCookie('csrf_token');
    if (token) return token;
    await fetch('/api/v1/auth/csrf-cookie', { credentials: 'same-origin' });
    return readCookie('csrf_token');
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setStatus('sending');
    try {
      const res = await fetch('/api/v1/contact', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': await csrfToken() },
        body: JSON.stringify({
          topic: 'beta_ios',
          name: form.name,
          email: form.email,
          /* The endpoint requires a message of at least 10 characters and the
             notes are optional, so the form states its own intent and carries
             the notes after it. The row then reads sensibly in the inbox
             whether or not anything was typed. */
          message: `iOS beta request.${form.notes.trim() ? `\n\n${form.notes.trim()}` : ''}`,
          website: form.website,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        /* The server's own sentence. A generic failure hides the one useful
           thing — whether to try again or write to someone. */
        throw new Error(
          typeof data?.detail === 'string' ? data.detail : t('Landing.beta_could_not_send'),
        );
      }
      setReference(data.reference || '');
      setStatus('sent');
    } catch (err) {
      setStatus('error');
      setError(err.message);
    }
  }

  if (status === 'sent') {
    return (
      <div className="beta-panel">
        <h4>{t('Landing.beta_request_received')}</h4>
        <p>{t('Landing.beta_we_have_your_request')}</p>
        {reference && (
          <p className="beta-ref">
            {t('Landing.your_reference_is')} <strong>{reference}</strong>
          </p>
        )}
        <button type="button" className="platform-link" onClick={onClose}>
          {t('Landing.close')}
        </button>
      </div>
    );
  }

  return (
    <form className="beta-panel contact-form" onSubmit={handleSubmit} noValidate>
      <h4>{t('Landing.get_it_in_beta')}</h4>
      <p>{t('Landing.beta_blurb')}</p>

      <div className="form-group">
        <label htmlFor="beta-name">{t('Landing.your_name')}</label>
        <input id="beta-name" className="form-input" type="text" autoComplete="name"
          value={form.name} onChange={set('name')} required />
      </div>

      <div className="form-group">
        <label htmlFor="beta-email">{t('Landing.email')}</label>
        <input id="beta-email" className="form-input" type="email" autoComplete="email"
          value={form.email} onChange={set('email')} required />
      </div>

      <div className="form-group">
        <label htmlFor="beta-notes">{t('Landing.notes_optional')}</label>
        <textarea id="beta-notes" className="form-input" rows="3"
          value={form.notes} onChange={set('notes')} />
        <p className="form-hint">{t('Landing.beta_notes_hint')}</p>
      </div>

      {/* Honeypot — off-screen rather than display:none so it is not an obvious
          tell, and out of the tab order and assistive tech. */}
      <div aria-hidden="true" className="hp-field">
        <label htmlFor="beta-website">{t('Landing.leave_this_field_empty')}</label>
        <input id="beta-website" type="text" tabIndex={-1} autoComplete="off"
          value={form.website} onChange={set('website')} />
      </div>

      {error && <div className="callout callout--danger">{error}</div>}

      <div className="beta-actions">
        <button type="submit" className="btn-primary-lg" disabled={status === 'sending'}>
          {status === 'sending' ? t('Landing.sending') : t('Landing.request_beta')}
        </button>
        <button type="button" className="platform-link" onClick={onClose}>
          {t('Landing.cancel')}
        </button>
      </div>
    </form>
  );
}

// ── Main Landing Component ────────────────────────────────────────────────────
export default function Landing() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [betaOpen, setBetaOpen] = useState(false);

  const features = [
    { icon: '🤖', title: t('Landing.ai_health_companion'), desc: t('Landing.agentic_ai_that_learns_your_patterns_and') },
    { icon: '🧬', title: t('Landing.lab_intelligence'), desc: t('Landing.upload_lab_results_and_unlock_ai_powered') },
    { icon: '💊', title: t('Landing.smart_medications'), desc: t('Landing.track_every_prescription_dosage_and') },
    { icon: '🥗', title: t('Landing.nutrition_pantry'), desc: t('Landing.log_meals_manage_pantry_inventory_scan') },
    { icon: '🏋️', title: t('Landing.fitness_exercise'), desc: t('Landing.log_workouts_generate_personalized') },
    { icon: '🧠', title: t('Landing.mental_wellness'), desc: t('Landing.mood_tracking_stress_journaling') },
    { icon: '🏥', title: t('Landing.telehealth'), desc: t('Landing.connect_with_physicians_coordinate_your') },
    { icon: '📊', title: t('Landing.health_charts'), desc: t('Landing.beautiful_ai_powered_dashboards') },
    { icon: '🌍', title: t('Landing.community_safety'), desc: t('Landing.fda_recall_alerts_wellness_resources_and') },
  ];

  return (
    <div className="landing">
      <SnowCanvas />

      {/* Ambient background orbs */}
      <Orb style={{ top: '8%', left: '3%', width: 420, height: 420, background: 'radial-gradient(circle, rgba(0,212,255,0.07) 0%, transparent 70%)' }} />
      <Orb style={{ top: '35%', right: '2%', width: 520, height: 520, background: 'radial-gradient(circle, rgba(139,92,246,0.08) 0%, transparent 70%)' }} />
      <Orb style={{ bottom: '12%', left: '25%', width: 650, height: 450, background: 'radial-gradient(circle, rgba(16,185,129,0.05) 0%, transparent 70%)' }} />

      {/* Background angels (hero only) */}
      <div className="bg-angel bg-angel--left" aria-hidden="true">
        <Angel size={210} />
      </div>
      <div className="bg-angel bg-angel--right" aria-hidden="true">
        <Angel size={175} />
      </div>

      <MarketingNav />

      {/* ══ HERO ════════════════════════════════════════════════════════════ */}
      <section className="hero-section">
        <div className="hero-content">
          <div className="hero-badge">
            <span className="badge-orb" />
            {t('Landing.agentic_health_intelligence_est_2026')}
          </div>

          <h1 className="hero-h1">
            <span className="h1-plain">{t('Landing.heal_smarter')}</span>
            <span className="h1-gradient">{t('Landing.live_infinitely')}</span>
          </h1>

          <p className="hero-sub">
            {t('Landing.alafia_is_an_intelligent_health_platform')}
          </p>

          <div className="hero-actions">
            <button className="btn-primary-lg" onClick={() => navigate(user ? '/' : '/register')}>
              {user ? 'Open Dashboard →' : 'Begin Your Journey ✦'}
            </button>
            {!user && (
              <button className="btn-ghost-lg" onClick={() => navigate('/login')}>
                {t('Landing.sign_in')}
              </button>
            )}
          </div>

          <div className="hero-stats">
            <Stat value="30+" label={t('Landing.health_modules')} />
            <div className="stat-divider" />
            <Stat value="AI" label={t('Landing.powered')} />
            <div className="stat-divider" />
            <Stat value="3" label={t('Landing.platforms')} />
            <div className="stat-divider" />
            <Stat value="∞" label={t('Landing.possibilities')} />
          </div>
        </div>

        <div className="hero-glow-ring" />
        <div className="hero-bottom-fade" />
      </section>

      {/* ══ TAGLINE BAND ════════════════════════════════════════════════════ */}
      <div className="tagline-band">
        <span>{t('Landing.wholeness_of_body')}</span>
        <span className="divider">✦</span>
        <span>{t('Landing.intelligence_of_mind')}</span>
        <span className="divider">✦</span>
        <span>{t('Landing.healing_of_spirit')}</span>
        <span className="divider">✦</span>
        <span>{t('Landing.health_for_all_humanity')}</span>
      </div>

      {/* ══ FEATURES ════════════════════════════════════════════════════════ */}
      <section className="section-wrap" id="features">
        <div className="section-head">
          <span className="eyebrow">PLATFORM CAPABILITIES</span>
          <h2>{t('Landing.everything_your_health_deserves')}</h2>
          <p>{t('Landing.a_complete_health_ecosystem_intelligent')}</p>
        </div>
        <div className="features-grid">
          {features.map((f, i) => (
            <FeatureCard key={i} delay={i * 60} {...f} />
          ))}
        </div>
      </section>

      {/* ══ VISION / MANIFESTO ══════════════════════════════════════════════ */}
      <section className="vision-section" id="vision">
        <div className="vision-inner">
          <div className="vision-angel-wrap" aria-hidden="true">
            <div className="vision-angel-glow" />
            <Angel size={280} className="vision-angel" />
          </div>
          <div className="vision-text">
            <span className="eyebrow">OUR VISION</span>
            <h2>{t('Landing.a_health_utopia_for_every_human')}</h2>
            <p>
              {t('Landing.we_believe_every_person_deserves_a')}
            </p>
            <p>
              {t('Landing.alafia_meaning')} <em>{t('Landing.health_peace_wellbeing')}</em> {t('Landing.in_yoruba_was_born_from_the_vision_that')}
            </p>
            <p>
              {t('Landing.our_agentic_ai_doesn_t_just_store_data')}
            </p>
            <Link to="/register" className="btn-vision">{t('Landing.join_the_movement')}</Link>
          </div>
        </div>
      </section>

      {/* ══ PLATFORMS ═══════════════════════════════════════════════════════ */}
      <section className="section-wrap section-wrap--narrow" id="platforms">
        <div className="section-head">
          <span className="eyebrow">AVAILABLE ON</span>
          <h2>{t('Landing.your_health_everywhere')}</h2>
          <p>{t('Landing.seamlessly_experience_alafia_across_all')}</p>
        </div>
        <div className="platforms-grid">
          <div className="platform-card">
            <span className="platform-icon">🌐</span>
            <h3>{t('Landing.web')}</h3>
            <p>{t('Landing.full_featured_dashboard_accessible_from')}</p>
            <Link to="/login" className="platform-link">{t('Landing.launch_app')}</Link>
          </div>
          <div className="platform-card platform-card--featured">
            <div className="platform-badge">{t('Landing.most_popular')}</div>
            <span className="platform-icon">📱</span>
            <h3>{t('Landing.ios')}</h3>
            <p>{t('Landing.native_swiftui_app_built_for_iphone_and')}</p>
            {/* The store line stays — it is still true — and the beta sits
                beneath it, because a build exists today and the store does not. */}
            <span className="platform-link platform-link--soon">{t('Landing.coming_to_app_store')}</span>
            {betaOpen ? (
              <BetaRequest onClose={() => setBetaOpen(false)} />
            ) : (
              <button type="button" className="platform-link platform-link--cta"
                onClick={() => setBetaOpen(true)}>
                {t('Landing.get_it_in_beta')}
              </button>
            )}
          </div>
          <div className="platform-card">
            <span className="platform-icon">🤖</span>
            <h3>{t('Landing.android')}</h3>
            <p>{t('Landing.native_jetpack_compose_app_for_all')}</p>
            <span className="platform-link platform-link--soon">{t('Landing.coming_to_play_store')}</span>
          </div>
        </div>
      </section>

      {/* ══ FINAL CTA ═══════════════════════════════════════════════════════ */}
      <section className="cta-section">
        <div className="cta-angels" aria-hidden="true">
          <Angel size={130} className="cta-angel cta-angel--left" />
          <Angel size={130} className="cta-angel cta-angel--right" />
        </div>
        <div className="cta-glow" />
        <span className="eyebrow">START TODAY — IT'S FREE</span>
        <h2>{t('Landing.your_guardian_angel_awaits')}</h2>
        <p>{t('Landing.join_the_movement_toward_total_health')}</p>
        <div className="cta-actions">
          <Link to="/register" className="btn-primary-lg">{t('Landing.create_free_account')}</Link>
          <Link to="/login" className="btn-ghost-lg">{t('Landing.sign_in')}</Link>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
