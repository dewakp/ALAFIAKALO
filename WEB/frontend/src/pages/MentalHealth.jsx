import { localToday } from '../utils/datetime';
import { useState, useEffect, useRef } from 'react';
import api from '../services/api';
import BackButton from '../components/BackButton';
import { t as translate } from '../i18n';

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

  if (loading) return <div className="page"><p>{translate('MentalHealth.loading_mental_health_data')}</p></div>;

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1>{translate('MentalHealth.mental_health')}</h1>
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
    entry_date: localToday(),
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
        <h2 style={{ margin: 0 }}>{translate('MentalHealth.mood_check_in')}</h2>
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
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.date')}</label>
                <input type="date" value={form.entry_date} onChange={e => setForm({ ...form, entry_date: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} required />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.mood_1_10', { mood_score: moodEmoji(form.mood_score), mood_score2: form.mood_score })}</label>
                <input type="range" min="1" max="10" value={form.mood_score}
                  onChange={e => setForm({ ...form, mood_score: parseInt(e.target.value) })} style={{ width: '100%' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.energy_1_10', { energy_level: form.energy_level })}</label>
                <input type="range" min="1" max="10" value={form.energy_level}
                  onChange={e => setForm({ ...form, energy_level: parseInt(e.target.value) })} style={{ width: '100%' }} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.stress_1_10', { stress_level: form.stress_level })}</label>
                <input type="range" min="1" max="10" value={form.stress_level}
                  onChange={e => setForm({ ...form, stress_level: parseInt(e.target.value) })} style={{ width: '100%' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.anxiety_1_10', { anxiety_level: form.anxiety_level })}</label>
                <input type="range" min="1" max="10" value={form.anxiety_level}
                  onChange={e => setForm({ ...form, anxiety_level: parseInt(e.target.value) })} style={{ width: '100%' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.sleep_quality_1_10', { sleep_quality: form.sleep_quality })}</label>
                <input type="range" min="1" max="10" value={form.sleep_quality}
                  onChange={e => setForm({ ...form, sleep_quality: parseInt(e.target.value) })} style={{ width: '100%' }} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.sleep_hours')}</label>
                <input type="number" step="0.5" value={form.sleep_hours}
                  onChange={e => setForm({ ...form, sleep_hours: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.emotions')}</label>
                <input placeholder={translate('MentalHealth.anxious_happy_frustrated')} value={form.emotions}
                  onChange={e => setForm({ ...form, emotions: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.triggers')}</label>
                <input placeholder={translate('MentalHealth.what_triggered_these_emotions')} value={form.triggers}
                  onChange={e => setForm({ ...form, triggers: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.coping_strategies')}</label>
                <input placeholder={translate('MentalHealth.meditation_exercise_talking')} value={form.coping_strategies}
                  onChange={e => setForm({ ...form, coping_strategies: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.gratitude')}</label>
                <input value={form.gratitude} onChange={e => setForm({ ...form, gratitude: e.target.value })}
                  style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
              </div>
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{translate('MentalHealth.journal_entry')}</label>
              <textarea rows={3} value={form.journal_entry} onChange={e => setForm({ ...form, journal_entry: e.target.value })}
                style={{ width: '100%', padding: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box', resize: 'vertical' }} />
            </div>
            <button type="submit" style={{ padding: '10px 32px', borderRadius: 8, background: 'var(--primary)', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 600 }}>
              {translate('MentalHealth.save_check_in')}
            </button>
          </form>
        </div>
      )}

      {/* Entries table */}
      <div style={{ background: '#fff', border: '1px solid #eee', borderRadius: 12, overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #eee' }}>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>{translate('MentalHealth.date')}</th>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>{translate('MentalHealth.mood')}</th>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>{translate('MentalHealth.energy')}</th>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>{translate('MentalHealth.stress')}</th>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>{translate('MentalHealth.sleep')}</th>
              <th style={{ textAlign: 'left', padding: 10, fontSize: 13 }}>{translate('MentalHealth.journal')}</th>
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
                    {translate('MentalHealth.delete')}
                  </button>
                </td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: 'center', padding: 32, color: '#999' }}>{translate('MentalHealth.no_mood_entries_yet_click_new_check_in')}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
function Dashboard({ stats }) {
  if (!stats) return <p>{translate('MentalHealth.no_data_yet_start_by_logging_your_mood')}</p>;

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
        <div style={{ fontSize: 16, color: '#666' }}>{translate('MentalHealth.wellness_score_0_100')}</div>
      </div>

      {/* Stat Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 16, marginBottom: 32 }}>
        <StatCard label={translate('MentalHealth.avg_mood_7d')} value={avg_mood_7d ? `${avg_mood_7d}/10 ${EMOJI_MAP[Math.round(avg_mood_7d)] || ''}` : '—'} />
        <StatCard label={translate('MentalHealth.mood_trend')} value={mood_trend ? `${trendIcon} ${mood_trend}` : '—'} />
        <StatCard label={translate('MentalHealth.stress_7d')} value={avg_stress_7d ? `${avg_stress_7d}/10` : '—'} color={avg_stress_7d > 6 ? '#f44336' : '#4caf50'} />
        <StatCard label={translate('MentalHealth.anxiety_7d')} value={avg_anxiety_7d ? `${avg_anxiety_7d}/10` : '—'} color={avg_anxiety_7d > 6 ? '#f44336' : '#4caf50'} />
        <StatCard label={translate('MentalHealth.sleep_quality')} value={avg_sleep_quality_7d ? `${avg_sleep_quality_7d}/10` : '—'} />
        <StatCard label={translate('MentalHealth.sleep_hours')} value={avg_sleep_hours_7d ? `${avg_sleep_hours_7d}h` : '—'} />
        <StatCard label={translate('MentalHealth.streak')} value={`${streak_days} days 🔥`} />
        <StatCard label={translate('MentalHealth.entries_30d')} value={total_entries_30d} />
        <StatCard label={translate('MentalHealth.breathing_30d')} value={`${total_breathing_minutes_30d} min`} />
      </div>

      {/* Clinical Assessments Summary */}
      {(latest_phq9_score !== null || latest_gad7_score !== null || latest_who5_score !== null) && (
        <div style={{ background: '#f9f9f9', borderRadius: 12, padding: 20, marginBottom: 24 }}>
          <h3 style={{ marginTop: 0 }}>{translate('MentalHealth.clinical_assessments')}</h3>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            {latest_phq9_score !== null && (
              <div>
                <strong>{translate('MentalHealth.phq_9_depression')}</strong> {latest_phq9_score}/27
                <span style={{ marginLeft: 8, padding: '2px 8px', borderRadius: 4, fontSize: 12,
                  background: SEVERITY_COLORS[latest_phq9_severity] || '#999', color: '#fff' }}>
                  {SEVERITY_LABELS[latest_phq9_severity] || latest_phq9_severity}
                </span>
              </div>
            )}
            {latest_gad7_score !== null && (
              <div>
                <strong>{translate('MentalHealth.gad_7_anxiety')}</strong> {latest_gad7_score}/21
                <span style={{ marginLeft: 8, padding: '2px 8px', borderRadius: 4, fontSize: 12,
                  background: SEVERITY_COLORS[latest_gad7_severity] || '#999', color: '#fff' }}>
                  {SEVERITY_LABELS[latest_gad7_severity] || latest_gad7_severity}
                </span>
              </div>
            )}
            {latest_who5_score !== null && (
              <div><strong>{translate('MentalHealth.who_5_well_being')}</strong> {latest_who5_score}%</div>
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
        session_date: localToday(),
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
        <h2>{translate('MentalHealth.session_complete')}</h2>
        <p>{translate('MentalHealth.how_do_you_feel_now')}</p>
        <label>{translate('MentalHealth.mood_after_1_10')} <input type="range" min={1} max={10} value={moodAfter} onChange={e => setMoodAfter(+e.target.value)} /> {moodAfter}</label>
        <br /><br />
        <button onClick={saveSession} style={{ padding: '12px 32px', borderRadius: 8, background: 'var(--primary)', color: '#fff', border: 'none', fontSize: 16, cursor: 'pointer' }}>
          {translate('MentalHealth.save_session')}
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
        <div style={{ fontSize: 14, color: '#888' }}>{translate('MentalHealth.cycle_of', { cycle, recommended_cycles: active.recommended_cycles })}</div>
        <button onClick={() => { setRunning(false); setActive(null); }} style={{ marginTop: 24, padding: '8px 24px', cursor: 'pointer' }}>{translate('MentalHealth.stop')}</button>
      </div>
    );
  }

  return (
    <div>
      <h2>{translate('MentalHealth.breathing_exercises')}</h2>
      <p style={{ color: '#666', marginBottom: 16 }}>
        {translate('MentalHealth.before_starting_rate_your_current_mood')}
        <input type="range" min={1} max={10} value={moodBefore} onChange={e => setMoodBefore(+e.target.value)} style={{ marginLeft: 8, verticalAlign: 'middle' }} /> {moodBefore}/10
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
        {exercises.map(ex => (
          <div key={ex.id} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 12, padding: 20 }}>
            <h3 style={{ marginTop: 0 }}>{ex.name}</h3>
            <p style={{ color: '#666', fontSize: 14 }}>{ex.description}</p>
            <div style={{ fontSize: 13, color: '#888', marginBottom: 12 }}>
              {translate('MentalHealth.s_in_s_hold_s_out_cycles', { inhale_seconds: ex.inhale_seconds, hold_seconds: ex.hold_seconds, exhale_seconds: ex.exhale_seconds, hold_after_exhale_seconds: ex.hold_after_exhale_seconds > 0 && ` → ${ex.hold_after_exhale_seconds}s hold`, recommended_cycles: ex.recommended_cycles })}
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
              {ex.benefits.map(b => (
                <span key={b} style={{ fontSize: 11, padding: '2px 8px', borderRadius: 12, background: '#e8f5e9', color: '#2e7d32' }}>{b}</span>
              ))}
            </div>
            <button onClick={() => startExercise(ex)} style={{ width: '100%', padding: '10px 0', borderRadius: 8, background: 'var(--primary)', color: '#fff', border: 'none', fontSize: 15, cursor: 'pointer' }}>
              {translate('MentalHealth.start_exercise')}
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
        entry_date: localToday(),
        ...form,
      });
      setForm({ item_1: '', item_2: '', item_3: '', reflection: '' });
      onSave();
    } catch (err) { console.error(err); }
    setSaving(false);
  }

  return (
    <div>
      <h2>{translate('MentalHealth.gratitude_journal')}</h2>
      <form onSubmit={handleSubmit} style={{ background: '#fff', border: '1px solid #eee', borderRadius: 12, padding: 20, marginBottom: 24 }}>
        <p style={{ color: '#666' }}>{translate('MentalHealth.what_are_you_grateful_for_today')}</p>
        <input placeholder={translate('MentalHealth.text_1_i_m_grateful_for')} value={form.item_1} onChange={e => setForm({ ...form, item_1: e.target.value })} required
          style={{ width: '100%', padding: 10, marginBottom: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
        <input placeholder={translate('MentalHealth.text_2_i_m_grateful_for')} value={form.item_2} onChange={e => setForm({ ...form, item_2: e.target.value })}
          style={{ width: '100%', padding: 10, marginBottom: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
        <input placeholder={translate('MentalHealth.text_3_i_m_grateful_for')} value={form.item_3} onChange={e => setForm({ ...form, item_3: e.target.value })}
          style={{ width: '100%', padding: 10, marginBottom: 8, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
        <textarea placeholder={translate('MentalHealth.reflection')} value={form.reflection} onChange={e => setForm({ ...form, reflection: e.target.value })} rows={3}
          style={{ width: '100%', padding: 10, marginBottom: 12, borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box', resize: 'vertical' }} />
        <button type="submit" disabled={saving} style={{ padding: '10px 32px', borderRadius: 8, background: 'var(--primary)', color: '#fff', border: 'none', cursor: 'pointer' }}>
          {saving ? 'Saving...' : 'Save Entry'}
        </button>
      </form>

      {entries.length > 0 && (
        <div>
          <h3>{translate('MentalHealth.recent_entries')}</h3>
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
    { key: 'phq_interest', text: translate('MentalHealth.little_interest_or_pleasure_in_doing') },
    { key: 'phq_feeling_down', text: translate('MentalHealth.feeling_down_depressed_or_hopeless') },
    { key: 'phq_sleep', text: translate('MentalHealth.trouble_falling_staying_asleep_or') },
    { key: 'phq_energy', text: translate('MentalHealth.feeling_tired_or_having_little_energy') },
    { key: 'phq_appetite', text: translate('MentalHealth.poor_appetite_or_overeating') },
    { key: 'phq_self_esteem', text: translate('MentalHealth.feeling_bad_about_yourself') },
    { key: 'phq_concentration', text: translate('MentalHealth.trouble_concentrating') },
    { key: 'phq_psychomotor', text: translate('MentalHealth.moving_or_speaking_slowly_being_fidgety') },
    { key: 'phq_suicidal_ideation', text: translate('MentalHealth.thoughts_of_self_harm') },
  ];
  const GAD7_QUESTIONS = [
    { key: 'gad_nervous', text: translate('MentalHealth.feeling_nervous_anxious_or_on_edge') },
    { key: 'gad_uncontrollable_worry', text: translate('MentalHealth.not_being_able_to_stop_worrying') },
    { key: 'gad_excessive_worry', text: translate('MentalHealth.worrying_too_much_about_different_things') },
    { key: 'gad_trouble_relaxing', text: translate('MentalHealth.trouble_relaxing') },
    { key: 'gad_restless', text: translate('MentalHealth.being_so_restless_that_it_s_hard_to_sit') },
    { key: 'gad_irritable', text: translate('MentalHealth.becoming_easily_annoyed_or_irritable') },
    { key: 'gad_afraid', text: translate('MentalHealth.feeling_afraid_something_awful_might') },
  ];
  const WHO5_QUESTIONS = [
    { key: 'who5_cheerful', text: translate('MentalHealth.i_have_felt_cheerful_and_in_good_spirits') },
    { key: 'who5_calm', text: translate('MentalHealth.i_have_felt_calm_and_relaxed') },
    { key: 'who5_active', text: translate('MentalHealth.i_have_felt_active_and_vigorous') },
    { key: 'who5_rested', text: translate('MentalHealth.i_woke_up_feeling_fresh_and_rested') },
    { key: 'who5_interesting', text: translate('MentalHealth.my_daily_life_has_been_filled_with') },
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
        assessment_date: localToday(),
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
      <h2>{translate('MentalHealth.clinical_assessments')}</h2>
      <p style={{ color: '#666' }}>{translate('MentalHealth.over_the_last_2_weeks_how_often_have_you')}</p>

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
          <h3>{translate('MentalHealth.assessment_history')}</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr style={{ borderBottom: '2px solid #eee' }}>
              <th style={{ textAlign: 'left', padding: 8 }}>{translate('MentalHealth.date')}</th>
              <th style={{ textAlign: 'left', padding: 8 }}>{translate('MentalHealth.type')}</th>
              <th style={{ textAlign: 'left', padding: 8 }}>{translate('MentalHealth.score')}</th>
              <th style={{ textAlign: 'left', padding: 8 }}>{translate('MentalHealth.severity')}</th>
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
