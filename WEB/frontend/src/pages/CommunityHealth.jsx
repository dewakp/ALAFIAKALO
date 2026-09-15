import { useState, useEffect } from 'react';
import api from '../services/api';
import BackButton from '../components/BackButton';
import { t as translate } from '../i18n';

const SEV_COLORS = { critical: '#b71c1c', high: '#f44336', moderate: '#ff9800', low: '#4caf50', info: '#2196f3' };
const SEV_LABELS = { critical: 'CRITICAL', high: 'High', moderate: 'Moderate', low: 'Low', info: 'Info' };

const TAB_BTN = (active) => ({
  padding: '8px 20px', borderRadius: 8,
  border: active ? '2px solid var(--primary)' : '1px solid #ddd',
  background: active ? 'var(--primary)' : '#fff',
  color: active ? '#fff' : '#333',
  fontWeight: active ? 700 : 400, cursor: 'pointer',
});

function SeverityBadge({ severity }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 12,
      fontSize: 11, fontWeight: 700, color: '#fff',
      background: SEV_COLORS[severity] || '#999',
    }}>
      {SEV_LABELS[severity] || severity}
    </span>
  );
}

function SourceBadge({ source }) {
  const colors = { who: '#0072bc', cdc: '#004b87', fda: '#00529b', ema: '#003399',
    health_canada: '#d4272e', ecdc: '#006633', mhra: '#6b2d5b', poison_control: '#8b0000' };
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 8,
      fontSize: 10, fontWeight: 700, color: '#fff',
      background: colors[source] || '#666', textTransform: 'uppercase',
    }}>
      {(source || '').replace(/_/g, ' ')}
    </span>
  );
}

function CategoryIcon({ category }) {
  const icons = {
    pandemic: '🦠', epidemic: '🏥', outbreak: '⚠️', recall_drug: '💊',
    recall_food: '🍽️', recall_device: '🩺', advisory: '📢', poison: '☠️',
    environmental: '🌍', natural_disaster: '🌪️', vaccination: '💉',
    guideline_update: '📋', travel_health: '✈️', water_safety: '💧', air_quality: '🌫️',
  };
  return <span style={{ fontSize: 20 }}>{icons[category] || '📌'}</span>;
}

export default function CommunityHealth() {
  const [tab, setTab] = useState('dashboard');
  const [stats, setStats] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [guidelines, setGuidelines] = useState([]);
  const [reports, setReports] = useState([]);
  const [categories, setCategories] = useState([]);
  const [sources, setSources] = useState([]);
  const [subscription, setSubscription] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [selectedGuideline, setSelectedGuideline] = useState(null);

  // Filters
  const [filterCategory, setFilterCategory] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterSource, setFilterSource] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [s, a, g, r, c, src, sub] = await Promise.all([
        api.get('/community/dashboard'),
        api.get('/community/alerts'),
        api.get('/community/guidelines'),
        api.get('/community/reports'),
        api.get('/community/categories'),
        api.get('/community/sources'),
        api.get('/community/subscriptions'),
      ]);
      setStats(s.data);
      setAlerts(a.data);
      setGuidelines(g.data);
      setReports(r.data);
      setCategories(c.data);
      setSources(src.data);
      setSubscription(sub.data);
    } catch (err) { console.error(err); }
    setLoading(false);
  }

  async function loadAlerts() {
    const params = {};
    if (filterCategory) params.category = filterCategory;
    if (filterSeverity) params.severity = filterSeverity;
    if (filterSource) params.source = filterSource;
    if (searchQuery) params.search = searchQuery;
    try {
      const res = await api.get('/community/alerts', { params });
      setAlerts(res.data);
    } catch (err) { console.error(err); }
  }

  useEffect(() => { if (!loading) loadAlerts(); }, [filterCategory, filterSeverity, filterSource, searchQuery]);

  async function toggleBookmark(alertId) {
    try {
      await api.post(`/community/alerts/${alertId}/bookmark`);
      loadAll();
    } catch (err) { console.error(err); }
  }

  async function viewAlert(alertId) {
    try {
      const res = await api.get(`/community/alerts/${alertId}`);
      setSelectedAlert(res.data);
    } catch (err) { console.error(err); }
  }

  if (loading) return <div className="page"><p>{translate('CommunityHealth.loading_community_health_data')}</p></div>;

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1>{translate('CommunityHealth.community_health')}</h1>
        </div>
      </div>
      <p style={{ color: '#666', marginBottom: 20 }}>
        {translate('CommunityHealth.alerts_recalls_guidelines_community')}
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {['dashboard', 'alerts', 'fda_recalls', 'guidelines', 'reports', 'settings'].map(t => (
          <button key={t} onClick={() => { setTab(t); setSelectedAlert(null); setSelectedGuideline(null); }}
            style={TAB_BTN(tab === t)}>
            {t === 'dashboard' ? '📊 Dashboard' : t === 'alerts' ? '🚨 Alerts & Recalls' :
              t === 'fda_recalls' ? '🏛️ FDA Recalls' :
              t === 'guidelines' ? '📋 Guidelines' : t === 'reports' ? '📝 Reports' : '⚙️ Settings'}
          </button>
        ))}
      </div>

      {tab === 'dashboard' && <DashboardTab stats={stats} onViewAlert={viewAlert} />}
      {tab === 'alerts' && !selectedAlert && (
        <AlertsTab
          alerts={alerts} categories={categories} sources={sources}
          filterCategory={filterCategory} setFilterCategory={setFilterCategory}
          filterSeverity={filterSeverity} setFilterSeverity={setFilterSeverity}
          filterSource={filterSource} setFilterSource={setFilterSource}
          searchQuery={searchQuery} setSearchQuery={setSearchQuery}
          onView={viewAlert} onBookmark={toggleBookmark}
        />
      )}
      {tab === 'alerts' && selectedAlert && (
        <AlertDetail alert={selectedAlert} onBack={() => setSelectedAlert(null)} onBookmark={toggleBookmark} />
      )}
      {tab === 'fda_recalls' && <FDARecallsTab />}
      {tab === 'guidelines' && !selectedGuideline && (
        <GuidelinesTab guidelines={guidelines} onView={setSelectedGuideline} />
      )}
      {tab === 'guidelines' && selectedGuideline && (
        <GuidelineDetail guideline={selectedGuideline} onBack={() => setSelectedGuideline(null)} />
      )}
      {tab === 'reports' && <ReportsTab reports={reports} onSubmit={loadAll} />}
      {tab === 'settings' && <SettingsTab subscription={subscription} categories={categories} sources={sources} onSave={loadAll} />}
    </div>
  );
}

// ── DASHBOARD ──────────────────────────────────────────────────────────

function DashboardTab({ stats, onViewAlert }) {
  if (!stats) return <p>{translate('CommunityHealth.no_community_health_data_available')}</p>;
  const {
    total_active_alerts, critical_alerts, active_recalls, active_outbreaks,
    active_advisories, active_poison_alerts, total_guidelines, user_reports_30d,
    unread_alerts, bookmarked_alerts, latest_outbreaks, latest_recalls, latest_advisories,
  } = stats;

  const statCards = [
    { label: translate('CommunityHealth.active_alerts'), value: total_active_alerts, color: '#2196f3', icon: '🚨' },
    { label: translate('CommunityHealth.critical'), value: critical_alerts, color: '#b71c1c', icon: '🔴' },
    { label: translate('CommunityHealth.active_recalls'), value: active_recalls, color: '#f44336', icon: '💊' },
    { label: translate('CommunityHealth.outbreaks'), value: active_outbreaks, color: '#ff9800', icon: '🦠' },
    { label: translate('CommunityHealth.advisories'), value: active_advisories, color: '#9c27b0', icon: '📢' },
    { label: translate('CommunityHealth.poison_alerts'), value: active_poison_alerts, color: '#8b0000', icon: '☠️' },
    { label: translate('CommunityHealth.guidelines'), value: total_guidelines, color: '#4caf50', icon: '📋' },
    { label: translate('CommunityHealth.your_reports'), value: user_reports_30d, color: '#607d8b', icon: '📝' },
    { label: translate('CommunityHealth.unread'), value: unread_alerts, color: '#e91e63', icon: '📬' },
    { label: translate('CommunityHealth.bookmarked'), value: bookmarked_alerts, color: '#ff9800', icon: '🔖' },
  ];

  return (
    <div>
      {/* Stats Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 32 }}>
        {statCards.map(({ label, value, color, icon }) => (
          <div key={label} style={{
            background: '#fff', borderRadius: 12, padding: 16,
            boxShadow: '0 2px 8px rgba(0,0,0,.08)', textAlign: 'center',
            borderTop: `3px solid ${color}`,
          }}>
            <div style={{ fontSize: 24 }}>{icon}</div>
            <div style={{ fontSize: 28, fontWeight: 800, color }}>{value}</div>
            <div style={{ fontSize: 12, color: '#666' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Latest Sections */}
      <AlertSection title={translate('CommunityHealth.latest_outbreaks_epidemics')} alerts={latest_outbreaks} onView={onViewAlert} />
      <AlertSection title={translate('CommunityHealth.recent_recalls')} alerts={latest_recalls} onView={onViewAlert} />
      <AlertSection title={translate('CommunityHealth.active_advisories')} alerts={latest_advisories} onView={onViewAlert} />
    </div>
  );
}

function AlertSection({ title, alerts, onView }) {
  if (!alerts?.length) return null;
  return (
    <div style={{ marginBottom: 28 }}>
      <h3 style={{ marginBottom: 12 }}>{title}</h3>
      {alerts.map(a => <AlertCard key={a.id} alert={a} onClick={() => onView(a.id)} />)}
    </div>
  );
}

function AlertCard({ alert, onClick, onBookmark }) {
  const a = alert;
  return (
    <div onClick={onClick} style={{
      background: '#fff', borderRadius: 12, padding: 16, marginBottom: 10, cursor: 'pointer',
      boxShadow: '0 2px 6px rgba(0,0,0,.06)',
      borderLeft: `4px solid ${SEV_COLORS[a.severity] || '#999'}`,
      transition: 'transform .15s', display: 'flex', gap: 12, alignItems: 'flex-start',
    }}
      onMouseEnter={e => e.currentTarget.style.transform = 'translateX(4px)'}
      onMouseLeave={e => e.currentTarget.style.transform = 'none'}
    >
      <CategoryIcon category={a.category} />
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700, marginBottom: 4, fontSize: 14 }}>{a.title}</div>
        <div style={{ fontSize: 12, color: '#666', marginBottom: 6 }}>{a.summary}</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <SeverityBadge severity={a.severity} />
          <SourceBadge source={a.source} />
          {a.issued_date && <span style={{ fontSize: 10, color: '#999' }}>{a.issued_date}</span>}
          {a.confirmed_cases && <span style={{ fontSize: 10, color: '#f44336' }}>{translate('CommunityHealth.cases', { confirmed_cases: a.confirmed_cases.toLocaleString() })}</span>}
          {a.product_name && <span style={{ fontSize: 10, color: '#666' }}>📦 {a.product_name}</span>}
          {a.is_global && <span style={{ fontSize: 10, background: '#e3f2fd', padding: '1px 6px', borderRadius: 4 }}>{translate('CommunityHealth.global')}</span>}
          {a.affected_countries?.length > 0 && (
            <span style={{ fontSize: 10, color: '#666' }}>📍 {a.affected_countries.join(', ')}</span>
          )}
        </div>
      </div>
      {onBookmark && (
        <button onClick={e => { e.stopPropagation(); onBookmark(a.id); }}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18 }}>🔖</button>
      )}
    </div>
  );
}

// ── ALERTS ─────────────────────────────────────────────────────────────

function AlertsTab({ alerts, categories, sources, filterCategory, setFilterCategory,
  filterSeverity, setFilterSeverity, filterSource, setFilterSource,
  searchQuery, setSearchQuery, onView, onBookmark }) {

  const filterStyle = {
    padding: '6px 12px', borderRadius: 8, border: '1px solid #ddd', fontSize: 13,
    background: '#fff', cursor: 'pointer', minWidth: 120,
  };

  return (
    <div>
      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <input type="text" placeholder={translate('CommunityHealth.search_alerts')} value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          style={{ ...filterStyle, minWidth: 200 }} />
        <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)} style={filterStyle}>
          <option value="">{translate('CommunityHealth.all_categories')}</option>
          {categories.map(c => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
        </select>
        <select value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)} style={filterStyle}>
          <option value="">{translate('CommunityHealth.all_severities')}</option>
          {['critical', 'high', 'moderate', 'low', 'info'].map(s => (
            <option key={s} value={s}>{SEV_LABELS[s]}</option>
          ))}
        </select>
        <select value={filterSource} onChange={e => setFilterSource(e.target.value)} style={filterStyle}>
          <option value="">{translate('CommunityHealth.all_sources')}</option>
          {sources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        {(filterCategory || filterSeverity || filterSource || searchQuery) && (
          <button onClick={() => { setFilterCategory(''); setFilterSeverity(''); setFilterSource(''); setSearchQuery(''); }}
            style={{ ...filterStyle, background: '#f5f5f5', fontWeight: 600 }}>{translate('CommunityHealth.clear')}</button>
        )}
      </div>

      <div style={{ fontSize: 13, color: '#666', marginBottom: 12 }}>{translate('CommunityHealth.alert_s', { alerts: alerts.length })}</div>

      {alerts.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
          <div style={{ fontSize: 48 }}>✅</div>
          <p>{translate('CommunityHealth.no_alerts_matching_your_criteria')}</p>
        </div>
      ) : alerts.map(a => <AlertCard key={a.id} alert={a} onClick={() => onView(a.id)} onBookmark={onBookmark} />)}
    </div>
  );
}

// ── ALERT DETAIL ──────────────────────────────────────────────────────

function AlertDetail({ alert, onBack, onBookmark }) {
  const a = alert;
  const section = { marginBottom: 20 };
  const sectionTitle = { fontWeight: 700, marginBottom: 8, fontSize: 14, color: '#333' };

  return (
    <div>
      <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', marginBottom: 12, color: 'var(--primary)', fontWeight: 600 }}>
        {translate('CommunityHealth.back_to_alerts')}
      </button>

      <div style={{
        background: '#fff', borderRadius: 16, padding: 28, boxShadow: '0 4px 12px rgba(0,0,0,.08)',
        borderTop: `4px solid ${SEV_COLORS[a.severity]}`,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
              <CategoryIcon category={a.category} />
              <SeverityBadge severity={a.severity} />
              <SourceBadge source={a.source} />
              {a.is_global && <span style={{ fontSize: 11, background: '#e3f2fd', padding: '2px 8px', borderRadius: 4 }}>{translate('CommunityHealth.global')}</span>}
            </div>
            <h2 style={{ margin: 0, fontSize: 20 }}>{a.title}</h2>
          </div>
          <button onClick={() => onBookmark(a.id)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 24 }}>🔖</button>
        </div>

        <p style={{ color: '#555', fontSize: 15, lineHeight: 1.6 }}>{a.summary}</p>
        {a.description && <p style={{ color: '#666', lineHeight: 1.5 }}>{a.description}</p>}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginTop: 20 }}>
          {/* Dates */}
          <div style={section}>
            <div style={sectionTitle}>{translate('CommunityHealth.dates')}</div>
            <div style={{ fontSize: 13, color: '#666' }}>
              {a.issued_date && <div>{translate('CommunityHealth.issued')} <strong>{a.issued_date}</strong></div>}
              {a.effective_date && <div>{translate('CommunityHealth.effective')} <strong>{a.effective_date}</strong></div>}
              {a.expiry_date && <div>{translate('CommunityHealth.expires')} <strong>{a.expiry_date}</strong></div>}
            </div>
          </div>

          {/* Geographic */}
          {(a.affected_countries?.length > 0 || a.affected_regions?.length > 0) && (
            <div style={section}>
              <div style={sectionTitle}>{translate('CommunityHealth.affected_areas')}</div>
              <div style={{ fontSize: 13, color: '#666' }}>
                {a.affected_countries?.length > 0 && <div>{translate('CommunityHealth.countries', { affected_countries: a.affected_countries.join(', ') })}</div>}
                {a.affected_regions?.length > 0 && <div>{translate('CommunityHealth.regions', { affected_regions: a.affected_regions.join(', ') })}</div>}
              </div>
            </div>
          )}

          {/* Outbreak info */}
          {a.disease_name && (
            <div style={section}>
              <div style={sectionTitle}>{translate('CommunityHealth.outbreak_details')}</div>
              <div style={{ fontSize: 13, color: '#666' }}>
                <div>{translate('CommunityHealth.disease')} <strong>{a.disease_name}</strong></div>
                {a.pathogen && <div>{translate('CommunityHealth.pathogen', { pathogen: a.pathogen })}</div>}
                {a.confirmed_cases != null && <div>{translate('CommunityHealth.confirmed_cases')} <strong style={{ color: '#f44336' }}>{a.confirmed_cases.toLocaleString()}</strong></div>}
                {a.deaths != null && <div>{translate('CommunityHealth.deaths')} <strong style={{ color: '#b71c1c' }}>{a.deaths.toLocaleString()}</strong></div>}
              </div>
            </div>
          )}

          {/* Recall info  */}
          {a.product_name && (
            <div style={section}>
              <div style={sectionTitle}>{translate('CommunityHealth.recall_details')}</div>
              <div style={{ fontSize: 13, color: '#666' }}>
                <div>{translate('CommunityHealth.product')} <strong>{a.product_name}</strong></div>
                {a.product_type && <div>{translate('CommunityHealth.type', { product_type: a.product_type })}</div>}
                {a.manufacturer && <div>{translate('CommunityHealth.manufacturer', { manufacturer: a.manufacturer })}</div>}
                {a.recall_class && <div>{translate('CommunityHealth.class')} <strong>{translate('CommunityHealth.class_2', { recall_class: a.recall_class })}</strong></div>}
                {a.reason_for_recall && <div>{translate('CommunityHealth.reason', { reason_for_recall: a.reason_for_recall })}</div>}
                {a.lot_numbers?.length > 0 && <div>{translate('CommunityHealth.lot', { lot_numbers: a.lot_numbers.join(', ') })}</div>}
              </div>
            </div>
          )}
        </div>

        {/* Recommended actions */}
        {a.recommended_actions?.length > 0 && (
          <div style={{ ...section, marginTop: 12 }}>
            <div style={sectionTitle}>{translate('CommunityHealth.recommended_actions')}</div>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {a.recommended_actions.map((act, i) => (
                <li key={i} style={{ fontSize: 13, color: '#444', marginBottom: 4 }}>{act}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Target population */}
        {a.target_population?.length > 0 && (
          <div style={section}>
            <div style={sectionTitle}>{translate('CommunityHealth.target_population')}</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {a.target_population.map((p, i) => (
                <span key={i} style={{ fontSize: 11, background: '#f0f0f0', padding: '2px 8px', borderRadius: 8 }}>{p}</span>
              ))}
            </div>
          </div>
        )}

        {/* Source link */}
        {a.source_url && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #eee' }}>
            <a href={a.source_url} target="_blank" rel="noopener noreferrer"
              style={{ color: 'var(--primary)', fontWeight: 600, fontSize: 13 }}>
              {translate('CommunityHealth.view_original_source')}
            </a>
          </div>
        )}

        {/* Tags */}
        {a.tags?.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {a.tags.map((t, i) => (
              <span key={i} style={{ fontSize: 10, color: '#999', background: '#f8f8f8', padding: '2px 6px', borderRadius: 4 }}>#{t}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── GUIDELINES ────────────────────────────────────────────────────────

function GuidelinesTab({ guidelines, onView }) {
  const [search, setSearch] = useState('');
  const [catFilter, setCatFilter] = useState('');

  const filtered = guidelines.filter(g => {
    if (catFilter && g.category !== catFilter) return false;
    if (search && !g.title.toLowerCase().includes(search.toLowerCase())
      && !(g.summary || '').toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const cats = [...new Set(guidelines.map(g => g.category))];

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <input type="text" placeholder={translate('CommunityHealth.search_guidelines')} value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #ddd', minWidth: 200 }} />
        <select value={catFilter} onChange={e => setCatFilter(e.target.value)}
          style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #ddd' }}>
          <option value="">{translate('CommunityHealth.all_categories')}</option>
          {cats.map(c => <option key={c} value={c}>{c.replace(/_/g, ' ')}</option>)}
        </select>
      </div>

      {filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
          <div style={{ fontSize: 48 }}>📋</div>
          <p>{translate('CommunityHealth.no_guidelines_found')}</p>
        </div>
      ) : filtered.map(g => (
        <div key={g.id} onClick={() => onView(g)} style={{
          background: '#fff', borderRadius: 12, padding: 16, marginBottom: 10,
          boxShadow: '0 2px 6px rgba(0,0,0,.06)', cursor: 'pointer',
          borderLeft: '4px solid #4caf50', transition: 'transform .15s',
        }}
          onMouseEnter={e => e.currentTarget.style.transform = 'translateX(4px)'}
          onMouseLeave={e => e.currentTarget.style.transform = 'none'}
        >
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
            <span style={{ fontSize: 18 }}>📋</span>
            <SourceBadge source={g.source} />
            <span style={{ fontSize: 10, background: '#e8f5e9', padding: '2px 6px', borderRadius: 4, textTransform: 'capitalize' }}>
              {(g.category || '').replace(/_/g, ' ')}
            </span>
            {g.version && <span style={{ fontSize: 10, color: '#999' }}>v{g.version}</span>}
          </div>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{g.title}</div>
          <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{g.summary}</div>
          {g.effective_date && <div style={{ fontSize: 10, color: '#999', marginTop: 4 }}>{translate('CommunityHealth.effective_2', { effective_date: g.effective_date })}</div>}
        </div>
      ))}
    </div>
  );
}

function GuidelineDetail({ guideline, onBack }) {
  const g = guideline;
  return (
    <div>
      <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', marginBottom: 12, color: 'var(--primary)', fontWeight: 600 }}>
        {translate('CommunityHealth.back_to_guidelines')}
      </button>
      <div style={{
        background: '#fff', borderRadius: 16, padding: 28,
        boxShadow: '0 4px 12px rgba(0,0,0,.08)', borderTop: '4px solid #4caf50',
      }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
          <SourceBadge source={g.source} />
          <span style={{ fontSize: 11, background: '#e8f5e9', padding: '2px 8px', borderRadius: 4, textTransform: 'capitalize' }}>
            {(g.category || '').replace(/_/g, ' ')}
          </span>
          {g.version && <span style={{ fontSize: 11, color: '#999' }}>{translate('CommunityHealth.version', { version: g.version })}</span>}
          {g.is_current && <span style={{ fontSize: 11, background: '#c8e6c9', padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>{translate('CommunityHealth.current')}</span>}
        </div>
        <h2 style={{ margin: '0 0 12px' }}>{g.title}</h2>
        <p style={{ color: '#555', lineHeight: 1.6 }}>{g.summary}</p>
        {g.full_text && <p style={{ color: '#666', lineHeight: 1.5 }}>{g.full_text}</p>}

        {g.recommendations?.length > 0 && (
          <div style={{ marginTop: 20 }}>
            <h4 style={{ marginBottom: 8 }}>{translate('CommunityHealth.key_recommendations')}</h4>
            <ul style={{ paddingLeft: 20, margin: 0 }}>
              {g.recommendations.map((r, i) => (
                <li key={i} style={{ fontSize: 13, color: '#444', marginBottom: 6, lineHeight: 1.4 }}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 20 }}>
          {g.effective_date && (
            <div><strong style={{ fontSize: 12 }}>{translate('CommunityHealth.effective_date')}</strong> <span style={{ fontSize: 13 }}>{g.effective_date}</span></div>
          )}
          {g.target_population?.length > 0 && (
            <div>
              <strong style={{ fontSize: 12 }}>{translate('CommunityHealth.target_population_2')}</strong>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                {g.target_population.map((p, i) => (
                  <span key={i} style={{ fontSize: 11, background: '#f0f0f0', padding: '2px 8px', borderRadius: 8 }}>{p}</span>
                ))}
              </div>
            </div>
          )}
          {g.applicable_countries?.length > 0 && (
            <div><strong style={{ fontSize: 12 }}>{translate('CommunityHealth.countries_2')}</strong> <span style={{ fontSize: 13 }}>{g.applicable_countries.join(', ')}</span></div>
          )}
        </div>

        {g.source_url && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #eee' }}>
            <a href={g.source_url} target="_blank" rel="noopener noreferrer"
              style={{ color: 'var(--primary)', fontWeight: 600, fontSize: 13 }}>
              {translate('CommunityHealth.view_full_guideline')}
            </a>
          </div>
        )}

        {g.tags?.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {g.tags.map((t, i) => (
              <span key={i} style={{ fontSize: 10, color: '#999', background: '#f8f8f8', padding: '2px 6px', borderRadius: 4 }}>#{t}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── REPORTS ────────────────────────────────────────────────────────────

function ReportsTab({ reports, onSubmit }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    report_type: 'symptom_cluster', title: '', description: '', location_name: '',
    country: '', severity: 'moderate', number_affected: 1, symptoms_reported: '',
  });
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        number_affected: parseInt(form.number_affected) || 1,
        symptoms_reported: form.symptoms_reported ? form.symptoms_reported.split(',').map(s => s.trim()).filter(Boolean) : null,
      };
      await api.post('/community/reports', payload);
      setShowForm(false);
      setForm({ report_type: 'symptom_cluster', title: '', description: '', location_name: '',
        country: '', severity: 'moderate', number_affected: 1, symptoms_reported: '' });
      onSubmit();
    } catch (err) { console.error(err); alert(translate('CommunityHealth.failed_to_submit_report')); }
    setSubmitting(false);
  }

  const reportTypes = [
    'symptom_cluster', 'food_contamination', 'water_contamination', 'air_quality',
    'disease_outbreak', 'drug_reaction', 'poisoning', 'environmental_hazard', 'vaccine_reaction', 'other',
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0 }}>{translate('CommunityHealth.community_health_reports')}</h3>
        <button onClick={() => setShowForm(!showForm)}
          className="btn btn-primary" style={{ fontSize: 13 }}>
          {showForm ? 'Cancel' : '+ Submit Report'}
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} style={{
          background: '#fff', borderRadius: 12, padding: 20, marginBottom: 20,
          boxShadow: '0 2px 8px rgba(0,0,0,.08)',
        }}>
          <h4 style={{ marginTop: 0 }}>{translate('CommunityHealth.submit_a_community_health_report')}</h4>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>{translate('CommunityHealth.report_type')}</label>
              <select value={form.report_type} onChange={e => setForm({ ...form, report_type: e.target.value })}
                style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd' }}>
                {reportTypes.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>{translate('CommunityHealth.severity')}</label>
              <select value={form.severity} onChange={e => setForm({ ...form, severity: e.target.value })}
                style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd' }}>
                {['info', 'low', 'moderate', 'high', 'critical'].map(s => (
                  <option key={s} value={s}>{SEV_LABELS[s]}</option>
                ))}
              </select>
            </div>
            <div style={{ gridColumn: 'span 2' }}>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>{translate('CommunityHealth.title')}</label>
              <input type="text" required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
                style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd' }} />
            </div>
            <div style={{ gridColumn: 'span 2' }}>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>{translate('CommunityHealth.description')}</label>
              <textarea required value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                rows={3} style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', resize: 'vertical' }} />
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>{translate('CommunityHealth.location')}</label>
              <input type="text" value={form.location_name} onChange={e => setForm({ ...form, location_name: e.target.value })}
                placeholder={translate('CommunityHealth.city_state')} style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd' }} />
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>{translate('CommunityHealth.country')}</label>
              <input type="text" value={form.country} onChange={e => setForm({ ...form, country: e.target.value })}
                placeholder="US, CA, EU..." style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd' }} />
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>{translate('CommunityHealth.affected')}</label>
              <input type="number" min="1" value={form.number_affected}
                onChange={e => setForm({ ...form, number_affected: e.target.value })}
                style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd' }} />
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>{translate('CommunityHealth.symptoms_comma_separated')}</label>
              <input type="text" value={form.symptoms_reported}
                onChange={e => setForm({ ...form, symptoms_reported: e.target.value })}
                placeholder={translate('CommunityHealth.fever_cough_nausea')}
                style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd' }} />
            </div>
          </div>
          <button type="submit" className="btn btn-primary" style={{ marginTop: 16 }} disabled={submitting}>
            {submitting ? 'Submitting...' : 'Submit Report'}
          </button>
        </form>
      )}

      {reports.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
          <div style={{ fontSize: 48 }}>📝</div>
          <p>{translate('CommunityHealth.no_community_reports_yet_be_the_first_to')}</p>
        </div>
      ) : reports.map(r => (
        <div key={r.id} style={{
          background: '#fff', borderRadius: 12, padding: 16, marginBottom: 10,
          boxShadow: '0 2px 6px rgba(0,0,0,.06)',
          borderLeft: `4px solid ${SEV_COLORS[r.severity] || '#999'}`,
        }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
            <SeverityBadge severity={r.severity} />
            <span style={{ fontSize: 10, background: '#f0f0f0', padding: '2px 6px', borderRadius: 4, textTransform: 'capitalize' }}>
              {(r.report_type || '').replace(/_/g, ' ')}
            </span>
            {r.is_verified && <span style={{ fontSize: 10, color: '#4caf50', fontWeight: 700 }}>{translate('CommunityHealth.verified')}</span>}
            {r.location_name && <span style={{ fontSize: 10, color: '#666' }}>📍 {r.location_name}</span>}
          </div>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{r.title}</div>
          <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{r.description}</div>
          {r.symptoms_reported?.length > 0 && (
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
              {r.symptoms_reported.map((s, i) => (
                <span key={i} style={{ fontSize: 10, background: '#fce4ec', padding: '1px 6px', borderRadius: 4, color: '#c62828' }}>{s}</span>
              ))}
            </div>
          )}
          <div style={{ fontSize: 10, color: '#999', marginTop: 6 }}>
            {r.number_affected && `${r.number_affected} affected`}
            {r.created_at && ` · ${new Date(r.created_at).toLocaleDateString()}`}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── SETTINGS (Subscriptions) ──────────────────────────────────────────

function SettingsTab({ subscription, categories, sources, onSave }) {
  const [form, setForm] = useState({
    categories: subscription?.categories || [],
    sources: subscription?.sources || [],
    countries: subscription?.countries || [],
    severities: subscription?.severities || ['critical', 'high'],
    push_enabled: subscription?.push_enabled ?? true,
    email_enabled: subscription?.email_enabled ?? false,
    sms_enabled: subscription?.sms_enabled ?? false,
  });
  const [saving, setSaving] = useState(false);
  const [countriesInput, setCountriesInput] = useState((subscription?.countries || []).join(', '));

  function toggleArray(arr, val) {
    return arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val];
  }

  async function handleSave() {
    setSaving(true);
    try {
      await api.put('/community/subscriptions', {
        ...form,
        countries: countriesInput.split(',').map(s => s.trim()).filter(Boolean),
      });
      onSave();
    } catch (err) { console.error(err); alert(translate('CommunityHealth.failed_to_save_preferences')); }
    setSaving(false);
  }

  const chipStyle = (active) => ({
    padding: '4px 12px', borderRadius: 20, fontSize: 12, cursor: 'pointer',
    border: active ? '2px solid var(--primary)' : '1px solid #ddd',
    background: active ? '#e3f2fd' : '#fff', fontWeight: active ? 600 : 400,
    transition: 'all .15s',
  });

  return (
    <div style={{ maxWidth: 700 }}>
      <h3>{translate('CommunityHealth.alert_subscription_preferences')}</h3>
      <p style={{ color: '#666', fontSize: 13, marginBottom: 20 }}>
        {translate('CommunityHealth.choose_which_alert_categories_sources')}
      </p>

      {/* Categories */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontWeight: 700, fontSize: 14, display: 'block', marginBottom: 8 }}>{translate('CommunityHealth.categories')}</label>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {categories.map(c => (
            <button key={c.id} type="button"
              onClick={() => setForm({ ...form, categories: toggleArray(form.categories, c.id) })}
              style={chipStyle(form.categories.includes(c.id))}>
              {c.icon} {c.name}
            </button>
          ))}
        </div>
      </div>

      {/* Sources */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontWeight: 700, fontSize: 14, display: 'block', marginBottom: 8 }}>{translate('CommunityHealth.sources')}</label>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {sources.map(s => (
            <button key={s.id} type="button"
              onClick={() => setForm({ ...form, sources: toggleArray(form.sources, s.id) })}
              style={chipStyle(form.sources.includes(s.id))}>
              {s.name}
            </button>
          ))}
        </div>
      </div>

      {/* Severities */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontWeight: 700, fontSize: 14, display: 'block', marginBottom: 8 }}>{translate('CommunityHealth.minimum_severity')}</label>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {['critical', 'high', 'moderate', 'low', 'info'].map(s => (
            <button key={s} type="button"
              onClick={() => setForm({ ...form, severities: toggleArray(form.severities, s) })}
              style={{ ...chipStyle(form.severities.includes(s)), borderColor: form.severities.includes(s) ? SEV_COLORS[s] : '#ddd' }}>
              {SEV_LABELS[s]}
            </button>
          ))}
        </div>
      </div>

      {/* Countries */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontWeight: 700, fontSize: 14, display: 'block', marginBottom: 8 }}>{translate('CommunityHealth.countries_iso_codes')}</label>
        <input type="text" value={countriesInput} onChange={e => setCountriesInput(e.target.value)}
          placeholder="US, CA, EU, UK, AU..."
          style={{ padding: 8, borderRadius: 8, border: '1px solid #ddd', width: '100%', maxWidth: 400 }} />
      </div>

      {/* Notification channels */}
      <div style={{ marginBottom: 24 }}>
        <label style={{ fontWeight: 700, fontSize: 14, display: 'block', marginBottom: 8 }}>{translate('CommunityHealth.notification_channels')}</label>
        <div style={{ display: 'flex', gap: 16 }}>
          {[
            { key: 'push_enabled', label: translate('CommunityHealth.push'), },
            { key: 'email_enabled', label: translate('CommunityHealth.email') },
            { key: 'sms_enabled', label: '📱 SMS' },
          ].map(({ key, label }) => (
            <label key={key} style={{ display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={form[key]} onChange={() => setForm({ ...form, [key]: !form[key] })} />
              {label}
            </label>
          ))}
        </div>
      </div>

      <button onClick={handleSave} className="btn btn-primary" disabled={saving}>
        {saving ? 'Saving...' : 'Save Preferences'}
      </button>
    </div>
  );
}

// ── FDA RECALLS ────────────────────────────────────────────────────────

const FDA_CLASS_COLORS = {
  'Class I': { bg: '#fee2e2', color: '#ef4444', get label() { return translate('CommunityHealth.class_i_dangerous'); } },
  'Class II': { bg: '#fef3c7', color: '#f59e0b', get label() { return translate('CommunityHealth.class_ii_may_cause_harm'); } },
  'Class III': { bg: '#dbeafe', color: '#3b82f6', get label() { return translate('CommunityHealth.class_iii_minor_violations'); } },
};

function FDARecallsTab() {
  const [form, setForm] = useState({ search_term: '', days: 30, limit: 10 });
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSearch(e) {
    e.preventDefault();
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (form.search_term) params.append('search_term', form.search_term);
      params.append('days', form.days);
      params.append('limit', form.limit);
      const { data } = await api.get(`/fda-recalls/?${params}`);
      setResults(data);
    } catch (err) {
      alert(translate('CommunityHealth.error_searching_fda_recalls'));
    } finally {
      setLoading(false);
    }
  }

  async function loadRecent() {
    setLoading(true);
    try {
      const { data } = await api.get('/fda-recalls/recent');
      setResults(data);
      setForm(p => ({ ...p, search_term: '', days: 7 }));
    } catch (err) {
      alert(translate('CommunityHealth.error_loading_recent_recalls'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0 }}>{translate('CommunityHealth.fda_food_drug_recalls')}</h3>
        <button className="btn btn-secondary" onClick={loadRecent} disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {translate('CommunityHealth.recent_7_days')}
        </button>
      </div>

      <div style={{ background: '#fff', borderRadius: 12, padding: 20, boxShadow: '0 2px 8px rgba(0,0,0,.06)', marginBottom: 20 }}>
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: 2, minWidth: 200 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4, color: '#555' }}>{translate('CommunityHealth.search_term')}</label>
            <input style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #ddd', width: '100%' }}
              placeholder={translate('CommunityHealth.e_g_peanut_salmonella')} value={form.search_term}
              onChange={e => setForm(p => ({ ...p, search_term: e.target.value }))} />
          </div>
          <div style={{ flex: 0.5, minWidth: 90 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4, color: '#555' }}>{translate('CommunityHealth.days')}</label>
            <input type="number" min={1} max={365} value={form.days}
              style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #ddd', width: '100%' }}
              onChange={e => setForm(p => ({ ...p, days: e.target.value }))} />
          </div>
          <div style={{ flex: 0.5, minWidth: 80 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 4, color: '#555' }}>{translate('CommunityHealth.limit')}</label>
            <input type="number" min={1} max={100} value={form.limit}
              style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #ddd', width: '100%' }}
              onChange={e => setForm(p => ({ ...p, limit: e.target.value }))} />
          </div>
          <button className="btn btn-primary" disabled={loading} style={{ height: 40 }}>
            {loading ? 'Searching...' : '🔍 Search'}
          </button>
        </form>
      </div>

      {results && (
        <div>
          <p style={{ marginBottom: 12, color: '#666', fontSize: 13 }}>
            <strong>{results.total}</strong> {(results.total !== 1) ? translate('CommunityHealth.recalls_found') : translate('CommunityHealth.recall_found')}
          </p>

          {results.results?.length === 0 && (
            <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
              <div style={{ fontSize: 48 }}>✅</div>
              <p>{translate('CommunityHealth.no_recalls_found_for_the_given_criteria')}</p>
            </div>
          )}

          {results.results?.map((item, i) => {
            const cls = FDA_CLASS_COLORS[item.classification] || FDA_CLASS_COLORS['Class III'];
            return (
              <div key={i} style={{
                background: '#fff', borderRadius: 12, padding: 18, marginBottom: 12,
                boxShadow: '0 2px 6px rgba(0,0,0,.06)',
                borderLeft: `4px solid ${cls.color}`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, marginBottom: 10 }}>
                  <div style={{ fontWeight: 700, fontSize: 14, flex: 1 }}>{item.product_description}</div>
                  <span style={{
                    padding: '2px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700,
                    background: cls.bg, color: cls.color, whiteSpace: 'nowrap',
                  }}>
                    {cls.label}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 10 }}>
                  <span style={{ flexShrink: 0, marginTop: 1 }}>⚠️</span>
                  <p style={{ fontSize: 13, color: '#555', margin: 0 }}>{item.reason}</p>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 6, fontSize: 12, color: '#666' }}>
                  {item.recalling_firm && <div><strong>{translate('CommunityHealth.firm')}</strong> {item.recalling_firm}</div>}
                  {(item.city || item.state) && <div><strong>{translate('CommunityHealth.location_2')}</strong> {[item.city, item.state, item.country].filter(Boolean).join(', ')}</div>}
                  {item.recall_date && <div><strong>{translate('CommunityHealth.date')}</strong> {item.recall_date}</div>}
                  {item.status && <div><strong>{translate('CommunityHealth.status')}</strong> {item.status}</div>}
                  {item.recall_number && <div><strong>{translate('CommunityHealth.recall')}</strong> {item.recall_number}</div>}
                  {item.voluntary_mandated && <div><strong>{translate('CommunityHealth.type_2')}</strong> {item.voluntary_mandated}</div>}
                </div>

                {item.distribution_pattern && (
                  <details style={{ marginTop: 10 }}>
                    <summary style={{ cursor: 'pointer', fontSize: 12, color: '#2196f3', fontWeight: 600 }}>
                      {translate('CommunityHealth.distribution_pattern')}
                    </summary>
                    <p style={{ marginTop: 4, fontSize: 12, color: '#888' }}>
                      {item.distribution_pattern}
                    </p>
                  </details>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
