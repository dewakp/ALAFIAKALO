import { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus, Trash2, Edit2, Refrigerator, Snowflake, Package, AlertTriangle } from 'lucide-react';
import BackButton from '../components/BackButton';
import { t } from '../i18n';

const CATEGORIES = [
  'produce', 'dairy', 'meat', 'seafood', 'grains', 'canned',
  'frozen', 'beverages', 'condiments', 'snacks', 'baking', 'spices', 'other',
];

const LOCATIONS = [
  { value: 'refrigerator', get label() { return t('Pantry.refrigerator'); }, icon: Refrigerator },
  { value: 'freezer', get label() { return t('Pantry.freezer'); }, icon: Snowflake },
  { value: 'pantry', get label() { return t('Pantry.pantry'); }, icon: Package },
];

const UNITS = ['pieces', 'lbs', 'oz', 'kg', 'g', 'liters', 'ml', 'cups', 'gallons', 'bags', 'boxes', 'cans', 'bottles'];

const EMPTY_FORM = {
  name: '', category: 'other', quantity: 1, unit: 'pieces',
  location: 'pantry', expiration_date: '', notes: '',
  auto_replenish: false, low_threshold: '',
};

export default function Pantry() {
  const [items, setItems] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [editingId, setEditingId] = useState(null);
  const [filterLocation, setFilterLocation] = useState('all');

  useEffect(() => { loadItems(); }, []);

  async function loadItems() {
    const params = filterLocation !== 'all' ? { location: filterLocation } : {};
    const { data } = await api.get('/pantry/', { params });
    setItems(data);
  }

  useEffect(() => { loadItems(); }, [filterLocation]);

  async function handleSubmit(e) {
    e.preventDefault();
    const payload = {
      ...form,
      quantity: parseFloat(form.quantity) || 1,
      expiration_date: form.expiration_date || null,
      low_threshold: form.low_threshold ? parseFloat(form.low_threshold) : null,
    };
    if (editingId) {
      await api.put(`/pantry/${editingId}`, payload);
    } else {
      await api.post('/pantry/', payload);
    }
    setShowForm(false);
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    loadItems();
  }

  async function handleDelete(id) {
    await api.delete(`/pantry/${id}`);
    loadItems();
  }

  function startEdit(item) {
    setForm({
      name: item.name,
      category: item.category,
      quantity: item.quantity,
      unit: item.unit,
      location: item.location,
      expiration_date: item.expiration_date || '',
      notes: item.notes || '',
      auto_replenish: item.auto_replenish,
      low_threshold: item.low_threshold ?? '',
    });
    setEditingId(item.id);
    setShowForm(true);
  }

  function isExpiringSoon(dateStr) {
    if (!dateStr) return false;
    const diff = (new Date(dateStr) - new Date()) / (1000 * 60 * 60 * 24);
    return diff >= 0 && diff <= 3;
  }

  function isExpired(dateStr) {
    if (!dateStr) return false;
    return new Date(dateStr) < new Date();
  }

  const grouped = LOCATIONS.map(loc => ({
    ...loc,
    items: items.filter(i => i.location === loc.value),
  })).filter(g => filterLocation === 'all' || g.value === filterLocation);

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">{t('Pantry.pantry_refrigerator')}</h1>
        </div>
        <button className="btn btn-primary" onClick={() => {
          setShowForm(!showForm);
          if (showForm) { setEditingId(null); setForm({ ...EMPTY_FORM }); }
        }}>
          <Plus size={18} /> {(showForm) ? t('Pantry.cancel') : t('Pantry.add_item')}
        </button>
      </div>

      {/* Location filter */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <button
          className={`btn ${filterLocation === 'all' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setFilterLocation('all')}
        >{t('Pantry.all')}</button>
        {LOCATIONS.map(loc => (
          <button
            key={loc.value}
            className={`btn ${filterLocation === loc.value ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setFilterLocation(loc.value)}
          >
            <loc.icon size={16} /> {loc.label}
          </button>
        ))}
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleSubmit}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Pantry.item_name')}</label>
                <input className="form-input" value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Pantry.category')}</label>
                <select className="form-input" value={form.category}
                  onChange={e => setForm({ ...form, category: e.target.value })}>
                  {CATEGORIES.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Pantry.quantity')}</label>
                <input className="form-input" type="number" step="0.1" min="0" value={form.quantity}
                  onChange={e => setForm({ ...form, quantity: e.target.value })} required />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Pantry.unit')}</label>
                <select className="form-input" value={form.unit}
                  onChange={e => setForm({ ...form, unit: e.target.value })}>
                  {UNITS.map(u => <option key={u} value={u}>{u}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{t('Pantry.location')}</label>
                <select className="form-input" value={form.location}
                  onChange={e => setForm({ ...form, location: e.target.value })}>
                  {LOCATIONS.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t('Pantry.expiration_date')}</label>
                <input className="form-input" type="date" value={form.expiration_date}
                  onChange={e => setForm({ ...form, expiration_date: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">{t('Pantry.notes')}</label>
                <input className="form-input" value={form.notes}
                  onChange={e => setForm({ ...form, notes: e.target.value })} />
              </div>
            </div>

            {/* Future: Auto-replenish settings */}
            <details style={{ marginTop: '0.75rem', marginBottom: '0.75rem' }}>
              <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                {t('Pantry.auto_replenish_coming_soon')}
              </summary>
              <div className="form-row" style={{ marginTop: '0.5rem', opacity: 0.5, pointerEvents: 'none' }}>
                <div className="form-group">
                  <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <input type="checkbox" checked={form.auto_replenish}
                      onChange={e => setForm({ ...form, auto_replenish: e.target.checked })} />
                    {t('Pantry.enable_auto_replenish')}
                  </label>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', margin: '0.25rem 0 0' }}>
                    {t('Pantry.will_connect_to_grocery_services')}
                  </p>
                </div>
                <div className="form-group">
                  <label className="form-label">{t('Pantry.low_stock_threshold')}</label>
                  <input className="form-input" type="number" step="0.1" min="0" value={form.low_threshold}
                    onChange={e => setForm({ ...form, low_threshold: e.target.value })} placeholder="e.g. 2" />
                </div>
              </div>
            </details>

            <button className="btn btn-primary" type="submit">
              {editingId ? 'Update Item' : 'Add Item'}
            </button>
          </form>
        </div>
      )}

      {items.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <Package size={48} style={{ color: 'var(--text-secondary)', margin: '0 auto 1rem' }} />
          <p style={{ color: 'var(--text-secondary)' }}>{t('Pantry.no_items_yet_add_items_from_your_pantry')}</p>
        </div>
      ) : (
        grouped.map(group => (
          group.items.length > 0 && (
            <div key={group.value} style={{ marginBottom: '1.5rem' }}>
              <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                <group.icon size={22} /> {group.label}
                <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', fontWeight: 'normal' }}>
                  {t('Pantry.items', { items: group.items.length })}
                </span>
              </h2>
              <div className="data-table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t('Pantry.item')}</th>
                      <th>{t('Pantry.category')}</th>
                      <th>{t('Pantry.qty')}</th>
                      <th>{t('Pantry.expires')}</th>
                      <th>{t('Pantry.notes')}</th>
                      <th style={{ width: '100px' }}>{t('Pantry.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.items.map(item => (
                      <tr key={item.id} style={isExpired(item.expiration_date)
                        ? { background: 'rgba(239,68,68,0.08)' }
                        : isExpiringSoon(item.expiration_date)
                          ? { background: 'rgba(245,158,11,0.08)' }
                          : {}
                      }>
                        <td style={{ fontWeight: 600 }}>{item.name}</td>
                        <td>
                          <span className="badge" style={{ textTransform: 'capitalize' }}>
                            {item.category}
                          </span>
                        </td>
                        <td>{item.quantity} {item.unit}</td>
                        <td>
                          {item.expiration_date ? (
                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                              {isExpired(item.expiration_date) && <AlertTriangle size={14} style={{ color: '#ef4444' }} />}
                              {isExpiringSoon(item.expiration_date) && !isExpired(item.expiration_date) && <AlertTriangle size={14} style={{ color: '#f59e0b' }} />}
                              {item.expiration_date}
                            </span>
                          ) : '—'}
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                          {item.notes || '—'}
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: '0.25rem' }}>
                            <button className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem' }}
                              onClick={() => startEdit(item)}>
                              <Edit2 size={14} />
                            </button>
                            <button className="btn" style={{ padding: '0.25rem 0.5rem', color: '#ef4444' }}
                              onClick={() => handleDelete(item.id)}>
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )
        ))
      )}
    </div>
  );
}
