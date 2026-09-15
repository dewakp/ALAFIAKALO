import { Link, NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useClinicianMode } from '../context/ClinicianModeContext';
import api from '../services/api';
import MembershipNudge from './MembershipNudge';
import LanguageSwitcher from './LanguageSwitcher';
import {
  Menu,
  LayoutDashboard,
  Apple,
  Dumbbell,
  FlaskConical,
  Pill,
  HeartPulse,
  Heart,
  Globe,
  Camera,
  User,
  UserCog,
  CalendarDays,
  Video,
  MessageSquare,
  Bot,
  Shield,
  Stethoscope,
  LogOut,
  BarChart3,
  Gauge,
  UtensilsCrossed,
  PersonStanding,
  ScanLine,
  FileText,
  Droplets,
  FileHeart,
  Share2,
  ChevronDown,
  Activity,
  BrainCircuit,
  ListChecks,
  Briefcase,
  Cross,
  Wrench,
  Bell,
  Package,
  FlaskRound,
  TrendingUp,
  BookOpen,
  AlertTriangle,
  History,
  Moon,
  Network,
  Radar,
  Building,
  Sparkles,
  HelpCircle,
  Mail,
  Users,
} from 'lucide-react';
import { t } from '../i18n';

const navGroups = [
  // Prompt Hub — the modality-aware entry point (Basis.md)
  { to: '/', icon: Bot, get label() { return t('Layout.ask_alafia'); } },
  // ── Firebase-matching primary nav ──
  {
    get label() { return t('Layout.overview_analysis'); }, icon: LayoutDashboard, children: [
      { to: '/dashboard', icon: LayoutDashboard, get label() { return t('Layout.dashboard'); } },
      { to: '/insights', icon: Network, get label() { return t('Layout.health_insights'); } },
      { to: '/chart-dashboard', icon: TrendingUp, get label() { return t('Layout.health_trends'); } },
      { to: '/wellness', icon: Gauge, get label() { return t('Layout.wellness_score'); } },
      { to: '/calendar', icon: CalendarDays, get label() { return t('Layout.calendar'); } },
    ],
  },
  {
    get label() { return t('Layout.meals'); }, icon: UtensilsCrossed, children: [
      { to: '/meal-planner', icon: UtensilsCrossed, get label() { return t('Layout.meal_planner'); } },
      { to: '/nutrition', icon: Apple, get label() { return t('Layout.log_food_intake'); } },
      { to: '/meals-diary', icon: BookOpen, get label() { return t('Layout.meals_diary'); } },
      { to: '/nutrient-tracking', icon: BarChart3, get label() { return t('Layout.nutrient_tracking'); } },
      { to: '/pantry', icon: Package, get label() { return t('Layout.pantry'); } },
    ],
  },
  // Conditions are a cornerstone of the record (they drive nutrient limits,
  // the clinician board and the AI coach), so they sit at the top level rather
  // than inside a collapsed group.
  { to: '/chronic-conditions', icon: Stethoscope, get label() { return t('Layout.conditions'); } },
  { to: '/medications', icon: Pill, get label() { return t('Layout.medications'); } },
  {
    get label() { return t('Layout.activities_logs'); }, icon: Activity, children: [
      { to: '/journal', icon: BookOpen, get label() { return t('Layout.journal'); } },
      { to: '/vitals', icon: HeartPulse, get label() { return t('Layout.vitals'); } },
      { to: '/elimination', icon: FlaskRound, get label() { return t('Layout.elimination_log'); } },
      { to: '/symptoms', icon: Activity, get label() { return t('Layout.symptoms'); } },
      { to: '/sleep', icon: Moon, get label() { return t('Layout.sleep'); } },
      { to: '/mood', icon: HeartPulse, get label() { return t('Layout.mood'); } },
      { to: '/lifestyle', icon: Activity, get label() { return t('Layout.lifestyle'); } },
    ],
  },
  {
    get label() { return t('Layout.labs_records'); }, icon: FlaskConical, children: [
      { to: '/labs', icon: FlaskConical, get label() { return t('Layout.lab_tests'); } },
      { to: '/lab-charts', icon: BarChart3, get label() { return t('Layout.charts'); } },
    ],
  },
  // Sharing is core, so it sits at the top level rather than inside a collapsed
  // group. It used to be "Connect Records" three clicks deep under
  // Labs & Records, where nobody could find it.
  { to: '/data-sharing', icon: Share2, get label() { return t('Layout.share_records'); } },
  {
    get label() { return t('Layout.therapies'); }, icon: Cross, children: [
      { to: '/hemodialysis', icon: Activity, get label() { return t('Layout.hd_flowsheet'); } },
      { to: '/peritoneal-dialysis', icon: Droplets, get label() { return t('Layout.pd_report'); } },
      { to: '/therapy-history', icon: History, get label() { return t('Layout.therapy_history'); } },
    ],
  },
  {
    get label() { return t('Layout.community_health'); }, icon: Globe, children: [
      { to: '/community', icon: Globe, get label() { return t('Layout.overview'); } },
      { to: '/physicians', icon: Stethoscope, get label() { return t('Layout.physician_directory'); } },
      { to: '/facilities', icon: Building, get label() { return t('Layout.facility_directory'); } },
      { to: '/fda-recalls', icon: AlertTriangle, get label() { return t('Layout.food_drug_recalls'); } },
      { to: '/surveillance', icon: Radar, get label() { return t('Layout.disease_surveillance'); } },
    ],
  },
  // ── Additional web features ──
  {
    get label() { return t('Layout.more'); }, icon: Wrench, children: [
      { to: '/fitness', icon: Dumbbell, get label() { return t('Layout.fitness'); } },
      { to: '/mental-health', icon: HeartPulse, get label() { return t('Layout.mental_health'); } },
      { to: '/exercise-planner', icon: PersonStanding, get label() { return t('Layout.exercise_planner'); } },
      { to: '/ai', icon: Bot, get label() { return t('Layout.ai_assistant'); } },
      { to: '/telehealth', icon: Video, get label() { return t('Layout.telehealth'); } },
      { to: '/messaging', icon: MessageSquare, get label() { return t('Layout.messaging'); } },
      { to: '/pharmacy', icon: Pill, get label() { return t('Layout.pharmacy'); } },
      { to: '/image-ai', icon: ScanLine, get label() { return t('Layout.image_ai'); } },
      { to: '/pdf-tools', icon: FileText, get label() { return t('Layout.pdf_tools'); } },
      { to: '/capture', icon: Camera, get label() { return t('Layout.capture'); } },
    ],
  },
  {
    get label() { return t('Layout.profile'); }, icon: User, children: [
      { to: '/profile', icon: User, get label() { return t('Layout.my_profile'); } },
      { to: '/subscription', icon: Sparkles, get label() { return t('Layout.alafia_membership'); } },
      { to: '/roles', icon: UserCog, get label() { return t('Layout.role'); } },
      { to: '/advanced-directives', icon: FileHeart, get label() { return t('Layout.advanced_directives'); } },
      { to: '/insurance', icon: Shield, get label() { return t('Layout.insurance'); } },
    ],
  },
];

// Clinician mode replaces the nav entirely rather than adding to it. A
// physician reviewing patients does not want their own meal diary in the way,
// and mixing the two is what made the clinical features hard to find.
const clinicianNavGroups = [
  { to: '/clinician-dashboard', icon: Users, get label() { return t('Layout.my_patients'); } },
  { to: '/data-sharing', icon: Share2, get label() { return t('Layout.share_records'); } },
  { to: '/messaging', icon: MessageSquare, get label() { return t('Layout.messaging'); } },
  { to: '/telehealth', icon: Video, get label() { return t('Layout.telehealth'); } },
  { to: '/calendar', icon: CalendarDays, get label() { return t('Layout.calendar'); } },
  { to: '/physicians', icon: Stethoscope, get label() { return t('Layout.physician_directory'); } },
  { to: '/facilities', icon: Building, get label() { return t('Layout.facilities'); } },
  {
    get label() { return t('Layout.account'); }, icon: User, children: [
      { to: '/profile', icon: User, get label() { return t('Layout.my_profile'); } },
      { to: '/roles', icon: UserCog, get label() { return t('Layout.role'); } },
      { to: '/subscription', icon: Sparkles, get label() { return t('Layout.alafia_membership'); } },
    ],
  },
];

/** Patient ⇄ Clinician switch. Only rendered for users who hold a clinical role. */
function PersonaSwitcher() {
  const { clinicianMode, canBeClinician, enterClinicianMode, exitClinicianMode } =
    useClinicianMode();
  const navigate = useNavigate();

  if (!canBeClinician) return null;

  const select = (toClinician) => {
    if (toClinician) {
      enterClinicianMode();
      navigate('/clinician-dashboard');
    } else {
      exitClinicianMode();
      navigate('/');
    }
  };

  return (
    <div style={{ margin: '0 12px 12px', display: 'flex', gap: 4, padding: 3, background: 'var(--color-bg)', borderRadius: 10 }}>
      {[
        { label: t('Layout.patient'), icon: User, active: !clinicianMode, to: false },
        { label: t('Layout.clinician'), icon: Stethoscope, active: clinicianMode, to: true },
      ].map(({ label, icon: Icon, active, to }) => (
        <button
          key={label}
          onClick={() => select(to)}
          aria-pressed={active}
          style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: 6, padding: '7px 8px', border: 'none', borderRadius: 8,
            cursor: 'pointer', fontSize: 13, fontWeight: 600,
            background: active ? 'var(--color-primary)' : 'transparent',
            color: active ? '#fff' : 'var(--color-text-secondary)',
          }}
        >
          <Icon size={15} /> {label}
        </button>
      ))}
    </div>
  );
}

// Sidebar footer. These are the public marketing pages, which render outside
// <Layout> — following one leaves the app shell, and its navbar links back in.
const FOOTER_LINKS = [
  { to: '/help', icon: HelpCircle, get label() { return t('Layout.help'); } },
  { to: '/contact', icon: Mail, get label() { return t('Layout.contact_us'); } },
  { to: '/investors', icon: Briefcase, get label() { return t('Layout.investors'); } },
];

function SidebarGroup({ group }) {
  const [open, setOpen] = useState(false);
  const GroupIcon = group.icon;
  const visibleChildren = group.children;

  return (
    <div className="sidebar-group">
      <button
        className={`sidebar-group-toggle${open ? ' open' : ''}`}
        onClick={() => setOpen(!open)}
      >
        <GroupIcon size={20} />
        <span style={{ flex: 1, textAlign: 'left' }}>{group.label}</span>
        <ChevronDown size={16} className={`sidebar-chevron${open ? ' rotated' : ''}`} />
      </button>
      {open && (
        <div className="sidebar-group-children">
          {visibleChildren.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `sidebar-link sidebar-link-child${isActive ? ' active' : ''}`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const { clinicianMode } = useClinicianMode();
  const navigate = useNavigate();
  const [unreadCount, setUnreadCount] = useState(0);
  const nav = clinicianMode ? clinicianNavGroups : navGroups;

  useEffect(() => {
    let cancelled = false;
    const fetchCount = async () => {
      try {
        const { data } = await api.get('/notifications/unread-count');
        if (!cancelled) setUnreadCount(data.count);
      } catch { /* ignore */ }
    };
    fetchCount();
    const interval = setInterval(fetchCount, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  /* Mobile navigation.
     The sidebar is `display: none` below 768px and nothing replaced it, so an
     authenticated phone user had NO navigation at all — every route was
     unreachable except by typing a URL. This adds a top bar with a menu button
     and a slide-in drawer holding the same nav. Desktop is unchanged: both are
     hidden at >=769px by CSS. */
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { pathname } = useLocation();

  // Close on navigate — otherwise the drawer stays over the page you just opened.
  useEffect(() => { setMobileNavOpen(false); }, [pathname]);

  // Escape closes it, and a drawer that is open must not let the page behind scroll.
  useEffect(() => {
    if (!mobileNavOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setMobileNavOpen(false); };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [mobileNavOpen]);

  return (
    <div className="app-layout">
      <header className="mobile-topbar">
        <button
          type="button"
          className="mobile-nav-toggle"
          aria-label={t('Layout.open_menu')}
          aria-expanded={mobileNavOpen}
          onClick={() => setMobileNavOpen(true)}
        >
          <Menu size={22} />
        </button>
        <span className="mobile-topbar-logo">ALAFIA</span>
        <button
          type="button"
          className="mobile-nav-toggle"
          aria-label={t('Layout.notifications')}
          onClick={() => navigate('/notifications')}
        >
          <Bell size={20} />
          {unreadCount > 0 && <span className="mobile-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>}
        </button>
      </header>

      {mobileNavOpen && (
        <div
          className="mobile-nav-backdrop"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside className={`sidebar${mobileNavOpen ? ' sidebar-mobile-open' : ''}`}>
        <div className="sidebar-logo">ALAFIA</div>
        <button
          onClick={() => navigate('/notifications')}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 16px', margin: '0 12px 8px',
            border: 'none', background: unreadCount > 0 ? '#e3f2fd' : 'transparent',
            borderRadius: 8, cursor: 'pointer', width: 'calc(100% - 24px)',
            fontSize: 14, color: 'inherit',
          }}
        >
          <Bell size={18} />
          <span style={{ flex: 1, textAlign: 'left' }}>{t('Layout.notifications')}</span>
          {unreadCount > 0 && (
            <span style={{
              background: '#d50000', color: '#fff', borderRadius: 10,
              padding: '1px 7px', fontSize: 11, fontWeight: 700, minWidth: 18,
              textAlign: 'center',
            }}>
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>
        <PersonaSwitcher />
        <nav className="sidebar-nav">
          {nav.map((item, idx) =>
            item.to ? (
              <NavLink
                key={item.to}
                to={item.to}
                end
                className={({ isActive }) =>
                  `sidebar-link${isActive ? ' active' : ''}`
                }
              >
                <item.icon size={20} />
                {item.label}
              </NavLink>
            ) : (
              <SidebarGroup key={item.label} group={item} />
            )
          )}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-footer-links">
            {FOOTER_LINKS.map(({ to, icon: Icon, label }) => (
              <Link key={to} to={to}>
                <Icon size={13} /> {label}
              </Link>
            ))}
          </div>
          <div style={{ fontSize: '0.9rem', marginBottom: '0.25rem', fontWeight: 600 }}>
            {user?.full_name}
          </div>
          {user?.primary_role && user.primary_role !== 'patient' && (
            <div style={{
              fontSize: '0.75rem', marginBottom: '0.5rem',
              display: 'inline-block', padding: '2px 10px', borderRadius: 12,
              background: 'var(--color-primary-light)', color: 'var(--color-primary-dark)',
              fontWeight: 600, textTransform: 'capitalize',
            }}>
              {user.primary_role.replace(/_/g, ' ')}
            </div>
          )}
          <LanguageSwitcher />
          <div>
            <button className="btn btn-secondary btn-sm" onClick={logout}>
              <LogOut size={16} /> {t('Layout.logout')}
            </button>
          </div>
        </div>
      </aside>
      <main className="main-content">
        <MembershipNudge />
        <Outlet />
      </main>
    </div>
  );
}
