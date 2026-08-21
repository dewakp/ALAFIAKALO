import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useClinicianMode } from '../context/ClinicianModeContext';
import api from '../services/api';
import MembershipNudge from './MembershipNudge';
import {
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

const navGroups = [
  // Prompt Hub — the modality-aware entry point (Basis.md)
  { to: '/', icon: Bot, label: 'Ask ALAFIA' },
  // ── Firebase-matching primary nav ──
  {
    label: 'Overview & Analysis', icon: LayoutDashboard, children: [
      { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
      { to: '/insights', icon: Network, label: 'Health Insights' },
      { to: '/chart-dashboard', icon: TrendingUp, label: 'Health Trends' },
      { to: '/wellness', icon: Gauge, label: 'Wellness Score' },
      { to: '/calendar', icon: CalendarDays, label: 'Calendar' },
    ],
  },
  {
    label: 'Meals', icon: UtensilsCrossed, children: [
      { to: '/meal-planner', icon: UtensilsCrossed, label: 'Meal Planner' },
      { to: '/nutrition', icon: Apple, label: 'Log Food Intake' },
      { to: '/meals-diary', icon: BookOpen, label: 'Meals Diary' },
      { to: '/nutrient-tracking', icon: BarChart3, label: 'Nutrient Tracking' },
      { to: '/pantry', icon: Package, label: 'Pantry' },
    ],
  },
  // Conditions are a cornerstone of the record (they drive nutrient limits,
  // the clinician board and the AI coach), so they sit at the top level rather
  // than inside a collapsed group.
  { to: '/chronic-conditions', icon: Stethoscope, label: 'Conditions' },
  { to: '/medications', icon: Pill, label: 'Medications' },
  {
    label: 'Activities & Logs', icon: Activity, children: [
      { to: '/journal', icon: BookOpen, label: 'Journal' },
      { to: '/vitals', icon: HeartPulse, label: 'Vitals' },
      { to: '/elimination', icon: FlaskRound, label: 'Elimination Log' },
      { to: '/symptoms', icon: Activity, label: 'Symptoms' },
      { to: '/sleep', icon: Moon, label: 'Sleep' },
    ],
  },
  {
    label: 'Labs & Records', icon: FlaskConical, children: [
      { to: '/labs', icon: FlaskConical, label: 'Lab Tests' },
      { to: '/lab-charts', icon: BarChart3, label: 'Charts' },
    ],
  },
  // Sharing is core, so it sits at the top level rather than inside a collapsed
  // group. It used to be "Connect Records" three clicks deep under
  // Labs & Records, where nobody could find it.
  { to: '/data-sharing', icon: Share2, label: 'Share Records' },
  {
    label: 'Therapies', icon: Cross, children: [
      { to: '/hemodialysis', icon: Activity, label: 'HD Flowsheet' },
      { to: '/peritoneal-dialysis', icon: Droplets, label: 'PD Report' },
      { to: '/therapy-history', icon: History, label: 'Therapy History' },
    ],
  },
  {
    label: 'Community Health', icon: Globe, children: [
      { to: '/community', icon: Globe, label: 'Overview' },
      { to: '/physicians', icon: Stethoscope, label: 'Physician Directory' },
      { to: '/facilities', icon: Building, label: 'Facility Directory' },
      { to: '/fda-recalls', icon: AlertTriangle, label: 'Food & Drug Recalls' },
      { to: '/surveillance', icon: Radar, label: 'Disease Surveillance' },
    ],
  },
  // ── Additional web features ──
  {
    label: 'More', icon: Wrench, children: [
      { to: '/fitness', icon: Dumbbell, label: 'Fitness' },
      { to: '/mental-health', icon: HeartPulse, label: 'Mental Health' },
      { to: '/exercise-planner', icon: PersonStanding, label: 'Exercise Planner' },
      { to: '/ai', icon: Bot, label: 'AI Assistant' },
      { to: '/telehealth', icon: Video, label: 'Telehealth' },
      { to: '/messaging', icon: MessageSquare, label: 'Messaging' },
      { to: '/pharmacy', icon: Pill, label: 'Pharmacy' },
      { to: '/image-ai', icon: ScanLine, label: 'Image AI' },
      { to: '/pdf-tools', icon: FileText, label: 'PDF Tools' },
      { to: '/capture', icon: Camera, label: 'Capture' },
    ],
  },
  {
    label: 'Profile', icon: User, children: [
      { to: '/profile', icon: User, label: 'My Profile' },
      { to: '/subscription', icon: Sparkles, label: 'ALAFIA Membership' },
      { to: '/roles', icon: UserCog, label: 'Role' },
      { to: '/advanced-directives', icon: FileHeart, label: 'Advanced Directives' },
      { to: '/insurance', icon: Shield, label: 'Insurance' },
    ],
  },
];

// Clinician mode replaces the nav entirely rather than adding to it. A
// physician reviewing patients does not want their own meal diary in the way,
// and mixing the two is what made the clinical features hard to find.
const clinicianNavGroups = [
  { to: '/clinician-dashboard', icon: Users, label: 'My Patients' },
  { to: '/data-sharing', icon: Share2, label: 'Share Records' },
  { to: '/messaging', icon: MessageSquare, label: 'Messaging' },
  { to: '/telehealth', icon: Video, label: 'Telehealth' },
  { to: '/calendar', icon: CalendarDays, label: 'Calendar' },
  { to: '/physicians', icon: Stethoscope, label: 'Physician Directory' },
  { to: '/facilities', icon: Building, label: 'Facilities' },
  {
    label: 'Account', icon: User, children: [
      { to: '/profile', icon: User, label: 'My Profile' },
      { to: '/roles', icon: UserCog, label: 'Role' },
      { to: '/subscription', icon: Sparkles, label: 'ALAFIA Membership' },
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
        { label: 'Patient', icon: User, active: !clinicianMode, to: false },
        { label: 'Clinician', icon: Stethoscope, active: clinicianMode, to: true },
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
  { to: '/help', icon: HelpCircle, label: 'Help' },
  { to: '/contact', icon: Mail, label: 'Contact Us' },
  { to: '/investors', icon: Briefcase, label: 'Investors' },
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

  return (
    <div className="app-layout">
      <aside className="sidebar">
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
          <span style={{ flex: 1, textAlign: 'left' }}>Notifications</span>
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
          <div>
            <button className="btn btn-secondary btn-sm" onClick={logout}>
              <LogOut size={16} /> Logout
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
