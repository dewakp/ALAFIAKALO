import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Plus, BookOpen, Apple, Zap, Pill, CalendarDays, ExternalLink } from 'lucide-react';

/* ─── helpers ─── */
const todayStr = () => new Date().toISOString().split('T')[0];
const fmtDateLabel = (d) => new Date(d + 'T12:00:00').toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
const fmtTime = (t) => { if (!t) return ''; const [h, m] = t.split(':'); const hr = parseInt(h, 10); return `${String(hr % 12 || 12).padStart(2,'0')}:${m} ${hr < 12 ? 'AM' : 'PM'}`; };

function daysInMonth(y, mo) { return new Date(y, mo + 1, 0).getDate(); }
function calGrid(y, mo) {
  const first = new Date(y, mo, 1).getDay();
  const total = daysInMonth(y, mo);
  const rows = []; let d = 1 - first;
  for (let w = 0; w < 6; w++) {
    const row = [];
    for (let i = 0; i < 7; i++, d++) row.push(d >= 1 && d <= total ? d : null);
    if (row.some(x => x !== null)) rows.push(row);
  }
  return rows;
}

/* ─── mini calendar ─── */
function MiniCalendar({ selected, onChange, dotDates }) {
  const [view, setView] = useState(() => { const d = new Date(selected + 'T12:00:00'); return { y: d.getFullYear(), mo: d.getMonth() }; });
  const grid = useMemo(() => calGrid(view.y, view.mo), [view]);
  const label = new Date(view.y, view.mo).toLocaleString('default', { month: 'long', year: 'numeric' });
  const td = todayStr();

  function prev() { setView(v => v.mo === 0 ? { y: v.y - 1, mo: 11 } : { y: v.y, mo: v.mo - 1 }); }
  function next() { setView(v => v.mo === 11 ? { y: v.y + 1, mo: 0 } : { y: v.y, mo: v.mo + 1 }); }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '.75rem' }}>
        <button className="btn btn-secondary btn-sm" onClick={prev} style={{ padding: '4px 8px' }}><ChevronLeft size={14}/></button>
        <span style={{ fontWeight: 700, fontSize: '.9rem' }}>{label}</span>
        <button className="btn btn-secondary btn-sm" onClick={next} style={{ padding: '4px 8px' }}><ChevronRight size={14}/></button>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
        <thead>
          <tr>{['Su','Mo','Tu','We','Th','Fr','Sa'].map(d => (
            <th key={d} style={{ padding: '4px 0', textAlign: 'center', fontSize: '.72rem', color: 'var(--color-text-tertiary)' }}>{d}</th>
          ))}</tr>
        </thead>
        <tbody>
          {grid.map((row, ri) => (
            <tr key={ri}>
              {row.map((day, di) => {
                if (!day) return <td key={di}/>;
                const ds = `${view.y}-${String(view.mo+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
                const isSel = ds === selected;
                const isToday = ds === td;
                const hasDot = dotDates?.has(ds);
                return (
                  <td key={di} style={{ padding: '2px 0', textAlign: 'center', cursor: 'pointer' }} onClick={() => onChange(ds)}>
                    <div style={{ width: 30, height: 30, lineHeight: '30px', borderRadius: '50%', margin: '0 auto',
                      fontWeight: isToday ? 700 : 400, fontSize: '.85rem',
                      background: isSel ? 'var(--color-primary)' : isToday ? 'rgba(var(--color-primary-rgb),0.15)' : 'transparent',
                      color: isSel ? '#fff' : isToday ? 'var(--color-primary)' : 'inherit',
                      position: 'relative' }}>
                      {day}
                      {hasDot && !isSel && (
                        <span style={{ position: 'absolute', bottom: 2, left: '50%', transform: 'translateX(-50%)',
                          width: 4, height: 4, borderRadius: '50%', background: 'var(--color-primary)' }}/>
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
  );
}

/* ─── collapsible section ─── */
function Section({ icon: Icon, title, badge, children, link, linkLabel, onLink, defaultOpen = true, accentColor }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card" style={{ marginBottom: '.75rem', padding: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '.85rem 1rem',
        cursor: 'pointer', borderBottom: open ? '1px solid var(--color-border)' : 'none' }}
        onClick={() => setOpen(o => !o)}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem' }}>
          {Icon && <Icon size={16} style={{ color: accentColor || 'var(--color-primary)' }}/>}
          <span style={{ fontWeight: 700, fontSize: '.95rem' }}>{title}</span>
          {badge != null && (
            <span style={{ fontSize: '.75rem', background: 'var(--color-bg-secondary)', borderRadius: 10,
              padding: '1px 8px', color: 'var(--color-text-secondary)' }}>{badge}</span>
          )}
        </div>
        {open ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
      </div>
      {open && (
        <div style={{ padding: '.85rem 1rem' }}>
          {children}
          {link && (
            <button className="btn btn-sm" onClick={e => { e.stopPropagation(); onLink(); }}
              style={{ marginTop: '.6rem', color: 'var(--color-primary)', background: 'none', border: 'none',
                padding: 0, display: 'flex', alignItems: 'center', gap: '.3rem', fontSize: '.82rem', cursor: 'pointer' }}>
              <ExternalLink size={12}/>{linkLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
export default function Dashboard() {
  const navigate = useNavigate();
  const [selDate, setSelDate] = useState(todayStr);
  const [nutrition, setNutrition]   = useState([]);
  const [bowel, setBowel]           = useState([]);
  const [vomiting, setVomiting]     = useState([]);
  const [meds, setMeds]             = useState([]);
  const [events, setEvents]         = useState([]);
  const [mood, setMood]             = useState([]);
  /* dates that have any data — for calendar dots */
  const [dotDates, setDotDates]     = useState(new Set());

  /* load all data for selected date in parallel */
  const load = useCallback(async (d) => {
    const p = { start_date: d, end_date: d };
    const [n, b, v, mo, ev, me] = await Promise.allSettled([
      api.get('/nutrition/', { params: p }),
      api.get('/elimination/bowel', { params: p }),
      api.get('/elimination/vomiting', { params: p }),
      api.get('/mood/', { params: p }),
      api.get('/calendar/', { params: { ...p, limit: 100 } }),
      api.get('/medications/', { params: { limit: 200 } }),
    ]);
    setNutrition(n.status === 'fulfilled' ? n.value.data : []);
    setBowel(b.status === 'fulfilled' ? b.value.data : []);
    setVomiting(v.status === 'fulfilled' ? v.value.data : []);
    setMood(mo.status === 'fulfilled' ? mo.value.data : []);
    setEvents(ev.status === 'fulfilled' ? ev.value.data : []);
    /* medications: show those logged or active */
    if (me.status === 'fulfilled') {
      const medsData = me.value.data;
      /* show ones active on that date */
      const active = medsData.filter(m => m.is_active && (!m.end_date || m.end_date >= d));
      setMeds(active);
    }
  }, []);

  /* load dot dates for the visible month (all nutrition entries) */
  const loadDotDates = useCallback(async () => {
    const today = todayStr();
    const [y, mo] = today.split('-').map(Number);
    const start = `${y}-${String(mo).padStart(2,'0')}-01`;
    const end = today;
    try {
      const { data } = await api.get('/nutrition/', { params: { start_date: start, end_date: end, limit: 1000 } });
      setDotDates(new Set(data.map(n => n.log_date)));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(selDate); }, [load, selDate]);
  useEffect(() => { loadDotDates(); }, [loadDotDates]);

  /* group nutrition by meal_type */
  const mealGroups = useMemo(() => {
    const order = ['breakfast', 'lunch', 'dinner', 'snack', 'other'];
    const g = {};
    nutrition.forEach(n => {
      const k = (n.meal_type || 'other').toLowerCase();
      (g[k] = g[k] || []).push(n);
    });
    return order.filter(k => g[k]).map(k => ({ type: k, items: g[k] }));
  }, [nutrition]);

  /* combine elimination events */
  const elimEvents = useMemo(() => [
    ...bowel.map(e => ({ type: 'Bowel', time: e.time || e.log_date, note: e.stool_type || e.notes || '', ...e })),
    ...vomiting.map(e => ({ type: 'Vomiting', time: e.time || e.log_date, note: e.contents || e.notes || '', ...e })),
  ].sort((a, b) => (a.time > b.time ? 1 : -1)), [bowel, vomiting]);

  const mealEmoji = { breakfast: '🌅', lunch: '☀️', dinner: '🌙', snack: '🍎', other: '🍽️' };
  const noData = (text) => <p style={{ color: 'var(--color-text-tertiary)', fontSize: '.85rem', margin: 0 }}>{text}</p>;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '1.25rem', alignItems: 'start' }}>

      {/* ── LEFT: Calendar ── */}
      <div className="card" style={{ position: 'sticky', top: '1rem' }}>
        <h3 style={{ margin: '0 0 .75rem 0', fontSize: '.9rem', fontWeight: 700, color: 'var(--color-text-secondary)',
          textTransform: 'uppercase', letterSpacing: '.05em' }}>Select Date</h3>
        <MiniCalendar selected={selDate} onChange={setSelDate} dotDates={dotDates}/>
        <div style={{ marginTop: '1rem', paddingTop: '.75rem', borderTop: '1px solid var(--color-border)',
          fontSize: '.8rem', color: 'var(--color-text-secondary)', textAlign: 'center' }}>
          {fmtDateLabel(selDate)}
        </div>
      </div>

      {/* ── RIGHT: Daily sections ── */}
      <div>

        {/* Journal */}
        <Section icon={BookOpen} title={`Journal for ${fmtDateLabel(selDate)}`} accentColor="#8b5cf6">
          {mood.length > 0
            ? mood.map(m => (
                <div key={m.id} style={{ marginBottom: '.5rem' }}>
                  {m.notes && <p style={{ margin: 0, fontSize: '.88rem' }}>{m.notes}</p>}
                  {m.mood_score != null && (
                    <span style={{ fontSize: '.75rem', color: 'var(--color-text-secondary)' }}>
                      Mood score: {m.mood_score}/10
                    </span>
                  )}
                </div>
              ))
            : noData('No journal entry found for this date.')}
        </Section>

        {/* Meals & Nutrition */}
        <Section icon={Apple} title="Meals & Nutrition"
          badge={nutrition.length ? `Daily Totals (${nutrition.length} item${nutrition.length > 1 ? 's' : ''})` : null}
          link={true} linkLabel="View Full Meals Diary" onLink={() => navigate('/meals-diary')}
          accentColor="#10b981">
          {nutrition.length === 0
            ? noData('No meals logged for this date.')
            : mealGroups.map(g => (
                <div key={g.type} style={{ marginBottom: '.6rem' }}>
                  <div style={{ fontWeight: 600, fontSize: '.82rem', color: 'var(--color-text-secondary)',
                    textTransform: 'capitalize', marginBottom: '.25rem' }}>
                    {mealEmoji[g.type]} {g.type}:
                  </div>
                  {g.items.map(item => (
                    <div key={item.id} style={{ fontSize: '.85rem', padding: '.2rem 0 .2rem .75rem',
                      borderLeft: '2px solid var(--color-border)', marginBottom: '.2rem',
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ flex: 1 }}>{item.food_name}</span>
                      {item.calories > 0 && (
                        <span style={{ fontSize: '.75rem', color: 'var(--color-text-tertiary)',
                          fontFamily: 'monospace', marginLeft: '.5rem' }}>
                          {Math.round(item.calories)} kcal
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ))}
        </Section>

        {/* General Activities & Events (Elimination) */}
        <Section icon={Zap} title="General Activities & Events"
          link={elimEvents.length > 0} linkLabel="View Full Elimination Log"
          onLink={() => navigate('/elimination')} accentColor="#f59e0b">
          {elimEvents.length === 0
            ? noData('No elimination events logged for this date.')
            : (
              <div>
                <div style={{ fontWeight: 600, fontSize: '.82rem', color: 'var(--color-text-secondary)', marginBottom: '.35rem' }}>
                  Elimination Events:
                </div>
                {elimEvents.map((e, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: '.4rem',
                    fontSize: '.85rem', marginBottom: '.3rem', paddingLeft: '.5rem' }}>
                    <span style={{ color: 'var(--color-text-secondary)', minWidth: 24 }}>•</span>
                    <span>
                      <strong>{e.type}</strong>
                      {e.time && <span style={{ color: 'var(--color-text-tertiary)' }}> at {fmtTime(typeof e.time === 'string' && e.time.length <= 8 ? e.time : new Date(e.time).toTimeString().slice(0,5))}</span>}
                      {e.note && <span style={{ fontStyle: 'italic', color: 'var(--color-text-tertiary)' }}> — {e.note}</span>}
                    </span>
                  </div>
                ))}
              </div>
            )}
        </Section>

        {/* Medications Taken */}
        <Section icon={Pill} title="Medications Taken" accentColor="#ef4444">
          {meds.length === 0
            ? noData('No medications logged for this date.')
            : (
              <div>
                {meds.slice(0, 5).map(m => (
                  <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between',
                    fontSize: '.85rem', padding: '.3rem 0', borderBottom: '1px solid var(--color-border)' }}>
                    <span>{m.name || m.medication_name}</span>
                    <span style={{ color: 'var(--color-text-secondary)', fontSize: '.78rem' }}>
                      {m.dosage || ''} {m.unit || ''}
                    </span>
                  </div>
                ))}
                {meds.length > 5 && (
                  <p style={{ fontSize: '.78rem', color: 'var(--color-text-tertiary)', marginTop: '.5rem', marginBottom: 0 }}>
                    +{meds.length - 5} more
                  </p>
                )}
              </div>
            )}
        </Section>

        {/* Schedules & Appointments */}
        <Section icon={CalendarDays} title="Schedules & Appointments"
          accentColor="#3b82f6"
          badge={
            <button className="btn btn-primary btn-sm"
              onClick={e => { e.stopPropagation(); navigate('/calendar'); }}
              style={{ padding: '3px 10px', fontSize: '.75rem', display: 'flex', alignItems: 'center', gap: '.3rem' }}>
              <Plus size={12}/> Add New
            </button>
          }>
          {events.length === 0
            ? noData('No appointments or events for this date.')
            : events.map(ev => (
                <div key={ev.id} style={{ display: 'flex', alignItems: 'center', gap: '.5rem',
                  padding: '.35rem 0', borderBottom: '1px solid var(--color-border)', fontSize: '.85rem' }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: ev.color || '#3b82f6',
                    flexShrink: 0 }}/>
                  <span style={{ flex: 1 }}>{ev.title}</span>
                  {ev.start_time && (
                    <span style={{ fontSize: '.75rem', color: 'var(--color-text-tertiary)', fontFamily: 'monospace' }}>
                      {fmtTime(ev.start_time.slice(0,5))}
                    </span>
                  )}
                </div>
              ))}
        </Section>

      </div>
    </div>
  );
}
