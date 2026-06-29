import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
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
  ClipboardList,
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
} from 'lucide-react';

// Roles that can see the Clinician Dashboard
const CLINICIAN_ROLES = [
  'physician', 'surgeon', 'nurse_practitioner',
  'physician_assistant', 'resident', 'fellow', 'attending_physician',
  'cardiologist', 'dermatologist', 'endocrinologist', 'gastroenterologist',
  'neurologist', 'oncologist', 'pediatrician', 'radiologist',
  'general_surgeon', 'orthopedic_surgeon', 'neurosurgeon',
  'cardiothoracic_surgeon', 'plastic_surgeon', 'vascular_surgeon',
  'oral_surgeon', 'clinical_nurse_specialist', 'nurse_anesthetist',
  'nurse_midwife', 'charge_nurse', 'nurse_administrator',
  'medical_director', 'chief_medical_officer',
];

function isClinician(user) {
  if (!user) return false;
  const roles = user.active_roles || [];
  if (user.primary_role) roles.push(user.primary_role);
  return roles.some(r => CLINICIAN_ROLES.includes(r));
}

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
      { to: '/data-sharing', icon: Share2, label: 'Connect Records' },
    ],
  },
  {
    label: 'Therapies', icon: Cross, children: [
      { to: '/hemodialysis', icon: Activity, label: 'HD Flowsheet' },
      { to: '/peritoneal-dialysis', icon: Droplets, label: 'PD Report' },
      { to: '/therapy-history', icon: History, label: 'Therapy History' },
    ],
  },
  { to: '/physicians', icon: Stethoscope, label: 'Physician Directory' },
  { to: '/fda-recalls', icon: AlertTriangle, label: 'Food & Drug Recalls' },
  { to: '/surveillance', icon: Radar, label: 'Disease Surveillance' },
  // ── Additional web features ──
  {
    label: 'More', icon: Wrench, children: [
      { to: '/fitness', icon: Dumbbell, label: 'Fitness' },
      { to: '/mental-health', icon: HeartPulse, label: 'Mental Health' },
      { to: '/exercise-planner', icon: PersonStanding, label: 'Exercise Planner' },
      { to: '/community', icon: Globe, label: 'Community Health' },
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
      { to: '/roles', icon: UserCog, label: 'Role' },
      { to: '/advanced-directives', icon: FileHeart, label: 'Advanced Directives' },
      { to: '/insurance', icon: Shield, label: 'Insurance' },
      { to: '/clinician-dashboard', icon: ClipboardList, label: 'Clinician Dashboard', clinicianOnly: true },
    ],
  },
];

function SidebarGroup({ group, user }) {
  const [open, setOpen] = useState(false);
  const GroupIcon = group.icon;
  const showClinician = isClinician(user);
  const visibleChildren = group.children.filter(c => !c.clinicianOnly || showClinician);

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
  const navigate = useNavigate();
  const [unreadCount, setUnreadCount] = useState(0);

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
        <nav className="sidebar-nav">
          {navGroups.map((item, idx) =>
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
              <SidebarGroup key={item.label} group={item} user={user} />
            )
          )}
        </nav>
        <div className="sidebar-footer">
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
        <Outlet />
      </main>
    </div>
  );
}
