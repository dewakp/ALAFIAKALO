import { useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './Landing.css';

// ── Snow + Star Particle Canvas ────────────────────────────────────────────────
function SnowCanvas() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    let raf;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    // Mix of round snowflakes and sparkle crosses
    const flakes = Array.from({ length: 220 }, (_, i) => ({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      r: Math.random() * 2.5 + 0.4,
      speed: Math.random() * 0.7 + 0.2,
      drift: (Math.random() - 0.5) * 0.35,
      opacity: Math.random() * 0.75 + 0.15,
      wobble: Math.random() * Math.PI * 2,
      wobbleSpeed: (Math.random() - 0.5) * 0.018,
      isStar: i % 7 === 0,   // every 7th particle is a sparkle cross
      rotation: Math.random() * Math.PI,
      rotSpeed: (Math.random() - 0.5) * 0.01,
    }));

    function drawStar(x, y, r, opacity) {
      ctx.save();
      ctx.globalAlpha = opacity;
      ctx.strokeStyle = `rgba(190,225,255,${opacity})`;
      ctx.lineWidth = r * 0.7;
      ctx.lineCap = 'round';
      ctx.shadowColor = 'rgba(100,200,255,0.9)';
      ctx.shadowBlur = 6;
      // 4-point cross sparkle
      for (let a = 0; a < 4; a++) {
        const angle = (a * Math.PI) / 2;
        ctx.beginPath();
        ctx.moveTo(x + Math.cos(angle) * r * 0.3, y + Math.sin(angle) * r * 0.3);
        ctx.lineTo(x + Math.cos(angle) * r * 1.6, y + Math.sin(angle) * r * 1.6);
        ctx.stroke();
      }
      ctx.restore();
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      flakes.forEach(f => {
        f.wobble += f.wobbleSpeed;
        f.x += f.drift + Math.sin(f.wobble) * 0.25;
        f.y += f.speed;
        f.rotation += f.rotSpeed;
        if (f.y > canvas.height + 5) { f.y = -5; f.x = Math.random() * canvas.width; }
        if (f.x > canvas.width + 5) f.x = 0;
        if (f.x < -5) f.x = canvas.width;

        if (f.isStar) {
          ctx.save();
          ctx.translate(f.x, f.y);
          ctx.rotate(f.rotation);
          drawStar(0, 0, f.r * 1.8, f.opacity);
          ctx.restore();
        } else {
          ctx.save();
          ctx.shadowColor = 'rgba(140,200,255,0.7)';
          ctx.shadowBlur = 5;
          ctx.beginPath();
          ctx.arc(f.x, f.y, f.r, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(215,235,255,${f.opacity})`;
          ctx.fill();
          ctx.restore();
        }
      });
      raf = requestAnimationFrame(draw);
    }

    draw();
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', resize); };
  }, []);

  return <canvas ref={canvasRef} className="snow-canvas" />;
}

// ── Angel SVG ─────────────────────────────────────────────────────────────────
function Angel({ className = '', size = 150 }) {
  const w = size;
  const h = size * 1.4;
  return (
    <svg viewBox="0 0 120 168" width={w} height={h} className={`angel-svg ${className}`} aria-hidden="true">
      {/* Halo glow */}
      <ellipse cx="60" cy="17" rx="27" ry="8" fill="none" stroke="rgba(255,220,60,0.35)" strokeWidth="6" />
      <ellipse cx="60" cy="17" rx="27" ry="8" fill="none" stroke="#ffd700" strokeWidth="2" />
      <ellipse cx="60" cy="17" rx="27" ry="8" fill="rgba(255,220,60,0.07)" />

      {/* Left wing — outer */}
      <path d="M58,58 C42,22 0,12 1,48 C2,82 44,88 58,68" fill="rgba(180,210,255,0.45)" />
      {/* Left wing — inner feathers */}
      <path d="M58,58 C46,36 18,30 14,52 C10,70 41,78 58,68" fill="rgba(210,228,255,0.35)" />
      <path d="M58,60 C50,42 28,38 24,56 C22,68 44,73 58,68" fill="rgba(230,240,255,0.25)" />

      {/* Right wing — outer */}
      <path d="M62,58 C78,22 120,12 119,48 C118,82 76,88 62,68" fill="rgba(180,210,255,0.45)" />
      {/* Right wing — inner feathers */}
      <path d="M62,58 C74,36 102,30 106,52 C110,70 79,78 62,68" fill="rgba(210,228,255,0.35)" />
      <path d="M62,60 C70,42 92,38 96,56 C98,68 76,73 62,68" fill="rgba(230,240,255,0.25)" />

      {/* Wing shimmer lines */}
      <path d="M58,62 C44,48 18,44 10,60" stroke="rgba(255,255,255,0.2)" strokeWidth="0.8" fill="none" />
      <path d="M62,62 C76,48 102,44 110,60" stroke="rgba(255,255,255,0.2)" strokeWidth="0.8" fill="none" />

      {/* Body / robe */}
      <path d="M47,63 Q44,82 41,110 Q45,118 60,120 Q75,118 79,110 Q76,82 73,63 Z"
        fill="rgba(230,240,255,0.65)" />
      {/* Robe sheen */}
      <path d="M53,65 Q51,85 50,108" stroke="rgba(255,255,255,0.3)" strokeWidth="1.5" fill="none" />

      {/* Arms */}
      <path d="M47,69 C34,74 22,82 17,96" stroke="rgba(220,235,255,0.7)" strokeWidth="5" strokeLinecap="round" fill="none" />
      <path d="M73,69 C86,74 98,82 103,96" stroke="rgba(220,235,255,0.7)" strokeWidth="5" strokeLinecap="round" fill="none" />
      {/* Hands (small orbs of healing light) */}
      <circle cx="16" cy="97" r="4" fill="rgba(0,212,255,0.4)" />
      <circle cx="16" cy="97" r="4" fill="none" stroke="rgba(0,212,255,0.6)" strokeWidth="1" />
      <circle cx="104" cy="97" r="4" fill="rgba(0,212,255,0.4)" />
      <circle cx="104" cy="97" r="4" fill="none" stroke="rgba(0,212,255,0.6)" strokeWidth="1" />

      {/* Head */}
      <circle cx="60" cy="43" r="15" fill="rgba(255,245,225,0.88)" />
      {/* Hair */}
      <path d="M46,40 Q48,28 60,28 Q72,28 74,40" fill="rgba(200,170,100,0.6)" />

      {/* Radiance aura */}
      <ellipse cx="60" cy="90" rx="35" ry="45" fill="none" stroke="rgba(0,212,255,0.07)" strokeWidth="10" />
      <ellipse cx="60" cy="90" rx="28" ry="38" fill="none" stroke="rgba(100,200,255,0.05)" strokeWidth="6" />
    </svg>
  );
}

// ── Ambient Orb ───────────────────────────────────────────────────────────────
function Orb({ style }) {
  return <div className="ambient-orb" style={style} />;
}

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

      {/* ══ NAVBAR ══════════════════════════════════════════════════════════ */}
      <nav className="land-nav">
        <div className="land-logo">
          <span className="land-logo-icon">⚕</span>
          <span className="land-logo-text">ALAFIA</span>
        </div>
        <ul className="land-navlinks">
          <li><a href="#features">Features</a></li>
          <li><a href="#vision">Vision</a></li>
          <li><a href="#platforms">Platforms</a></li>
          {user ? (
            <li>
              <button className="nav-cta nav-cta--primary" onClick={() => navigate('/')}>
                Go to Dashboard
              </button>
            </li>
          ) : (
            <>
              <li><Link to="/login" className="nav-cta nav-cta--ghost">Sign In</Link></li>
              <li><Link to="/register" className="nav-cta nav-cta--primary">Get Started ✦</Link></li>
            </>
          )}
        </ul>
      </nav>

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
            ALAFIA is an agentic AI health platform that unifies your entire health universe —
            labs, medications, fitness, nutrition, mental wellness, and clinical care — into one
            intelligent, radiant experience.
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

      {/* ══ FOOTER ══════════════════════════════════════════════════════════ */}
      <footer className="land-footer">
        <div className="land-logo" style={{ justifyContent: 'center', marginBottom: '0.5rem' }}>
          <span className="land-logo-icon">⚕</span>
          <span className="land-logo-text">ALAFIA</span>
        </div>
        <p className="footer-tagline">Healing Intelligence for All Humanity</p>
        <div className="footer-links">
          <Link to="/login">Sign In</Link>
          <Link to="/register">Register</Link>
          <a href="#features">Features</a>
          <a href="#vision">Vision</a>
          <a href="#platforms">Platforms</a>
        </div>
        <p className="footer-copy">© 2026 ALAFIA. All rights reserved. Built with ❤️ for humanity.</p>
      </footer>
    </div>
  );
}
