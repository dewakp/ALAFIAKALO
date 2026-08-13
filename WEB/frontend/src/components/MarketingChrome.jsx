/**
 * Chrome shared by every public marketing page (Landing, Help, Contact,
 * Investors) — the particle canvas, the angel, the navbar and the footer.
 *
 * They live here rather than in Landing.jsx so that adding a link adds it to
 * every marketing page at once. The navbar carries the sales path only; Help,
 * Investors and Contact Us belong in the footer.
 */
import { useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import '../pages/Landing.css';

// ── Snow + Star Particle Canvas ────────────────────────────────────────────────
export function SnowCanvas() {
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
export function Angel({ className = '', size = 150 }) {
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
export function Orb({ style }) {
  return <div className="ambient-orb" style={style} />;
}

/**
 * A link to one of the landing page's own sections. `#features` only means
 * anything while the landing page is mounted, so from any other page it has to
 * be a real navigation — that also lets the browser do the anchor scroll,
 * which react-router does not do for hashes.
 */
function SectionLink({ hash, children }) {
  const { pathname } = useLocation();
  const onLanding = pathname === '/landing';
  return <a href={onLanding ? `#${hash}` : `/landing#${hash}`}>{children}</a>;
}

// ── Navbar ────────────────────────────────────────────────────────────────────
export function MarketingNav() {
  const navigate = useNavigate();
  const { user } = useAuth();

  return (
    <nav className="land-nav">
      <Link to="/landing" className="land-logo">
        <span className="land-logo-icon">⚕</span>
        <span className="land-logo-text">ALAFIA</span>
      </Link>
      <ul className="land-navlinks">
        <li><SectionLink hash="features">Features</SectionLink></li>
        <li><SectionLink hash="vision">Vision</SectionLink></li>
        <li><SectionLink hash="platforms">Platforms</SectionLink></li>
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
  );
}

// ── Footer ────────────────────────────────────────────────────────────────────
export function MarketingFooter() {
  return (
    <footer className="land-footer">
      <div className="land-logo" style={{ justifyContent: 'center', marginBottom: '0.5rem' }}>
        <span className="land-logo-icon">⚕</span>
        <span className="land-logo-text">ALAFIA</span>
      </div>
      <p className="footer-tagline">Healing Intelligence for All Humanity</p>
      <div className="footer-links">
        <Link to="/login">Sign In</Link>
        <Link to="/register">Register</Link>
        <SectionLink hash="features">Features</SectionLink>
        <SectionLink hash="vision">Vision</SectionLink>
        <SectionLink hash="platforms">Platforms</SectionLink>
        <Link to="/help">Help</Link>
        <Link to="/investors">Investors</Link>
        <Link to="/contact">Contact Us</Link>
        <Link to="/privacy">Privacy</Link>
      </div>
      <p className="footer-copy">© 2026 ALAFIA. All rights reserved. Built with ❤️ for humanity.</p>
    </footer>
  );
}

/**
 * Full-page shell for the marketing sub-pages. Landing.jsx does not use this —
 * it composes the same pieces around its own hero-first layout.
 */
export default function MarketingPage({ children }) {
  return (
    <div className="landing marketing-page">
      <SnowCanvas />
      <Orb style={{ top: '6%', left: '3%', width: 420, height: 420, background: 'radial-gradient(circle, rgba(0,212,255,0.07) 0%, transparent 70%)' }} />
      <Orb style={{ top: '45%', right: '2%', width: 520, height: 520, background: 'radial-gradient(circle, rgba(139,92,246,0.08) 0%, transparent 70%)' }} />
      <MarketingNav />
      <main className="marketing-main">{children}</main>
      <MarketingFooter />
    </div>
  );
}
