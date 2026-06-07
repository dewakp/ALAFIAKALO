import { useState, useEffect, useMemo } from 'react';
import api from '../services/api';
import { Plus, ChevronLeft, ChevronRight, Check, Trash2, X, Clock, MapPin, Calendar as CalIcon, Repeat } from 'lucide-react';
import BackButton from '../components/BackButton';

const CATEGORIES = [
  { key: 'appointment', label: 'Appointment', color: '#2196F3' },
  { key: 'meal', label: 'Meal', color: '#4CAF50' },
  { key: 'medication', label: 'Medication', color: '#FF9800' },
  { key: 'exercise', label: 'Exercise', color: '#E91E63' },
  { key: 'meditation', label: 'Meditation', color: '#9C27B0' },
  { key: 'therapy', label: 'Therapy', color: '#00BCD4' },
  { key: 'lab', label: 'Lab / Test', color: '#795548' },
  { key: 'wellness', label: 'Wellness', color: '#607D8B' },
  { key: 'custom', label: 'Custom', color: '#9E9E9E' },
];
const STATUS_OPTIONS = ['scheduled', 'completed', 'missed', 'cancelled', 'skipped'];
const RECURRENCE_OPTIONS = ['none', 'daily', 'weekly', 'biweekly', 'monthly', 'yearly'];
const PRIORITY_OPTIONS = ['low', 'medium', 'high'];

const catColor = (key) => CATEGORIES.find(c => c.key === key)?.color || '#9E9E9E';
const catLabel = (key) => CATEGORIES.find(c => c.key === key)?.label || key;
const today = () => new Date().toISOString().split('T')[0];

function daysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate();
}

function calendarGrid(year, month) {
  const firstDay = new Date(year, month, 1).getDay();
  const total = daysInMonth(year, month);
  const rows = [];
  let day = 1 - firstDay;
  for (let w = 0; w < 6; w++) {
    const week = [];
    for (let d = 0; d < 7; d++, day++) {
      week.push(day >= 1 && day <= total ? day : null);
    }
    if (week.some(d => d !== null)) rows.push(week);
  }
  return rows;
}

const EMPTY_FORM = {
  title: '', description: '', category: 'appointment', event_date: today(),
  start_time: '', end_time: '', all_day: false, recurrence: 'none',
  recurrence_end_date: '', location: '', reminder_minutes: '',
  priority: '', notes: '', color: '',
};

export default function Calendar() {
  const [events, setEvents] = useState([]);
  const [viewDate, setViewDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(today());
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [editId, setEditId] = useState(null);
  const [filterCat, setFilterCat] = useState('');

  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();
  const monthLabel = viewDate.toLocaleString('default', { month: 'long', year: 'numeric' });

  useEffect(() => { loadMonth(); }, [year, month]);

  async function loadMonth() {
    const start = `${year}-${String(month + 1).padStart(2, '0')}-01`;
    const endDay = daysInMonth(year, month);
    const end = `${year}-${String(month + 1).padStart(2, '0')}-${String(endDay).padStart(2, '0')}`;
    try {
      const { data } = await api.get('/calendar/', { params: { start_date: start, end_date: end, limit: 500 } });
      setEvents(data);
    } catch { /* ignore */ }
  }

  const eventsOnDate = useMemo(() => {
    let filtered = events.filter(e => e.event_date === selectedDate);
    if (filterCat) filtered = filtered.filter(e => e.category === filterCat);
    return filtered;
  }, [events, selectedDate, filterCat]);

  const eventCountByDate = useMemo(() => {
    const m = {};
    events.forEach(e => { m[e.event_date] = (m[e.event_date] || 0) + 1; });
    return m;
  }, [events]);

  function prevMonth() { setViewDate(new Date(year, month - 1, 1)); }
  function nextMonth() { setViewDate(new Date(year, month + 1, 1)); }

  function openCreate(dateStr) {
    setForm({ ...EMPTY_FORM, event_date: dateStr || selectedDate });
    setEditId(null);
    setShowForm(true);
  }

  function openEdit(ev) {
    setForm({
      title: ev.title, description: ev.description || '', category: ev.category,
      event_date: ev.event_date, start_time: ev.start_time?.slice(0, 5) || '',
      end_time: ev.end_time?.slice(0, 5) || '', all_day: ev.all_day,
      recurrence: ev.recurrence || 'none', recurrence_end_date: ev.recurrence_end_date || '',
      location: ev.location || '', reminder_minutes: ev.reminder_minutes ?? '',
      priority: ev.priority || '', notes: ev.notes || '', color: ev.color || '',
    });
    setEditId(ev.id);
    setShowForm(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const payload = { ...form };
    if (!payload.start_time) delete payload.start_time;
    if (!payload.end_time) delete payload.end_time;
    if (payload.recurrence === 'none') payload.recurrence = null;
    if (!payload.recurrence_end_date) delete payload.recurrence_end_date;
    if (!payload.reminder_minutes && payload.reminder_minutes !== 0) delete payload.reminder_minutes;
    else payload.reminder_minutes = Number(payload.reminder_minutes);
    if (!payload.priority) delete payload.priority;
    if (!payload.color) delete payload.color;
    if (!payload.description) delete payload.description;
    if (!payload.notes) delete payload.notes;
    if (!payload.location) delete payload.location;

    try {
      if (editId) {
        await api.patch(`/calendar/${editId}`, payload);
      } else {
        await api.post('/calendar/', payload);
      }
      setShowForm(false);
      loadMonth();
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error saving event');
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this event?')) return;
    await api.delete(`/calendar/${id}`);
    loadMonth();
  }

  async function handleComplete(id) {
    await api.patch(`/calendar/${id}/complete`);
    loadMonth();
  }

  const grid = calendarGrid(year, month);
  const todayStr = today();

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Calendar</h1>
        </div>
        <button className="btn btn-primary" onClick={() => openCreate(selectedDate)}>
          <Plus size={18} /> New Event
        </button>
      </div>

      {/* Month navigation */}
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <button className="btn btn-secondary btn-sm" onClick={prevMonth}><ChevronLeft size={16} /></button>
          <h2 style={{ margin: 0, fontSize: '1.2rem' }}>{monthLabel}</h2>
          <button className="btn btn-secondary btn-sm" onClick={nextMonth}><ChevronRight size={16} /></button>
        </div>

        {/* Calendar grid */}
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
          <thead>
            <tr>
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
                <th key={d} style={{ padding: '6px', textAlign: 'center', fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>{d}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.map((week, wi) => (
              <tr key={wi}>
                {week.map((day, di) => {
                  if (!day) return <td key={di} style={{ padding: '4px' }} />;
                  const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                  const isToday = dateStr === todayStr;
                  const isSelected = dateStr === selectedDate;
                  const count = eventCountByDate[dateStr] || 0;
                  return (
                    <td key={di} style={{ padding: '2px', textAlign: 'center', cursor: 'pointer' }}
                      onClick={() => setSelectedDate(dateStr)}
                    >
                      <div style={{
                        width: 36, height: 36, lineHeight: '36px', borderRadius: '50%', margin: '0 auto',
                        fontWeight: isToday ? 700 : 400,
                        background: isSelected ? 'var(--color-primary)' : isToday ? 'var(--color-primary-light)' : 'transparent',
                        color: isSelected ? '#fff' : isToday ? 'var(--color-primary-dark)' : 'inherit',
                        position: 'relative',
                      }}>
                        {day}
                        {count > 0 && (
                          <span style={{
                            position: 'absolute', bottom: -2, left: '50%', transform: 'translateX(-50%)',
                            width: 6, height: 6, borderRadius: '50%', background: 'var(--color-primary)',
                          }} />
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Category filter */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: '1rem' }}>
        <button className={`btn btn-sm ${!filterCat ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setFilterCat('')}>All</button>
        {CATEGORIES.map(c => (
          <button key={c.key}
            className={`btn btn-sm ${filterCat === c.key ? 'btn-primary' : 'btn-secondary'}`}
            style={filterCat === c.key ? { background: c.color, borderColor: c.color } : {}}
            onClick={() => setFilterCat(filterCat === c.key ? '' : c.key)}
          >{c.label}</button>
        ))}
      </div>

      {/* Events for selected date */}
      <div style={{ marginBottom: '1rem' }}>
        <h3 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>
          {new Date(selectedDate + 'T12:00:00').toLocaleDateString('default', { weekday: 'long', month: 'long', day: 'numeric' })}
          <span style={{ color: 'var(--color-text-secondary)', fontWeight: 400 }}> — {eventsOnDate.length} event{eventsOnDate.length !== 1 ? 's' : ''}</span>
        </h3>
        {eventsOnDate.length === 0 && (
          <div className="card" style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: '2rem' }}>
            No events on this day.
            <br />
            <button className="btn btn-primary btn-sm" style={{ marginTop: 8 }} onClick={() => openCreate(selectedDate)}>
              <Plus size={14} /> Add Event
            </button>
          </div>
        )}

        {eventsOnDate.map(ev => (
          <div key={ev.id} className="card" style={{
            marginBottom: '0.75rem', borderLeft: `4px solid ${ev.color || catColor(ev.category)}`,
            opacity: ev.status === 'cancelled' ? 0.5 : 1,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{
                    fontSize: '0.7rem', padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                    background: ev.color || catColor(ev.category), color: '#fff',
                  }}>{catLabel(ev.category)}</span>
                  {ev.priority && (
                    <span style={{
                      fontSize: '0.7rem', padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                      background: ev.priority === 'high' ? '#f44336' : ev.priority === 'medium' ? '#ff9800' : '#9e9e9e',
                      color: '#fff',
                    }}>{ev.priority}</span>
                  )}
                  {ev.status !== 'scheduled' && (
                    <span style={{
                      fontSize: '0.7rem', padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                      background: ev.status === 'completed' ? '#4caf50' : '#f44336', color: '#fff',
                    }}>{ev.status}</span>
                  )}
                </div>
                <div style={{ fontWeight: 600, fontSize: '1rem', textDecoration: ev.status === 'completed' ? 'line-through' : 'none' }}>
                  {ev.title}
                </div>
                {ev.description && <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginTop: 2 }}>{ev.description}</div>}
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 6, fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                  {(ev.start_time || ev.all_day) && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                      <Clock size={12} />
                      {ev.all_day ? 'All day' : `${ev.start_time?.slice(0, 5)}${ev.end_time ? ' – ' + ev.end_time?.slice(0, 5) : ''}`}
                    </span>
                  )}
                  {ev.location && <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}><MapPin size={12} />{ev.location}</span>}
                  {ev.recurrence && <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}><Repeat size={12} />{ev.recurrence}</span>}
                </div>
                {ev.notes && <div style={{ fontSize: '0.8rem', marginTop: 6, fontStyle: 'italic', color: 'var(--color-text-secondary)' }}>{ev.notes}</div>}
              </div>
              <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                {ev.status === 'scheduled' && (
                  <button className="btn btn-sm" title="Complete" style={{ background: '#4caf50', color: '#fff', border: 'none' }}
                    onClick={() => handleComplete(ev.id)}><Check size={14} /></button>
                )}
                <button className="btn btn-secondary btn-sm" title="Edit" onClick={() => openEdit(ev)}>Edit</button>
                <button className="btn btn-danger btn-sm" title="Delete" onClick={() => handleDelete(ev.id)}><Trash2 size={14} /></button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Create/Edit form modal */}
      {showForm && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setShowForm(false)}>
          <div className="card" style={{ maxWidth: 560, width: '95%', maxHeight: '85vh', overflowY: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 style={{ margin: 0 }}>{editId ? 'Edit Event' : 'New Event'}</h2>
              <button className="btn btn-sm btn-secondary" onClick={() => setShowForm(false)}><X size={16} /></button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">Title *</label>
                <input className="form-input" value={form.title} required
                  onChange={e => setForm({ ...form, title: e.target.value })} />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Category</label>
                  <select className="form-input" value={form.category}
                    onChange={e => setForm({ ...form, category: e.target.value })}>
                    {CATEGORIES.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Date *</label>
                  <input className="form-input" type="date" value={form.event_date} required
                    onChange={e => setForm({ ...form, event_date: e.target.value })} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Start Time</label>
                  <input className="form-input" type="time" value={form.start_time} disabled={form.all_day}
                    onChange={e => setForm({ ...form, start_time: e.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">End Time</label>
                  <input className="form-input" type="time" value={form.end_time} disabled={form.all_day}
                    onChange={e => setForm({ ...form, end_time: e.target.value })} />
                </div>
                <div className="form-group" style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 6 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input type="checkbox" checked={form.all_day}
                      onChange={e => setForm({ ...form, all_day: e.target.checked })} />
                    All day
                  </label>
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Description</label>
                <textarea className="form-input" rows={2} value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })} />
              </div>
              <div className="form-group">
                <label className="form-label">Location</label>
                <input className="form-input" value={form.location} placeholder="e.g., Dr. Smith's Clinic"
                  onChange={e => setForm({ ...form, location: e.target.value })} />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Recurrence</label>
                  <select className="form-input" value={form.recurrence}
                    onChange={e => setForm({ ...form, recurrence: e.target.value })}>
                    {RECURRENCE_OPTIONS.map(r => <option key={r} value={r}>{r === 'none' ? 'No repeat' : r}</option>)}
                  </select>
                </div>
                {form.recurrence !== 'none' && (
                  <div className="form-group">
                    <label className="form-label">Repeat Until</label>
                    <input className="form-input" type="date" value={form.recurrence_end_date}
                      onChange={e => setForm({ ...form, recurrence_end_date: e.target.value })} />
                  </div>
                )}
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Priority</label>
                  <select className="form-input" value={form.priority}
                    onChange={e => setForm({ ...form, priority: e.target.value })}>
                    <option value="">None</option>
                    {PRIORITY_OPTIONS.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Reminder (minutes before)</label>
                  <input className="form-input" type="number" min={0} value={form.reminder_minutes}
                    placeholder="e.g., 30"
                    onChange={e => setForm({ ...form, reminder_minutes: e.target.value })} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Notes</label>
                <textarea className="form-input" rows={2} value={form.notes}
                  onChange={e => setForm({ ...form, notes: e.target.value })} />
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">{editId ? 'Save Changes' : 'Create Event'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
