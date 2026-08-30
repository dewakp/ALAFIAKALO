import { localToday, toDateInput } from '../utils/datetime';
import { useState, useEffect, useCallback } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { ChevronLeft, ChevronRight, Plus, Trash2, Save, BookOpen, Smile } from 'lucide-react';
import BackButton from '../components/BackButton';
import { usePromptPrefill } from '../hooks/usePromptPrefill';

const todayStr = () => localToday();
const fmtDate = (d) => new Date(d + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
const shiftDay = (d, n) => { const dt = new Date(d + 'T12:00:00'); dt.setDate(dt.getDate() + n); return toDateInput(dt); };

const MOOD_LABELS = { 1: 'Very Low', 2: 'Low', 3: 'Below Average', 4: 'Slightly Low', 5: 'Neutral', 6: 'Slightly Good', 7: 'Good', 8: 'Very Good', 9: 'Excellent', 10: 'Outstanding' };
const MOOD_COLOR = (s) => s >= 8 ? '#22c55e' : s >= 6 ? '#3b82f6' : s >= 4 ? '#f59e0b' : '#ef4444';

// The slider's resting position is NEUTRAL, not 7/10 "Good". An entry nobody
// scored should read as the middle of the scale — claiming a good day on the
// patient's behalf is what made "exhausted and fatigued" come out as Good.
const EMPTY = { entry_date: todayStr(), mood_score: 5, energy_level: '', notes: '', tags: '' };

export default function Journal() {
  const navigate = useNavigate();
  const [selDate, setSelDate] = useState(todayStr());
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY, entry_date: todayStr() });
  // Whether the number came from the person or from a default nobody chose.
  // The form used to pre-fill 7/10 — "Good" — and save that for anyone who
  // wrote their entry without dragging the slider, so "exhausted and fatigued"
  // was filed as Good. A default is not a measurement.
  const [moodTouched, setMoodTouched] = useState(false);
  const [moodSuggestion, setMoodSuggestion] = useState(null);  // { mood_score, rationale, available }
  const [suggestingMood, setSuggestingMood] = useState(false);

  /* Ask the model to read the entry and propose a score. It only ever
     proposes: the number lands on the slider with the reason beside it and the
     user still presses save, so a wrong read is visible instead of silent. */
  const suggestMood = async () => {
    const notes = form.notes.trim();
    if (!notes || suggestingMood) return;
    setSuggestingMood(true);
    try {
      const { data } = await api.post('/mood/suggest-score', { notes });
      setMoodSuggestion(data);
      if (data.available && data.mood_score) {
        setForm(prev => ({
          ...prev,
          mood_score: data.mood_score,
          energy_level: prev.energy_level || (data.energy_level ?? ''),
        }));
      }
    } catch {
      // Unreachable is not a score. Say so and leave the slider to the user.
      setMoodSuggestion({ available: false,
        rationale: 'Scoring is unavailable right now — set the slider yourself.' });
    } finally {
      setSuggestingMood(false);
    }
  };
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (d) => {
    setLoading(true);
    try {
      const { data } = await api.get('/mood/', { params: { start_date: d, end_date: d } });
      setEntries(data);
    } catch { setEntries([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(selDate); }, [load, selDate]);

  function changeDate(n) {
    const nd = shiftDay(selDate, n);
    if (nd > todayStr()) return; // no future
    setSelDate(nd);
    setShowForm(false);
    resetMoodProvenance();
  }

  function openForm() {
    setForm({ ...EMPTY, entry_date: selDate });
    resetMoodProvenance();
    setShowForm(true);
  }

  /* A new entry starts with no score and no explanation of one. Carrying the
     last entry's suggestion forward would attach yesterday's reasoning to
     today's words. */
  function resetMoodProvenance() {
    setMoodTouched(false);
    setMoodSuggestion(null);
  }

  // Prompt Hub hand-off: open a new journal entry pre-filled with the prompt text.
  usePromptPrefill((prefill) => {
    setForm({ ...EMPTY, entry_date: selDate, notes: prefill.text || prefill.notes || '' });
    resetMoodProvenance();
    setShowForm(true);
  });

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...form };
      if (!payload.energy_level) delete payload.energy_level;
      if (!payload.tags) delete payload.tags;
      await api.post('/mood/', payload);
      setShowForm(false);
      load(selDate);
    } catch (err) {
      alert(apiErrorMessage(err, 'Error saving entry'));
    } finally { setSaving(false); }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this journal entry?')) return;
    await api.delete(`/mood/${id}`);
    load(selDate);
  }

  const isToday = selDate === todayStr();

  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title"><BookOpen size={22} style={{ marginRight: '.4rem', verticalAlign: 'middle' }}/>Journal</h1>
        </div>
        <button className="btn btn-primary" onClick={openForm}>
          <Plus size={16}/> New Entry
        </button>
      </div>

      {/* ── Date navigator ── */}
      <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', padding: '.6rem 1rem' }}>
        <button className="btn btn-secondary btn-sm" onClick={() => changeDate(-1)}>
          <ChevronLeft size={16}/>
        </button>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontWeight: 700, fontSize: '1rem' }}>{fmtDate(selDate)}</div>
          {isToday && <div style={{ fontSize: '.72rem', color: 'var(--color-primary)', fontWeight: 600 }}>Today</div>}
        </div>
        <button className="btn btn-secondary btn-sm" onClick={() => changeDate(1)} disabled={isToday}>
          <ChevronRight size={16}/>
        </button>
      </div>

      {/* ── Add entry form ── */}
      {showForm && (
        <div className="card" style={{ marginBottom: '1rem', border: '2px solid var(--color-primary)' }}>
          <h3 style={{ margin: '0 0 .75rem 0', fontSize: '.95rem', fontWeight: 700 }}>
            <Smile size={16} style={{ marginRight: '.3rem', verticalAlign: 'middle', color: 'var(--color-primary)' }}/>
            New Journal Entry
          </h3>
          <form onSubmit={handleSave}>
            <div style={{ marginBottom: '.75rem' }}>
              <label style={{ fontSize: '.82rem', fontWeight: 600, display: 'block', marginBottom: '.25rem' }}>
                How are you feeling? ({form.mood_score}/10 — {MOOD_LABELS[form.mood_score] || ''})
              </label>
              <input type="range" min="1" max="10" value={form.mood_score}
                onChange={e => { setMoodTouched(true); setMoodSuggestion(null);
                                 setForm({ ...form, mood_score: Number(e.target.value) }); }}
                style={{ width: '100%', accentColor: MOOD_COLOR(form.mood_score) }}/>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '.68rem', color: 'var(--color-text-tertiary)' }}>
                <span>1 — Very Low</span><span>10 — Outstanding</span>
              </div>
              {/* Provenance: say where the number came from, always. */}
              {moodSuggestion?.available && moodSuggestion.mood_score ? (
                <div style={{ fontSize: '.72rem', color: 'var(--color-text-secondary)', marginTop: '.35rem' }}>
                  Read from what you wrote: <strong>{moodSuggestion.mood_score}/10</strong>
                  {moodSuggestion.rationale ? ` — ${moodSuggestion.rationale}` : ''}
                  {' '}Drag the slider if that is not right.
                </div>
              ) : moodSuggestion && !moodSuggestion.available ? (
                <div style={{ fontSize: '.72rem', color: '#f59e0b', marginTop: '.35rem' }}>
                  {moodSuggestion.rationale}
                </div>
              ) : !moodTouched && (
                <div style={{ fontSize: '.72rem', color: 'var(--color-text-tertiary)', marginTop: '.35rem' }}>
                  Neutral by default — write below and this is scored from your
                  own words, or drag the slider.
                </div>
              )}
            </div>
            <div style={{ marginBottom: '.75rem' }}>
              <label style={{ fontSize: '.82rem', fontWeight: 600, display: 'block', marginBottom: '.25rem' }}>Energy Level (1–10)</label>
              <input type="number" min="1" max="10" className="form-input"
                value={form.energy_level}
                onChange={e => setForm({ ...form, energy_level: e.target.value })}
                style={{ maxWidth: 100 }} placeholder="optional"/>
            </div>
            <div style={{ marginBottom: '.75rem' }}>
              <label style={{ fontSize: '.82rem', fontWeight: 600, display: 'block', marginBottom: '.25rem' }}>Write your thoughts…</label>
              <textarea className="form-input" rows={5} value={form.notes}
                onChange={e => setForm({ ...form, notes: e.target.value })}
                onBlur={() => { if (!moodTouched) suggestMood(); }}
                placeholder="How was your day? Any symptoms, reflections, or things you're grateful for?"
                style={{ resize: 'vertical', fontFamily: 'inherit' }}/>
              {form.notes.trim() && (
                <button type="button" onClick={suggestMood} disabled={suggestingMood}
                  style={{ marginTop: '.35rem', background: 'none', border: 'none', padding: 0,
                           cursor: 'pointer', color: 'var(--color-primary)', fontSize: '.72rem', fontWeight: 600 }}>
                  {suggestingMood ? 'Reading your entry…' : 'Score this from what I wrote'}
                </button>
              )}
            </div>
            <div style={{ marginBottom: '.75rem' }}>
              <label style={{ fontSize: '.82rem', fontWeight: 600, display: 'block', marginBottom: '.25rem' }}>Tags (comma-separated, optional)</label>
              <input className="form-input" value={form.tags}
                onChange={e => setForm({ ...form, tags: e.target.value })}
                placeholder="e.g. fatigue, dialysis, pain"/>
            </div>
            <div style={{ display: 'flex', gap: '.5rem' }}>
              <button type="submit" className="btn btn-primary" disabled={saving}>
                <Save size={14}/> {saving ? 'Saving…' : 'Save Entry'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* ── Entries ── */}
      {loading && <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-tertiary)' }}>Loading…</div>}

      {!loading && entries.length === 0 && !showForm && (
        <div className="card" style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--color-text-secondary)' }}>
          <BookOpen size={36} style={{ marginBottom: '.75rem', opacity: 0.35 }}/>
          <p style={{ margin: 0 }}>No journal entries for this day.</p>
          <button className="btn btn-primary btn-sm" style={{ marginTop: '.75rem' }} onClick={openForm}>
            <Plus size={14}/> Write something
          </button>
        </div>
      )}

      {entries.map(entry => (
        <div key={entry.id} className="card" style={{ marginBottom: '.75rem',
          borderLeft: `4px solid ${MOOD_COLOR(entry.mood_score)}` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem', marginBottom: '.4rem' }}>
                <span style={{ fontWeight: 800, fontSize: '1.4rem', color: MOOD_COLOR(entry.mood_score) }}>
                  {entry.mood_score}/10
                </span>
                <span style={{ fontSize: '.82rem', color: MOOD_COLOR(entry.mood_score), fontWeight: 600 }}>
                  {MOOD_LABELS[entry.mood_score] || ''}
                </span>
                {entry.energy_level && (
                  <span style={{ fontSize: '.78rem', color: 'var(--color-text-tertiary)', marginLeft: '.5rem' }}>
                    ⚡ Energy: {entry.energy_level}/10
                  </span>
                )}
              </div>
              {entry.notes && (
                <p style={{ margin: '0 0 .5rem 0', fontSize: '.9rem', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                  {entry.notes}
                </p>
              )}
              {entry.tags && entry.tags.length > 0 && (
                <div style={{ display: 'flex', gap: '.3rem', flexWrap: 'wrap' }}>
                  {(typeof entry.tags === 'string' ? entry.tags.split(',') : entry.tags).map((t, i) => (
                    <span key={i} style={{ fontSize: '.7rem', padding: '2px 8px', borderRadius: 10,
                      background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)' }}>
                      {t.trim()}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <button className="btn btn-danger btn-sm" style={{ flexShrink: 0, marginLeft: '.5rem' }}
              onClick={() => handleDelete(entry.id)}>
              <Trash2 size={13}/>
            </button>
          </div>
        </div>
      ))}

      <div style={{ textAlign: 'center', marginTop: '1.5rem' }}>
        <button className="btn btn-secondary btn-sm" onClick={() => navigate('/mental-health')}
          style={{ fontSize: '.8rem' }}>
          View full Mental Health dashboard →
        </button>
      </div>
    </div>
  );
}
