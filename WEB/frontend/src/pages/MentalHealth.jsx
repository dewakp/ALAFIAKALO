import { useState, useEffect, useRef } from 'react';
import api from '../services/api';
import BackButton from '../components/BackButton';

const EMOJI_MAP = { 1: '😢', 2: '😢', 3: '😔', 4: '😔', 5: '😐', 6: '😐', 7: '🙂', 8: '🙂', 9: '😄', 10: '😄' };
const SEVERITY_COLORS = { minimal: '#4caf50', mild: '#8bc34a', moderate: '#ff9800', moderately_severe: '#f44336', severe: '#b71c1c', good: '#4caf50', low: '#ff9800', very_low: '#f44336' };
const SEVERITY_LABELS = { minimal: 'Minimal', mild: 'Mild', moderate: 'Moderate', moderately_severe: 'Moderately Severe', severe: 'Severe', good: 'Good', low: 'Low', very_low: 'Very Low' };

export default function MentalHealth() {
  const [tab, setTab] = useState('dashboard');
  const [stats, setStats] = useState(null);
  const [exercises, setExercises] = useState([]);
  const [gratitudes, setGratitudes] = useState([]);
  const [assessments, setAssessments] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadAll(); }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [s, e, g, a] = await Promise.all([
        api.get('/mental-health/stats'),
        api.get('/mental-health/breathing/exercises'),
        api.get('/mental-health/gratitude'),
        api.get('/mental-health/assessments'),
      ]);
      setStats(s.data);
      setExercises(e.data);
      setGratitudes(g.data);
      setAssessments(a.data);
    } catch (err) { console.error(err); }
    setLoading(false);
  }

  if (loading) return <div className="page"><p>Loading mental health data...</p></div>;

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1>🧠 Mental Health</h1>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {['dashboard', 'mood', 'breathing', 'gratitude', 'assessments'].map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{ padding: '8px 20px', borderRadius: 8, border: tab === t ? '2px solid var(--primary)' : '1px solid #ddd',
              background: tab === t ? 'var(--primary)' : '#fff', color: tab === t ? '#fff' : '#333',
              fontWeight: tab === t ? 700 : 400, cursor: 'pointer', textTransform: 'capitalize' }}>
            {t === 'mood' ? '😊 Mood Check-In' : t === 'breathing' ? '🫁 Breathing' : t === 'gratitude' ? '🙏 Gratitude' : t === 'assessments' ? '📋 Assessments' : '📊 Dashboard'}
          </button>
        ))}
      </div>

      {tab === 'dashboard' && <Dashboard stats={stats} />}
      {tab === 'mood' && <MoodTab />}
      {tab === 'breathing' && <BreathingTab exercises={exercises} onComplete={loadAll} />}
      {tab === 'gratitude' && <GratitudeTab entries={gratitudes} onSave={loadAll} />}
      {tab === 'assessments' && <AssessmentTab assessments={assessments} onSave={loadAll} />}
    </div>
  );
}

// ─── Dashboard ──────────────────────────────────────────────────────
// ─── Mood Check-In ───────────────────────────────────────────────────

function MoodTab() {
  const [entries, setEntries] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    entry_date: new Date().toISOString().split('T')[0],
    mood_score: 5, energy_level: 5, stress_level: 5, anxiety_level: 5, sleep_quality: 5,
    sleep_hours: '', emotions: '', triggers: '', coping_strategies: '', journal_entry: '', gratitude: '',
  });

  useEffect(() => { loadEntries(); }, []);

  async function loadEntries() {
    try {
      const { data } = await api.get('/mood/');
      setEntries(data);
    } catch (err) { console.error(err); }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const payload = { ...form };
    payload.sleep_hours = payload.sleep_hours ? parseFloat(payload.sleep_hours) : null;
    payload.emotions = payload.emotions || null;
    payload.triggers = payload.triggers || null;
    payload.coping_strategies = payload.coping_strategies || null;
    try {
      await api.post('/mood/', payload);
      setShowForm(false);
      loadEntries();
    } catch (err) { console.error(err); }
  }

  async function handleDelete(id) {
    try {
      await api.delete(`/mood/${id}`);
      loadEntries();
    } catch (err) { console.error(err); }
  }

  const moodEmoji = (score) => {
    if (score >= 8) return '😄';
    if (score >= 6) return '🙂';
    if (score >= 4) return '😐';
    if (score >= 2) return '😔';
    return '😢';
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>😊 Mood Check-In</h2>
        <button onClick={() => setShowForm(!showForm)}
          style={{ padding: '8px 20px', borderRadius: 8, background: 'var(--primary)', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 600 }}>
          {showForm ? 'Cancel' : '+ New Check-In'}
        </button>
      </div>

      {showForm && (
        <div style={{ background: '#fff', border: '1px solid #eee', borderRadius: 12, padding: 20, marginBottom: 20 }}>
          <form onSubmit={handleSubmit}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Date</label>
                <input type="date" value={form.entry_date} onChange={e => setForm({ ...form, entry_date: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} required />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Mood (1-10): {moodEmoji(form.mood_score)} {form.mood_score}</label>
                <input type="range" min="1" max="10" value={form.mood_score}
                  onChange={e => setForm({ ...form, mood_score: parseInt(e.target.value) })} style={{ width: '100%' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Energy (1-10): {form.energy_level}</label>
                <input type="range" min="1" max="10" value={form.energy_level}
                  onChange={e => setForm({ ...form, energy_level: parseInt(e.target.value) })} style={{ width: '100%' }} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Stress (1-10): {form.stress_level}</label>
                <input type="range" min="1" max="10" value={form.stress_level}
                  onChange={e => setForm({ ...form, stress_level: parseInt(e.target.value) })} style={{ width: '100%' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Anxiety (1-10): {form.anxiety_level}</label>
                <input type="range" min="1" max="10" value={form.anxiety_level}
                  onChange={e => setForm({ ...form, anxiety_level: parseInt(e.target.value) })} style={{ width: '100%' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Sleep Quality (1-10): {form.sleep_quality}</label>
                <input type="range" min="1" max="10" value={form.sleep_quality}
                  onChange={e => setForm({ ...form, sleep_quality: parseInt(e.target.value) })} style={{ width: '100%' }} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Sleep Hours</label>
                <input type="number" step="0.5" value={form.sleep_hours}
                  onChange={e => setForm({ ...form, sleep_hours: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Emotions</label>
                <input placeholder="anxious, happy, frustrated..." value={form.emotions}
                  onChange={e => setForm({ ...form, emotions: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Triggers</label>
                <input placeholder="What triggered these emotions?" value={form.triggers}
                  onChange={e => setForm({ ...form, triggers: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Coping Strategies</label>
                <input placeholder="meditation, exercise, talking..." value={form.coping_strategies}
                  onChange={e => setForm({ ...form, coping_strategies: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Gratitude</label>
                <input value={form.gratitude} onChange={e => setForm({ ...form, gratitude: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
              </div>
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Journal Entry</label>
              <textarea rows={3} value={form.journal_entry} onChange={e => setForm({ ...form, journal_entry: e.target.value })}
                style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box', resize: 'vertical' }} />
            </div>
            <button type="submit" style={{ padding: '10px 32px', borderRadius: 8, background: 'var(--primary)', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 600 }}>
              Save Check-In
            </button>
          </form>
        </div>
      )}

      {/* Entries table */}
      <div style={{ background: '#fff', border: '1px solid #eee', borderRadius: 12, overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #eee' }}>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>Date</th>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>Mood</th>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>Energy</th>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>Stress</th>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>Sleep</th>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>Journal</th>
              <th style={{ padding: 10 }}></th>
            </tr>
          </thead>
          <tbody>
            {entries.map(e => (
              <tr key={e.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <td style={{ padding: 10, fontSize: 13 }}>{e.entry_date}</td>
                <td style={{ padding: 10, fontSize: 13 }}>{moodEmoji(e.mood_score)} {e.mood_score}/10</td>
                <td style={{ padding: 10, fontSize: 13 }}>{e.energy_level ?? '-'}/10</td>
                <td style={{ padding: 10, fontSize: 13 }}>{e.stress_level ?? '-'}/10</td>
                <td style={{ padding: 10, fontSize: 13 }}>{e.sleep_hours ? `${e.sleep_hours}h` : '-'}</td>
                <td style={{ padding: 10, fontSize: 13, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {e.journal_entry || '-'}
                </td>
                <td style={{ padding: 10 }}>
                  <button onClick={() => handleDelete(e.id)}
                    style={{ padding: '4px 12px', borderRadius: 6, background: '#fee2e2', color: '#ef4444', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: 'center', padding: 32, color: '#999' }}>No mood entries yet. Click "+ New Check-In" to log your first entry.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
function Dashboard({ stats }) {
  if (!stats) return <p>No data yet. Start by logging your mood!</p>;

  const { wellness_score, avg_mood_7d, avg_stress_7d, avg_anxiety_7d, avg_sleep_quality_7d,
    avg_sleep_hours_7d, mood_trend, total_entries_30d, streak_days,
    total_breathing_minutes_30d, latest_phq9_score, latest_phq9_severity,
    latest_gad7_score, latest_gad7_severity, latest_who5_score } = stats;

  const trendIcon = mood_trend === 'improving' ? '📈' : mood_trend === 'declining' ? '📉' : '➡️';

  return (
    <div>
      {/* Wellness Score */}
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <div style={{ fontSize: 64, fontWeight: 800, color: wellness_score >= 70 ? '#4caf50' : wellness_score >= 40 ? '#ff9800' : '#f44336' }}>
          {wellness_score ?? '—'}
        </div>
        <div style={{ fontSize: 16, color: '#666' }}>Wellness Score (0–100)</div>
      </div>

      {/* Stat Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 16, marginBottom: 32 }}>
        <StatCard label="Avg Mood (7d)" value={avg_mood_7d ? `${avg_mood_7d}/10 ${EMOJI_MAP[Math.round(avg_mood_7d)] || ''}` : '—'} />
        <StatCard label="Mood Trend" value={mood_trend ? `${trendIcon} ${mood_trend}` : '—'} />
        <StatCard label="Stress (7d)" value={avg_stress_7d ? `${avg_stress_7d}/10` : '—'} color={avg_stress_7d > 6 ? '#f44336' : '#4caf50'} />
        <StatCard label="Anxiety (7d)" value={avg_anxiety_7d ? `${avg_anxiety_7d}/10` : '—'} color={avg_anxiety_7d > 6 ? '#f44336' : '#4caf50'} />
        <StatCard label="Sleep Quality" value={avg_sleep_quality_7d ? `${avg_sleep_quality_7d}/10` : '—'} />
        <StatCard label="Sleep Hours" value={avg_sleep_hours_7d ? `${avg_sleep_hours_7d}h` : '—'} />
        <StatCard label="Streak" value={`${streak_days} days 🔥`} />
        <StatCard label="Entries (30d)" value={total_entries_30d} />
        <StatCard label="Breathing (30d)" value={`${total_breathing_minutes_30d} min`} />
      </div>

      {/* Clinical Assessments Summary */}
      {(latest_phq9_score !== null || latest_gad7_score !== null || latest_who5_score !== null) && (
        <div style={{ background: '#f9f9f9', borderRadius: 12, padding: 20, marginBottom: 24 }}>
          <h3 style={{ marginTop: 0 }}>📋 Clinical Assessments</h3>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            {latest_phq9_score !== null && (
              <div>
                <strong>PHQ-9 (Depression):</strong> {latest_phq9_score}/27
                <span style={{ marginLeft: 8, padding: '2px 8px', borderRadius: 4, fontSize: 12,
                  background: SEVERITY_COLORS[latest_phq9_severity] || '#999', color: '#fff' }}>
                  {SEVERITY_LABELS[latest_phq9_severity] || latest_phq9_severity}
                </span>
              </div>
            )}
            {latest_gad7_score !== null && (
              <div>
                <strong>GAD-7 (Anxiety):</strong> {latest_gad7_score}/21
                <span style={{ marginLeft: 8, padding: '2px 8px', borderRadius: 4, fontSize: 12,
                  background: SEVERITY_COLORS[latest_gad7_severity] || '#999', color: '#fff' }}>
                  {SEVERITY_LABELS[latest_gad7_severity] || latest_gad7_severity}
                </span>
              </div>
            )}
            {latest_who5_score !== null && (
              <div><strong>WHO-5 Well-Being:</strong> {latest_who5_score}%</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{ background: '#fff', border: '1px solid #eee', borderRadius: 12, padding: 16, textAlign: 'center' }}>
      <div style={{ fontSize: 24, fontWeight: 700, color: color || 'var(--primary)' }}>{value}</div>
      <div style={{ fontSize: 13, color: '#888', marginTop: 4 }}>{label}</div>
    </div>
  );
}

// ─── Breathing Exercises ─────────────────────────────────────────────

function BreathingTab({ exercises, onComplete }) {
  const [active, setActive] = useState(null);
  const [phase, setPhase] = useState(null); // inhale, hold, exhale, hold2
  const [cycle, setCycle] = useState(0);
  const [timer, setTimer] = useState(0);
  const [running, setRunning] = useState(false);
  const [moodBefore, setMoodBefore] = useState(5);
  const [moodAfter, setMoodAfter] = useState(5);
  const [done, setDone] = useState(false);
  const intervalRef = useRef(null);
  const startTimeRef = useRef(null);

  function startExercise(ex) {
    setActive(ex);
    setPhase('inhale');
    setCycle(1);
    setTimer(ex.inhale_seconds);
    setRunning(true);
    setDone(false);
    startTimeRef.current = Date.now();
  }

  useEffect(() => {
    if (!running || !active) return;
    intervalRef.current = setInterval(() => {
      setTimer(prev => {
        if (prev <= 1) {
          // Move to next phase
          setPhase(p => {
            if (p === 'inhale') { setTimer(active.hold_seconds || 1); return active.hold_seconds ? 'hold' : 'exhale'; }
            if (p === 'hold') { setTimer(active.exhale_seconds); return 'exhale'; }
            if (p === 'exhale') {
              if (active.hold_after_exhale_seconds) { setTimer(active.hold_after_exhale_seconds); return 'hold2'; }
              setCycle(c => {
                if (c >= active.recommended_cycles) { setRunning(false); setDone(true); return c; }
                setTimer(active.inhale_seconds);
                return c + 1;
              });
              return 'inhale';
            }
            if (p === 'hold2') {
              setCycle(c => {
                if (c >= active.recommended_cycles) { setRunning(false); setDone(true); return c; }
                setTimer(active.inhale_seconds);
                return c + 1;
              });
              return 'inhale';
            }
            return p;
          });
          return prev;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(intervalRef.current);
  }, [running, active]);

  async function saveSession() {
    const duration = Math.round((Date.now() - startTimeRef.current) / 1000);
    try {
      await api.post('/mental-health/breathing/sessions', {
        session_date: new Date().toISOString().split('T')[0],
        exercise_type: active.id,
        duration_seconds: duration,
        mood_before: moodBefore,
        mood_after: moodAfter,
      });
      setActive(null); setDone(false);
      onComplete();
    } catch (err) { console.error(err); }
  }

  const PHASE_COLORS = { inhale: '#4caf50', hold: '#2196f3', exhale: '#ff9800', hold2: '#9c27b0' };
  const PHASE_LABELS = { inhale: 'Breathe In', hold: 'Hold', exhale: 'Breathe Out', hold2: 'Hold' };

  if (done && active) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <h2>✅ Session Complete!</h2>
        <p>How do you feel now?</p>
        <label>Mood After (1-10): <input type="range" min={1} max={10} value={moodAfter} onChange={e => setMoodAfter(+e.target.value)} /> {moodAfter}</label>
        <br /><br />
        <button onClick={saveSession} style={{ padding: '12px 32px', borderRadius: 8, background: 'var(--primary)', color: '#fff', border: 'none', fontSize: 16, cursor: 'pointer' }}>
          Save Session
        </button>
      </div>
    );
  }

  if (active && running) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <h2>{active.name}</h2>
        <div style={{ fontSize: 80, fontWeight: 800, color: PHASE_COLORS[phase], transition: 'color 0.5s' }}>{timer}</div>
        <div style={{ fontSize: 24, fontWeight: 600, marginBottom: 16 }}>{PHASE_LABELS[phase]}</div>
        <div style={{ fontSize: 14, color: '#888' }}>Cycle {cycle} of {active.recommended_cycles}</div>
        <button onClick={() => { setRunning(false); setActive(null); }} style={{ marginTop: 24, padding: '8px 24px', cursor: 'pointer' }}>Stop</button>
      </div>
    );
  }

  return (
    <div>
      <h2>🫁 Breathing Exercises</h2>
      <p style={{ color: '#666', marginBottom: 16 }}>
        Before starting, rate your current mood:
        <input type="range" min={1} max={10} value={moodBefore} onChange={e => setMoodBefore(+e.target.value)} style={{ marginLeft: 8, verticalAlign: 'middle' }} /> {moodBefore}/10
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
        {exercises.map(ex => (
          <div key={ex.id} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 12, padding: 20 }}>
            <h3 style={{ marginTop: 0 }}>{ex.name}</h3>
            <p style={{ color: '#666', fontSize: 14 }}>{ex.description}</p>
            <div style={{ fontSize: 13, color: '#888', marginBottom: 12 }}>
              {ex.inhale_seconds}s in → {ex.hold_seconds}s hold → {ex.exhale_seconds}s out
              {ex.hold_after_exhale_seconds > 0 && ` → ${ex.hold_after_exhale_seconds}s hold`}
              {' · '}{ex.recommended_cycles} cycles
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
              {ex.benefits.map(b => (
                <span key={b} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, background: '#e8f5e9', color: '#2e7d32' }}>{b}</span>
              ))}
            </div>
            <button onClick={() => startExercise(ex)} style={{ width: '100%', padding: '10px 0', borderRadius: 8, background: 'var(--primary)', color: '#fff', border: 'none', fontSize: 15, cursor: 'pointer' }}>
              Start Exercise
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Gratitude Journal ───────────────────────────────────────────────

function GratitudeTab({ entries, onSave }) {
  const [form, setForm] = useState({ item_1: '', item_2: '', item_3: '', reflection: '' });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.item_1.trim()) return;
    setSaving(true);
    try {
      await api.post('/mental-health/gratitude', {
        entry_date: new Date().toISOString().split('T')[0],
        ...form,
      });
      setForm({ item_1: '', item_2: '', item_3: '', reflection: '' });
      onSave();
    } catch (err) { console.error(err); }
    setSaving(false);
  }

  return (
    <div>
      <h2>🙏 Gratitude Journal</h2>
      <form onSubmit={handleSubmit} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 12, padding: 20, marginBottom: 24 }}>
        <p style={{ color: '#666' }}>What are you grateful for today?</p>
        <input placeholder="1. I'm grateful for..." value={form.item_1} onChange={e => setForm({ ...form, item_1: e.target.value })} required
          style={{ width: '100%', padding: 10, marginBottom: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
        <input placeholder="2. I'm grateful for..." value={form.item_2} onChange={e => setForm({ ...form, item_2: e.target.value })}
          style={{ width: '100%', padding: 10, marginBottom: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
        <input placeholder="3. I'm grateful for..." value={form.item_3} onChange={e => setForm({ ...form, item_3: e.target.value })}
          style={{ width: '100%', padding: 10, marginBottom: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
        <textarea placeholder="Reflection..." value={form.reflection} onChange={e => setForm({ ...form, reflection: e.target.value })} rows={3}
          style={{ width: '100%', padding: 10, marginBottom: 12, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box', resize: 'vertical' }} />
        <button type="submit" disabled={saving} style={{ padding: '10px 32px', borderRadius: 8, background: 'var(--primary)', color: '#fff', border: 'none', cursor: 'pointer' }}>
          {saving ? 'Saving...' : 'Save Entry'}
        </button>
      </form>

      {entries.length > 0 && (
        <div>
          <h3>Recent Entries</h3>
          {entries.map(e => (
            <div key={e.id} style={{ background: '#fffde7', borderRadius: 12, padding: 16, marginBottom: 12, borderLeft: '4px solid #ffc107' }}>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 8 }}>{e.entry_date}</div>
              <div>1. {e.item_1}</div>
              {e.item_2 && <div>2. {e.item_2}</div>}
              {e.item_3 && <div>3. {e.item_3}</div>}
              {e.reflection && <div style={{ marginTop: 8, fontStyle: 'italic', color: '#555' }}>{e.reflection}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Clinical Assessments ────────────────────────────────────────────

function AssessmentTab({ assessments, onSave }) {
  const [type, setType] = useState('phq9');
  const [answers, setAnswers] = useState({});
  const [saving, setSaving] = useState(false);

  const PHQ9_QUESTIONS = [
    { key: 'phq_interest', text: 'Little interest or pleasure in doing things' },
    { key: 'phq_feeling_down', text: 'Feeling down, depressed, or hopeless' },
    { key: 'phq_sleep', text: 'Trouble falling/staying asleep, or sleeping too much' },
    { key: 'phq_energy', text: 'Feeling tired or having little energy' },
    { key: 'phq_appetite', text: 'Poor appetite or overeating' },
    { key: 'phq_self_esteem', text: 'Feeling bad about yourself' },
    { key: 'phq_concentration', text: 'Trouble concentrating' },
    { key: 'phq_psychomotor', text: 'Moving or speaking slowly / being fidgety' },
    { key: 'phq_suicidal_ideation', text: 'Thoughts of self-harm' },
  ];
  const GAD7_QUESTIONS = [
    { key: 'gad_nervous', text: 'Feeling nervous, anxious, or on edge' },
    { key: 'gad_uncontrollable_worry', text: 'Not being able to stop worrying' },
    { key: 'gad_excessive_worry', text: 'Worrying too much about different things' },
    { key: 'gad_trouble_relaxing', text: 'Trouble relaxing' },
    { key: 'gad_restless', text: 'Being so restless that it\'s hard to sit still' },
    { key: 'gad_irritable', text: 'Becoming easily annoyed or irritable' },
    { key: 'gad_afraid', text: 'Feeling afraid something awful might happen' },
  ];
  const WHO5_QUESTIONS = [
    { key: 'who5_cheerful', text: 'I have felt cheerful and in good spirits' },
    { key: 'who5_calm', text: 'I have felt calm and relaxed' },
    { key: 'who5_active', text: 'I have felt active and vigorous' },
    { key: 'who5_rested', text: 'I woke up feeling fresh and rested' },
    { key: 'who5_interesting', text: 'My daily life has been filled with things that interest me' },
  ];

  const OPTIONS_03 = ['Not at all (0)', 'Several days (1)', 'More than half (2)', 'Nearly every day (3)'];
  const OPTIONS_05 = ['At no time (0)', 'Some of the time (1)', 'Less than half (2)', 'More than half (3)', 'Most of the time (4)', 'All of the time (5)'];

  const questions = type === 'phq9' ? PHQ9_QUESTIONS : type === 'gad7' ? GAD7_QUESTIONS : WHO5_QUESTIONS;
  const options = type === 'who5' ? OPTIONS_05 : OPTIONS_03;

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/mental-health/assessments', {
        assessment_date: new Date().toISOString().split('T')[0],
        assessment_type: type,
        ...answers,
      });
      setAnswers({});
      onSave();
    } catch (err) { console.error(err); }
    setSaving(false);
  }

  return (
    <div>
      <h2>📋 Clinical Assessments</h2>
      <p style={{ color: '#666' }}>Over the last 2 weeks, how often have you been bothered by the following?</p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {[['phq9', 'PHQ-9 (Depression)'], ['gad7', 'GAD-7 (Anxiety)'], ['who5', 'WHO-5 (Well-Being)']].map(([k, l]) => (
          <button key={k} onClick={() => { setType(k); setAnswers({}); }}
            style={{ padding: '8px 16px', borderRadius: 8, border: type === k ? '2px solid var(--primary)' : '1px solid #ddd',
              background: type === k ? 'var(--primary)' : '#fff', color: type === k ? '#fff' : '#333', cursor: 'pointer' }}>
            {l}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 12, padding: 20, marginBottom: 24 }}>
        {questions.map((q, i) => (
          <div key={q.key} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: '1px solid #f0f0f0' }}>
            <div style={{ fontWeight: 500, marginBottom: 8 }}>{i + 1}. {q.text}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {options.map((opt, val) => (
                <label key={val} style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer', padding: '4px 12px',
                  borderRadius: 6, background: answers[q.key] === val ? 'var(--primary)' : '#f5f5f5',
                  color: answers[q.key] === val ? '#fff' : '#333', fontSize: 13 }}>
                  <input type="radio" name={q.key} value={val} checked={answers[q.key] === val}
                    onChange={() => setAnswers({ ...answers, [q.key]: val })} style={{ display: 'none' }} />
                  {opt}
                </label>
              ))}
            </div>
          </div>
        ))}
        <button type="submit" disabled={saving} style={{ padding: '12px 32px', borderRadius: 8, background: 'var(--primary)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: 16 }}>
          {saving ? 'Submitting...' : 'Submit Assessment'}
        </button>
      </form>

      {assessments.length > 0 && (
        <div>
          <h3>Assessment History</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr style={{ borderBottom: '2px solid #eee' }}>
              <th style={{ textAlign: 'left', padding: 8 }}>Date</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Type</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Score</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Severity</th>
            </tr></thead>
            <tbody>
              {assessments.map(a => (
                <tr key={a.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                  <td style={{ padding: 8 }}>{a.assessment_date}</td>
                  <td style={{ padding: 8, textTransform: 'uppercase' }}>{a.assessment_type}</td>
                  <td style={{ padding: 8 }}>{a.total_score}</td>
                  <td style={{ padding: 8 }}>
                    <span style={{ padding: '2px 10px', borderRadius: 4, fontSize: 12,
                      background: SEVERITY_COLORS[a.severity] || '#999', color: '#fff' }}>
                      {SEVERITY_LABELS[a.severity] || a.severity}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
