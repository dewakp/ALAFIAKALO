import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Angel, MarketingFooter, MarketingNav, Orb, SnowCanvas } from '../components/MarketingChrome';
import './Landing.css';

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

// ── Main Landing Component ────────────────────────────────────────────────────
export default function Landing() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const features = [
    { icon: '🤖', title: 'AI Health Companion', desc: 'Agentic AI that learns your patterns and delivers personalized health guidance around the clock.' },
    { icon: '🧬', title: 'Lab Intelligence', desc: 'Upload lab results and unlock AI-powered trend charts, anomaly detection, and plain-language explanations.' },
    { icon: '💊', title: 'Smart Medications', desc: 'Track every prescription, dosage, and refill across all providers with pharmacy integration.' },
    { icon: '🥗', title: 'Nutrition & Pantry', desc: 'Log meals, manage pantry inventory, scan ingredients, and receive AI-generated meal plans.' },
    { icon: '🏋️', title: 'Fitness & Exercise', desc: 'Log workouts, generate personalized exercise plans, and visualize progress over time.' },
    { icon: '🧠', title: 'Mental Wellness', desc: 'Mood tracking, stress journaling, mindfulness tools, and mental health resource library.' },
    { icon: '🏥', title: 'Telehealth', desc: 'Connect with physicians, coordinate your care team, and manage appointments from one hub.' },
    { icon: '📊', title: 'Health Charts', desc: 'Beautiful AI-powered dashboards visualizing every dimension of your health over time.' },
    { icon: '🌍', title: 'Community & Safety', desc: 'FDA recall alerts, wellness resources, and evidence-based community health knowledge.' },
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
            ✦ Agentic Health Intelligence · Est. 2026 ✦
          </div>

          <h1 className="hero-h1">
            <span className="h1-plain">Heal Smarter.</span>
            <span className="h1-gradient">Live Infinitely.</span>
          </h1>

          <p className="hero-sub">
            ALAFIA is an Intelligent health platform that unifies your entire health universe —
            labs, medications, fitness, nutrition, mental wellness, and clinical care — into one
            intelligent, wholesome experience.
          </p>

          <div className="hero-actions">
            <button className="btn-primary-lg" onClick={() => navigate(user ? '/' : '/register')}>
              {user ? 'Open Dashboard →' : 'Begin Your Journey ✦'}
            </button>
            {!user && (
              <button className="btn-ghost-lg" onClick={() => navigate('/login')}>
                Sign In
              </button>
            )}
          </div>

          <div className="hero-stats">
            <Stat value="30+" label="Health Modules" />
            <div className="stat-divider" />
            <Stat value="AI" label="Powered" />
            <div className="stat-divider" />
            <Stat value="3" label="Platforms" />
            <div className="stat-divider" />
            <Stat value="∞" label="Possibilities" />
          </div>
        </div>

        <div className="hero-glow-ring" />
        <div className="hero-bottom-fade" />
      </section>

      {/* ══ TAGLINE BAND ════════════════════════════════════════════════════ */}
      <div className="tagline-band">
        <span>🕊️ Wholeness of Body</span>
        <span className="divider">✦</span>
        <span>💡 Intelligence of Mind</span>
        <span className="divider">✦</span>
        <span>🌿 Healing of Spirit</span>
        <span className="divider">✦</span>
        <span>🌍 Health for All Humanity</span>
      </div>

      {/* ══ FEATURES ════════════════════════════════════════════════════════ */}
      <section className="section-wrap" id="features">
        <div className="section-head">
          <span className="eyebrow">PLATFORM CAPABILITIES</span>
          <h2>Everything Your Health Deserves</h2>
          <p>A complete health ecosystem — intelligent, connected, and beautifully human.</p>
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
            <h2>A Health Utopia for Every Human</h2>
            <p>
              We believe every person deserves a guardian angel for their health — an intelligent,
              compassionate companion that never sleeps, never forgets, and always advocates for
              your total wellbeing.
            </p>
            <p>
              ALAFIA (meaning <em>"health/peace/wellbeing"</em> in Yoruba) was born from the vision that
              advanced healthcare intelligence should be universal — not a privilege for the few,
              but a fundamental right for all.
            </p>
            <p>
              Our agentic AI doesn't just store data. It understands you, learns from you, and
              works alongside you to chart a course toward optimal health — mind, body, and spirit.
            </p>
            <Link to="/register" className="btn-vision">Join the Movement ✦</Link>
          </div>
        </div>
      </section>

      {/* ══ PLATFORMS ═══════════════════════════════════════════════════════ */}
      <section className="section-wrap section-wrap--narrow" id="platforms">
        <div className="section-head">
          <span className="eyebrow">AVAILABLE ON</span>
          <h2>Your Health, Everywhere</h2>
          <p>Seamlessly experience ALAFIA across all your devices.</p>
        </div>
        <div className="platforms-grid">
          <div className="platform-card">
            <span className="platform-icon">🌐</span>
            <h3>Web</h3>
            <p>Full-featured dashboard accessible from any modern browser.</p>
            <Link to="/login" className="platform-link">Launch App →</Link>
          </div>
          <div className="platform-card platform-card--featured">
            <div className="platform-badge">Most Popular</div>
            <span className="platform-icon">📱</span>
            <h3>iOS</h3>
            <p>Native SwiftUI app built for iPhone and iPad.</p>
            <span className="platform-link platform-link--soon">Coming to App Store</span>
          </div>
          <div className="platform-card">
            <span className="platform-icon">🤖</span>
            <h3>Android</h3>
            <p>Native Jetpack Compose app for all Android devices.</p>
            <span className="platform-link platform-link--soon">Coming to Play Store</span>
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
        <h2>Your Guardian Angel Awaits</h2>
        <p>Join the movement toward total health sovereignty and intelligent living.</p>
        <div className="cta-actions">
          <Link to="/register" className="btn-primary-lg">Create Free Account ✦</Link>
          <Link to="/login" className="btn-ghost-lg">Sign In</Link>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
