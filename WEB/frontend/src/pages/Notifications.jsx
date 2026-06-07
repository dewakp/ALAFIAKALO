import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bell, BellOff, Check, CheckCheck, Trash2, AlertTriangle,
  Activity, Calendar, FlaskConical, Pill, Apple, Settings, X,
} from 'lucide-react';
import api from '../services/api';
import BackButton from '../components/BackButton';

const CATEGORY_META = {
  therapy_session: { icon: Activity, color: '#1976d2', label: 'Therapy Session' },
  calendar:        { icon: Calendar, color: '#7b1fa2', label: 'Calendar Event' },
  lab_anomaly:     { icon: FlaskConical, color: '#d32f2f', label: 'Lab Anomaly' },
  treatment_anomaly: { icon: AlertTriangle, color: '#e65100', label: 'Treatment Alert' },
  medication_conflict: { icon: Pill, color: '#c62828', label: 'Medication Conflict' },
  nutrition_alert: { icon: Apple, color: '#2e7d32', label: 'Nutrition Alert' },
  system:          { icon: Bell, color: '#546e7a', label: 'System' },
};

const PRIORITY_COLORS = {
  low: '#90a4ae', medium: '#42a5f5', high: '#ef6c00', urgent: '#d50000',
};

export default function Notifications() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // 'all' | 'unread' | category
  const [showPrefs, setShowPrefs] = useState(false);
  const [preferences, setPreferences] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filter === 'unread') params.unread_only = true;
      else if (filter !== 'all') params.category = filter;
      const { data } = await api.get('/notifications', { params });
      setNotifications(data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const markRead = async (id) => {
    await api.patch(`/notifications/${id}/read`);
    setNotifications(n => n.map(x => x.id === id ? { ...x, is_read: true } : x));
  };

  const markAllRead = async () => {
    await api.post('/notifications/read-all');
    setNotifications(n => n.map(x => ({ ...x, is_read: true })));
  };

  const remove = async (id) => {
    await api.delete(`/notifications/${id}`);
    setNotifications(n => n.filter(x => x.id !== id));
  };

  const handleClick = (n) => {
    if (!n.is_read) markRead(n.id);
    if (n.action_url) navigate(n.action_url);
  };

  // Preferences
  const loadPrefs = async () => {
    const { data } = await api.get('/notifications/preferences');
    setPreferences(data);
    setShowPrefs(true);
  };

  const togglePref = async (category, field, value) => {
    await api.patch(`/notifications/preferences/${category}`, { [field]: value });
    setPreferences(p => p.map(x => x.category === category ? { ...x, [field]: value } : x));
  };

  const unreadCount = notifications.filter(n => !n.is_read).length;

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <Bell size={28} />
        <div className="page-header">
          <div className="page-header-left">
            <BackButton />
            <h1 style={{ flex: 1, margin: 0 }}>Notifications</h1>
          </div>
        </div>
        {unreadCount > 0 && (
          <button className="btn btn-secondary btn-sm" onClick={markAllRead}>
            <CheckCheck size={16} /> Mark all read
          </button>
        )}
        <button className="btn btn-secondary btn-sm" onClick={loadPrefs}>
          <Settings size={16} /> Preferences
        </button>
      </div>

      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        {['all', 'unread', ...Object.keys(CATEGORY_META)].map(f => (
          <button
            key={f}
            className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setFilter(f)}
            style={{ textTransform: 'capitalize' }}
          >
            {f === 'all' ? 'All' : f === 'unread' ? `Unread (${unreadCount})` : CATEGORY_META[f]?.label || f}
          </button>
        ))}
      </div>

      {loading ? (
        <p>Loading…</p>
      ) : notifications.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>
          <BellOff size={48} style={{ marginBottom: 12 }} />
          <p>No notifications</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {notifications.map(n => {
            const meta = CATEGORY_META[n.category] || CATEGORY_META.system;
            const Icon = meta.icon;
            return (
              <div
                key={n.id}
                onClick={() => handleClick(n)}
                style={{
                  display: 'flex', gap: 12, padding: '12px 16px',
                  borderRadius: 10,
                  background: n.is_read ? 'var(--color-bg-secondary, #f5f5f5)' : '#e3f2fd',
                  border: `1px solid ${n.is_read ? '#e0e0e0' : meta.color + '40'}`,
                  cursor: n.action_url ? 'pointer' : 'default',
                  alignItems: 'flex-start',
                }}
              >
                <div style={{
                  width: 36, height: 36, borderRadius: '50%',
                  background: meta.color + '18', display: 'flex',
                  alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                  <Icon size={18} color={meta.color} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <strong style={{ fontSize: 14 }}>{n.title}</strong>
                    <span style={{
                      fontSize: 10, padding: '1px 6px', borderRadius: 6,
                      background: PRIORITY_COLORS[n.priority] + '22',
                      color: PRIORITY_COLORS[n.priority], fontWeight: 700,
                      textTransform: 'uppercase',
                    }}>
                      {n.priority}
                    </span>
                    {!n.is_read && (
                      <span style={{
                        width: 8, height: 8, borderRadius: '50%',
                        background: '#1976d2', flexShrink: 0,
                      }} />
                    )}
                  </div>
                  <p style={{ margin: '4px 0 0', fontSize: 13, color: '#555' }}>{n.message}</p>
                  <span style={{ fontSize: 11, color: '#999' }}>
                    {new Date(n.created_at).toLocaleString()}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                  {!n.is_read && (
                    <button
                      className="btn btn-sm btn-secondary"
                      onClick={e => { e.stopPropagation(); markRead(n.id); }}
                      title="Mark read"
                      style={{ padding: 4 }}
                    >
                      <Check size={14} />
                    </button>
                  )}
                  <button
                    className="btn btn-sm btn-secondary"
                    onClick={e => { e.stopPropagation(); remove(n.id); }}
                    title="Delete"
                    style={{ padding: 4 }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Preferences modal */}
      {showPrefs && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.4)', display: 'flex',
          alignItems: 'center', justifyContent: 'center', zIndex: 1000,
        }} onClick={() => setShowPrefs(false)}>
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: '#fff', borderRadius: 12, padding: 24,
              width: '100%', maxWidth: 520, maxHeight: '80vh', overflowY: 'auto',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h2 style={{ margin: 0 }}>Notification Preferences</h2>
              <button className="btn btn-sm btn-secondary" onClick={() => setShowPrefs(false)}>
                <X size={16} />
              </button>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: 6 }}>Category</th>
                  <th style={{ padding: 6 }}>Enabled</th>
                  <th style={{ padding: 6 }}>In-App</th>
                  <th style={{ padding: 6 }}>Push</th>
                  <th style={{ padding: 6 }}>Email</th>
                  <th style={{ padding: 6 }}>SMS</th>
                </tr>
              </thead>
              <tbody>
                {preferences.map(p => {
                  const meta = CATEGORY_META[p.category] || CATEGORY_META.system;
                  return (
                    <tr key={p.category} style={{ borderTop: '1px solid #eee' }}>
                      <td style={{ padding: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <meta.icon size={14} color={meta.color} /> {meta.label}
                      </td>
                      {['enabled', 'in_app', 'push', 'email', 'sms'].map(field => (
                        <td key={field} style={{ padding: 6, textAlign: 'center' }}>
                          <input
                            type="checkbox"
                            checked={p[field]}
                            onChange={() => togglePref(p.category, field, !p[field])}
                          />
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
