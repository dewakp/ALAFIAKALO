import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import {
  Video, VideoOff, Mic, MicOff, PhoneOff, Phone, Monitor, MonitorOff,
  MessageSquare, Users, Clock, Plus, ChevronLeft, X, Send, Clipboard,
  Shield, Calendar as CalIcon, FileText, AlertCircle, Check, Loader2,
  UserCheck, Settings, Maximize, Minimize,
} from 'lucide-react';
import BackButton from '../components/BackButton';

/* ──────────────────────────── Constants ──────────────────────────── */
const SESSION_TYPES = [
  { key: 'video', label: 'Video', icon: Video, color: '#2196F3' },
  { key: 'voice', label: 'Voice', icon: Phone, color: '#4CAF50' },
  { key: 'chat', label: 'Chat', icon: MessageSquare, color: '#9C27B0' },
];
const STATUS_COLORS = {
  scheduled: '#2196F3', waiting: '#FF9800', in_progress: '#4CAF50',
  completed: '#607D8B', cancelled: '#f44336', no_show: '#795548', rescheduled: '#00BCD4',
};
const PRIORITY_COLORS = { routine: '#9E9E9E', urgent: '#FF9800', emergency: '#f44336' };
const SPECIALTIES = [
  'General Practice', 'Cardiology', 'Dermatology', 'Endocrinology',
  'Gastroenterology', 'Neurology', 'Oncology', 'Orthopedics',
  'Pediatrics', 'Psychiatry', 'Pulmonology', 'Urology',
];

/* ──────────────────────── Utility Helpers ────────────────────────── */
function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('default', { month: 'short', day: 'numeric', year: 'numeric' });
}
function fmtTime(d) {
  if (!d) return '';
  return new Date(d).toLocaleTimeString('default', { hour: '2-digit', minute: '2-digit' });
}
function fmtDateTime(d) {
  if (!d) return '—';
  return `${fmtDate(d)} ${fmtTime(d)}`;
}
function minutesBetween(a, b) {
  if (!a || !b) return null;
  return Math.round((new Date(b) - new Date(a)) / 60000);
}
function statusLabel(s) { return (s || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()); }

/* ════════════════════════════════════════════════════════════════════
   MAIN TELEHEALTH COMPONENT
   ════════════════════════════════════════════════════════════════════ */
export default function Telehealth() {
  const { user } = useAuth();
  const [view, setView] = useState('list');          // list | detail | call | create
  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');       // all | upcoming | past | cancelled

  /* ── Load sessions ── */
  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (filter === 'upcoming') params.status = 'scheduled';
      else if (filter === 'past') params.status = 'completed';
      else if (filter === 'cancelled') params.status = 'cancelled';
      const { data } = await api.get('/telehealth/sessions', { params });
      setSessions(data);
    } catch { /* ignore */ }
    setLoading(false);
  }, [filter]);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  /* ── Navigation helpers ── */
  function openDetail(session) { setActiveSession(session); setView('detail'); }
  function openCall(session) { setActiveSession(session); setView('call'); }
  function backToList() { setActiveSession(null); setView('list'); loadSessions(); }

  /* ── Render ── */
  if (view === 'create') return <SessionForm onBack={backToList} />;
  if (view === 'call' && activeSession) return <VideoCall session={activeSession} user={user} onEnd={backToList} />;
  if (view === 'detail' && activeSession) return (
    <SessionDetail session={activeSession} user={user} onBack={backToList}
      onJoinCall={() => openCall(activeSession)} onReload={loadSessions} />
  );

  /* ── Session List ── */
  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title">Telehealth</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setView('create')}>
          <Plus size={18} /> New Session
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: '1rem' }}>
        {['all', 'upcoming', 'past', 'cancelled'].map(f => (
          <button key={f}
            className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setFilter(f)}
          >{statusLabel(f)}</button>
        ))}
      </div>

      {loading && <div className="card" style={{ textAlign: 'center', padding: '2rem' }}><Loader2 className="spin" size={24} /> Loading…</div>}

      {!loading && sessions.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-secondary)' }}>
          No telehealth sessions found.
          <br />
          <button className="btn btn-primary btn-sm" style={{ marginTop: 8 }} onClick={() => setView('create')}>
            <Plus size={14} /> Schedule Visit
          </button>
        </div>
      )}

      {sessions.map(s => (
        <div key={s.id} className="card" style={{
          marginBottom: '0.75rem', borderLeft: `4px solid ${STATUS_COLORS[s.status] || '#9E9E9E'}`,
          cursor: 'pointer',
        }} onClick={() => openDetail(s)}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              {/* Tags */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
                <span style={{
                  fontSize: '0.7rem', padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                  background: SESSION_TYPES.find(t => t.key === s.session_type)?.color || '#9E9E9E', color: '#fff',
                }}>{statusLabel(s.session_type)}</span>
                <span style={{
                  fontSize: '0.7rem', padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                  background: STATUS_COLORS[s.status] || '#9E9E9E', color: '#fff',
                }}>{statusLabel(s.status)}</span>
                {s.priority && s.priority !== 'routine' && (
                  <span style={{
                    fontSize: '0.7rem', padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                    background: PRIORITY_COLORS[s.priority] || '#9E9E9E', color: '#fff',
                  }}>{statusLabel(s.priority)}</span>
                )}
              </div>

              <div style={{ fontWeight: 600, fontSize: '1rem' }}>
                {s.title || s.reason_for_visit || 'Telehealth Visit'}
              </div>

              <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 4, fontSize: '0.82rem', color: 'var(--color-text-secondary)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                  <CalIcon size={13} /> {fmtDateTime(s.scheduled_start)}
                </span>
                {s.specialty && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                    <Shield size={13} /> {s.specialty}
                  </span>
                )}
                <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                  <Users size={13} /> {s.participants?.length || 0} participant{(s.participants?.length || 0) !== 1 ? 's' : ''}
                </span>
              </div>
            </div>

            {/* Join button for active/waiting sessions */}
            {['scheduled', 'waiting', 'in_progress'].includes(s.status) && (
              <button className="btn btn-primary btn-sm" onClick={e => { e.stopPropagation(); openCall(s); }}
                style={{ whiteSpace: 'nowrap' }}>
                <Video size={14} /> Join
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}


/* ════════════════════════════════════════════════════════════════════
   SESSION CREATION FORM
   ════════════════════════════════════════════════════════════════════ */
function SessionForm({ onBack }) {
  const [form, setForm] = useState({
    session_type: 'video',
    title: '',
    scheduled_start: '',
    scheduled_end: '',
    reason_for_visit: '',
    chief_complaint: '',
    specialty: '',
    priority: 'routine',
    provider_id: '',
    recording_enabled: false,
    transcription_enabled: true,
    chat_enabled: true,
    waiting_room_enabled: true,
  });
  const [submitting, setSubmitting] = useState(false);

  function upd(k, v) { setForm(f => ({ ...f, [k]: v })); }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    const payload = { ...form };
    if (!payload.title) delete payload.title;
    if (!payload.scheduled_end) delete payload.scheduled_end;
    if (!payload.reason_for_visit) delete payload.reason_for_visit;
    if (!payload.chief_complaint) delete payload.chief_complaint;
    if (!payload.specialty) delete payload.specialty;
    if (!payload.provider_id) delete payload.provider_id;
    else payload.provider_id = Number(payload.provider_id);
    try {
      await api.post('/telehealth/sessions', payload);
      onBack();
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error creating session');
    }
    setSubmitting(false);
  }

  return (
    <div>
      <div className="page-header">
        <button className="btn btn-secondary btn-sm" onClick={onBack}><ChevronLeft size={16} /> Back</button>
        <h1 className="page-title" style={{ marginLeft: 12 }}>Schedule Visit</h1>
      </div>

      <form className="card" onSubmit={handleSubmit}>
        {/* Session type */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ fontWeight: 600, display: 'block', marginBottom: 6 }}>Visit Type</label>
          <div style={{ display: 'flex', gap: 8 }}>
            {SESSION_TYPES.map(t => (
              <button type="button" key={t.key}
                className={`btn btn-sm ${form.session_type === t.key ? 'btn-primary' : 'btn-secondary'}`}
                style={form.session_type === t.key ? { background: t.color, borderColor: t.color } : {}}
                onClick={() => upd('session_type', t.key)}>
                <t.icon size={14} /> {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Title */}
        <div className="form-group">
          <label className="form-label">Title (optional)</label>
          <input className="form-input" value={form.title} onChange={e => upd('title', e.target.value)}
            placeholder="e.g. Follow-up consultation" />
        </div>

        {/* Schedule */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="form-group">
            <label className="form-label">Start Date & Time *</label>
            <input className="form-input" type="datetime-local" required
              value={form.scheduled_start} onChange={e => upd('scheduled_start', e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">End Date & Time</label>
            <input className="form-input" type="datetime-local"
              value={form.scheduled_end} onChange={e => upd('scheduled_end', e.target.value)} />
          </div>
        </div>

        {/* Clinical */}
        <div className="form-group">
          <label className="form-label">Reason for Visit</label>
          <input className="form-input" value={form.reason_for_visit} onChange={e => upd('reason_for_visit', e.target.value)}
            placeholder="Brief reason for this visit" />
        </div>
        <div className="form-group">
          <label className="form-label">Chief Complaint</label>
          <textarea className="form-input" rows={2} value={form.chief_complaint}
            onChange={e => upd('chief_complaint', e.target.value)} placeholder="Primary symptoms or concerns" />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="form-group">
            <label className="form-label">Specialty</label>
            <select className="form-input" value={form.specialty} onChange={e => upd('specialty', e.target.value)}>
              <option value="">— Select —</option>
              {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Priority</label>
            <select className="form-input" value={form.priority} onChange={e => upd('priority', e.target.value)}>
              <option value="routine">Routine</option>
              <option value="urgent">Urgent</option>
              <option value="emergency">Emergency</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Provider ID (optional)</label>
          <input className="form-input" type="number" value={form.provider_id}
            onChange={e => upd('provider_id', e.target.value)} placeholder="Assigned provider user ID" />
        </div>

        {/* Feature toggles */}
        <div style={{ marginTop: '0.5rem', marginBottom: '1rem' }}>
          <label style={{ fontWeight: 600, display: 'block', marginBottom: 6 }}>Features</label>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {[
              ['transcription_enabled', 'Live Transcription'],
              ['chat_enabled', 'In-Session Chat'],
              ['recording_enabled', 'Recording'],
              ['waiting_room_enabled', 'Waiting Room'],
            ].map(([k, label]) => (
              <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.9rem', cursor: 'pointer' }}>
                <input type="checkbox" checked={form[k]} onChange={e => upd(k, e.target.checked)} /> {label}
              </label>
            ))}
          </div>
        </div>

        <button className="btn btn-primary" type="submit" disabled={submitting} style={{ width: '100%' }}>
          {submitting ? <><Loader2 className="spin" size={16} /> Scheduling…</> : <><CalIcon size={16} /> Schedule Visit</>}
        </button>
      </form>
    </div>
  );
}


/* ════════════════════════════════════════════════════════════════════
   SESSION DETAIL VIEW
   ════════════════════════════════════════════════════════════════════ */
function SessionDetail({ session: initial, user, onBack, onJoinCall, onReload }) {
  const [session, setSession] = useState(initial);
  const [notes, setNotes] = useState([]);
  const [transcripts, setTranscripts] = useState([]);
  const [noteText, setNoteText] = useState('');
  const [noteType, setNoteType] = useState('general');
  const [tab, setTab] = useState('info');

  useEffect(() => { reload(); }, [session.id]);

  async function reload() {
    try {
      const { data } = await api.get(`/telehealth/sessions/${session.id}`);
      setSession(data);
    } catch { /* ignore */ }
    try {
      const { data } = await api.get(`/telehealth/sessions/${session.id}/notes`);
      setNotes(data);
    } catch { /* ignore */ }
    try {
      const { data } = await api.get(`/telehealth/sessions/${session.id}/transcripts`);
      setTranscripts(data);
    } catch { /* ignore */ }
  }

  async function handleCancel() {
    if (!confirm('Cancel this session?')) return;
    try {
      await api.patch(`/telehealth/sessions/${session.id}`, { status: 'cancelled' });
      reload();
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error');
    }
  }

  async function addNote(e) {
    e.preventDefault();
    if (!noteText.trim()) return;
    try {
      await api.post(`/telehealth/sessions/${session.id}/notes`, { content: noteText, note_type: noteType });
      setNoteText('');
      reload();
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error');
    }
  }

  async function deleteNote(id) {
    if (!confirm('Delete this note?')) return;
    try {
      await api.delete(`/telehealth/sessions/${session.id}/notes/${id}`);
      reload();
    } catch { /* ignore */ }
  }

  const canJoin = ['scheduled', 'waiting', 'in_progress'].includes(session.status);

  return (
    <div>
      <div className="page-header">
        <button className="btn btn-secondary btn-sm" onClick={onBack}><ChevronLeft size={16} /> Back</button>
        <h1 className="page-title" style={{ marginLeft: 12, flex: 1 }}>
          {session.title || session.reason_for_visit || 'Session Details'}
        </h1>
        {canJoin && (
          <button className="btn btn-primary" onClick={onJoinCall}>
            <Video size={16} /> Join Call
          </button>
        )}
      </div>

      {/* Status bar */}
      <div className="card" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: '1rem' }}>
        <span style={{
          padding: '4px 14px', borderRadius: 12, fontWeight: 700, fontSize: '0.8rem',
          background: STATUS_COLORS[session.status] || '#9E9E9E', color: '#fff',
        }}>{statusLabel(session.status)}</span>
        <span style={{
          padding: '4px 12px', borderRadius: 12, fontWeight: 600, fontSize: '0.8rem',
          background: SESSION_TYPES.find(t => t.key === session.session_type)?.color || '#9E9E9E', color: '#fff',
        }}>{statusLabel(session.session_type)}</span>
        {session.priority && (
          <span style={{
            padding: '4px 12px', borderRadius: 12, fontWeight: 600, fontSize: '0.8rem',
            background: PRIORITY_COLORS[session.priority] || '#9E9E9E', color: '#fff',
          }}>{statusLabel(session.priority)}</span>
        )}
        <span style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
          Code: <strong>{session.session_code?.slice(0, 8)}…</strong>
        </span>
        {session.status !== 'cancelled' && session.status !== 'completed' && (
          <button className="btn btn-sm" style={{ marginLeft: 'auto', color: '#f44336', borderColor: '#f44336' }}
            onClick={handleCancel}><X size={14} /> Cancel</button>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: '1rem' }}>
        {['info', 'notes', 'transcripts', 'participants'].map(t => (
          <button key={t} className={`btn btn-sm ${tab === t ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setTab(t)}>{statusLabel(t)}</button>
        ))}
      </div>

      {/* Tab: Info */}
      {tab === 'info' && (
        <div className="card">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>Scheduled Start</div>
              <div style={{ fontWeight: 600 }}>{fmtDateTime(session.scheduled_start)}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>Scheduled End</div>
              <div style={{ fontWeight: 600 }}>{fmtDateTime(session.scheduled_end)}</div>
            </div>
            {session.actual_start && <div>
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>Actual Start</div>
              <div style={{ fontWeight: 600 }}>{fmtDateTime(session.actual_start)}</div>
            </div>}
            {session.actual_end && <div>
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>Actual End</div>
              <div style={{ fontWeight: 600 }}>{fmtDateTime(session.actual_end)}</div>
            </div>}
            {session.duration_minutes != null && <div>
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>Duration</div>
              <div style={{ fontWeight: 600 }}>{session.duration_minutes} min</div>
            </div>}
            {session.specialty && <div>
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>Specialty</div>
              <div style={{ fontWeight: 600 }}>{session.specialty}</div>
            </div>}
            {session.reason_for_visit && <div style={{ gridColumn: '1 / -1' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>Reason for Visit</div>
              <div style={{ fontWeight: 600 }}>{session.reason_for_visit}</div>
            </div>}
            {session.chief_complaint && <div style={{ gridColumn: '1 / -1' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>Chief Complaint</div>
              <div style={{ fontWeight: 600 }}>{session.chief_complaint}</div>
            </div>}
          </div>
          {/* Follow-up */}
          {session.follow_up_needed && (
            <div style={{ marginTop: 16, padding: 12, background: 'var(--color-primary-light)', borderRadius: 8 }}>
              <strong>Follow-up Needed</strong>
              {session.follow_up_date && <span> — {fmtDate(session.follow_up_date)}</span>}
              {session.follow_up_notes && <div style={{ fontSize: '0.85rem', marginTop: 4 }}>{session.follow_up_notes}</div>}
            </div>
          )}
        </div>
      )}

      {/* Tab: Notes */}
      {tab === 'notes' && (
        <div>
          <form className="card" onSubmit={addNote} style={{ marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <select className="form-input" style={{ width: 'auto' }} value={noteType}
                onChange={e => setNoteType(e.target.value)}>
                {['general', 'subjective', 'objective', 'assessment', 'plan', 'follow_up'].map(t => (
                  <option key={t} value={t}>{statusLabel(t)}</option>
                ))}
              </select>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <textarea className="form-input" rows={2} value={noteText}
                onChange={e => setNoteText(e.target.value)} placeholder="Add a clinical note…" style={{ flex: 1 }} />
              <button className="btn btn-primary" type="submit"><Send size={16} /></button>
            </div>
          </form>
          {notes.length === 0 && (
            <div className="card" style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: '1.5rem' }}>
              No notes yet.
            </div>
          )}
          {notes.map(n => (
            <div key={n.id} className="card" style={{ marginBottom: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <span style={{
                  fontSize: '0.7rem', padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                  background: '#e3f2fd', color: '#1565c0',
                }}>{statusLabel(n.note_type)}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>{fmtDateTime(n.created_at)}</span>
                  <button className="btn btn-sm" style={{ color: '#f44336', padding: 2 }}
                    onClick={() => deleteNote(n.id)}><X size={14} /></button>
                </div>
              </div>
              <div style={{ whiteSpace: 'pre-wrap' }}>{n.content}</div>
              {n.diagnosis_codes && <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginTop: 4 }}>ICD: {n.diagnosis_codes}</div>}
              {n.procedure_codes && <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>CPT: {n.procedure_codes}</div>}
            </div>
          ))}
        </div>
      )}

      {/* Tab: Transcripts */}
      {tab === 'transcripts' && (
        <div>
          {transcripts.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: '1.5rem' }}>
              No transcripts recorded.
            </div>
          ) : (
            <div className="card" style={{ maxHeight: 400, overflowY: 'auto' }}>
              {transcripts.map(t => (
                <div key={t.id} style={{ marginBottom: 10, padding: '6px 0', borderBottom: '1px solid var(--color-border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
                    <span>Speaker #{t.speaker_id || '?'}</span>
                    <span>{t.confidence != null ? `${(t.confidence * 100).toFixed(0)}%` : ''}</span>
                  </div>
                  <div style={{ fontSize: '0.9rem' }}>{t.reviewed_content || t.content}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab: Participants */}
      {tab === 'participants' && (
        <div>
          {(session.participants || []).length === 0 ? (
            <div className="card" style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: '1.5rem' }}>
              No participants.
            </div>
          ) : (
            session.participants.map(p => (
              <div key={p.id} className="card" style={{ marginBottom: '0.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontWeight: 600 }}>User #{p.user_id}</div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)' }}>
                    {statusLabel(p.role)} — {statusLabel(p.status)}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  {p.camera_enabled ? <Video size={16} color="#4CAF50" /> : <VideoOff size={16} color="#9E9E9E" />}
                  {p.microphone_enabled ? <Mic size={16} color="#4CAF50" /> : <MicOff size={16} color="#9E9E9E" />}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}


/* ════════════════════════════════════════════════════════════════════
   VIDEO CALL — Full WebRTC with signaling, chat, transcription
   ════════════════════════════════════════════════════════════════════ */
function VideoCall({ session, user, onEnd }) {
  /* ── State ── */
  const [callState, setCallState] = useState('connecting');  // connecting | waiting | active | ended
  const [cameraOn, setCameraOn] = useState(true);
  const [micOn, setMicOn] = useState(true);
  const [screenShare, setScreenShare] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [transcripts, setTranscripts] = useState([]);
  const [peers, setPeers] = useState([]);
  const [fullscreen, setFullscreen] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [rtcConfig, setRtcConfig] = useState(null);

  /* ── Refs ── */
  const localVideoRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const localStreamRef = useRef(null);
  const screenStreamRef = useRef(null);
  const pcRef = useRef(null);
  const wsRef = useRef(null);
  const chatWsRef = useRef(null);
  const timerRef = useRef(null);
  const chatEndRef = useRef(null);

  /* ── Initialize call ── */
  useEffect(() => {
    initCall();
    return () => cleanup();
  }, []);

  /* ── Timer ── */
  useEffect(() => {
    if (callState === 'active') {
      timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000);
    }
    return () => clearInterval(timerRef.current);
  }, [callState]);

  /* Auto-scroll chat */
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  async function initCall() {
    try {
      // 1. Join the session
      try {
        await api.patch(`/telehealth/sessions/${session.id}/join`);
      } catch { /* may already be joined */ }

      // 2. Start the session if scheduled
      if (session.status === 'scheduled') {
        try { await api.patch(`/telehealth/sessions/${session.id}/start`); } catch { /* ignore */ }
      }

      // 3. Get RTC config
      const { data: config } = await api.get(`/telehealth/sessions/${session.id}/rtc-config`);
      setRtcConfig(config);

      // 4. Get local media
      const isVideo = session.session_type === 'video';
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: isVideo ? { width: 1280, height: 720, facingMode: 'user' } : false,
      });
      localStreamRef.current = stream;
      if (localVideoRef.current) localVideoRef.current.srcObject = stream;

      // 5. Create peer connection
      const pc = new RTCPeerConnection({
        iceServers: config.ice_servers.map(s => ({
          urls: s.urls,
          username: s.username || undefined,
          credential: s.credential || undefined,
        })),
      });
      pcRef.current = pc;

      // Add local tracks
      stream.getTracks().forEach(track => pc.addTrack(track, stream));

      // Handle remote tracks
      pc.ontrack = (event) => {
        if (remoteVideoRef.current && event.streams[0]) {
          remoteVideoRef.current.srcObject = event.streams[0];
        }
      };

      // 6. Connect WebSocket for signaling
      const token = localStorage.getItem('token');
      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${wsProto}//${window.location.host}/ws/telehealth/${config.session_code}?token=${token}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setCallState(session.waiting_room_enabled ? 'waiting' : 'active');
      };

      ws.onmessage = async (event) => {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
          case 'peers':
            setPeers(msg.peers || []);
            // If there are existing peers, create an offer
            if (msg.peers?.length > 0) {
              const offer = await pc.createOffer();
              await pc.setLocalDescription(offer);
              ws.send(JSON.stringify({ type: 'offer', payload: JSON.stringify(offer) }));
            }
            break;

          case 'offer': {
            const offer = JSON.parse(msg.payload);
            await pc.setRemoteDescription(new RTCSessionDescription(offer));
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            ws.send(JSON.stringify({ type: 'answer', payload: JSON.stringify(answer), to_user_id: msg.from_user_id }));
            setCallState('active');
            break;
          }

          case 'answer': {
            const answer = JSON.parse(msg.payload);
            await pc.setRemoteDescription(new RTCSessionDescription(answer));
            setCallState('active');
            break;
          }

          case 'ice_candidate': {
            const candidate = JSON.parse(msg.payload);
            await pc.addIceCandidate(new RTCIceCandidate(candidate));
            break;
          }

          case 'peer_joined':
            setPeers(prev => [...prev, msg.user_id]);
            break;

          case 'peer_left':
            setPeers(prev => prev.filter(id => id !== msg.user_id));
            break;
        }
      };

      ws.onclose = () => {
        if (callState !== 'ended') setCallState('ended');
      };

      // ICE candidate handling
      pc.onicecandidate = (event) => {
        if (event.candidate && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'ice_candidate',
            payload: JSON.stringify(event.candidate),
          }));
        }
      };

      // 7. Connect chat WebSocket
      if (session.chat_enabled) {
        const chatWsUrl = `${wsProto}//${window.location.host}/ws/telehealth/${config.session_code}/chat?token=${token}`;
        const chatWs = new WebSocket(chatWsUrl);
        chatWsRef.current = chatWs;

        chatWs.onmessage = (event) => {
          const msg = JSON.parse(event.data);
          if (msg.type === 'chat') {
            setChatMessages(prev => [...prev, {
              id: Date.now(),
              user_id: msg.user_id,
              content: msg.content,
              timestamp: msg.timestamp,
              isMine: msg.user_id === user.id,
            }]);
          } else if (msg.type === 'transcription') {
            setTranscripts(prev => [...prev, {
              id: Date.now(),
              speaker_id: msg.speaker_id,
              content: msg.content,
              timestamp: msg.timestamp,
            }]);
          }
        };
      }

    } catch (err) {
      console.error('Call init error:', err);
      setCallState('ended');
    }
  }

  function cleanup() {
    clearInterval(timerRef.current);
    localStreamRef.current?.getTracks().forEach(t => t.stop());
    screenStreamRef.current?.getTracks().forEach(t => t.stop());
    pcRef.current?.close();
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.close();
    if (chatWsRef.current?.readyState === WebSocket.OPEN) chatWsRef.current.close();
  }

  async function endCall() {
    try { await api.patch(`/telehealth/sessions/${session.id}/end`); } catch { /* ignore */ }
    try { await api.patch(`/telehealth/sessions/${session.id}/leave`); } catch { /* ignore */ }
    cleanup();
    setCallState('ended');
    onEnd();
  }

  function toggleCamera() {
    const track = localStreamRef.current?.getVideoTracks()[0];
    if (track) { track.enabled = !track.enabled; setCameraOn(track.enabled); }
  }

  function toggleMic() {
    const track = localStreamRef.current?.getAudioTracks()[0];
    if (track) { track.enabled = !track.enabled; setMicOn(track.enabled); }
  }

  async function toggleScreenShare() {
    if (!screenShare) {
      try {
        const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
        screenStreamRef.current = stream;
        const sender = pcRef.current?.getSenders().find(s => s.track?.kind === 'video');
        if (sender) sender.replaceTrack(stream.getVideoTracks()[0]);
        stream.getVideoTracks()[0].onended = () => {
          const localTrack = localStreamRef.current?.getVideoTracks()[0];
          if (sender && localTrack) sender.replaceTrack(localTrack);
          setScreenShare(false);
        };
        setScreenShare(true);
      } catch { /* user cancelled */ }
    } else {
      screenStreamRef.current?.getTracks().forEach(t => t.stop());
      const sender = pcRef.current?.getSenders().find(s => s.track?.kind === 'video');
      const localTrack = localStreamRef.current?.getVideoTracks()[0];
      if (sender && localTrack) sender.replaceTrack(localTrack);
      setScreenShare(false);
    }
  }

  function sendChat(e) {
    e.preventDefault();
    if (!chatInput.trim() || chatWsRef.current?.readyState !== WebSocket.OPEN) return;
    chatWsRef.current.send(JSON.stringify({ type: 'chat', content: chatInput }));
    setChatMessages(prev => [...prev, {
      id: Date.now(),
      user_id: user.id,
      content: chatInput,
      timestamp: new Date().toISOString(),
      isMine: true,
    }]);
    setChatInput('');
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
      setFullscreen(true);
    } else {
      document.exitFullscreen();
      setFullscreen(false);
    }
  }

  const elapsedStr = `${String(Math.floor(elapsed / 60)).padStart(2, '0')}:${String(elapsed % 60).padStart(2, '0')}`;
  const isVideo = session.session_type === 'video';

  /* ── Render ── */
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: '#1a1a2e', color: '#fff', display: 'flex', flexDirection: 'column',
    }}>
      {/* Top bar */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 16px', background: 'rgba(0,0,0,0.4)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontWeight: 700, fontSize: '1rem' }}>
            {session.title || 'Telehealth Call'}
          </span>
          <span style={{
            padding: '2px 10px', borderRadius: 10, fontSize: '0.75rem', fontWeight: 600,
            background: callState === 'active' ? '#4CAF50' : callState === 'waiting' ? '#FF9800' : '#f44336',
          }}>{callState === 'active' ? 'Live' : callState === 'waiting' ? 'Waiting Room' : 'Connecting…'}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontFamily: 'monospace', fontSize: '1rem' }}><Clock size={14} /> {elapsedStr}</span>
          <span style={{ fontSize: '0.8rem', opacity: 0.7 }}><Users size={14} /> {peers.length + 1}</span>
        </div>
      </div>

      {/* Video area */}
      <div style={{ flex: 1, display: 'flex', position: 'relative', overflow: 'hidden' }}>
        {/* Remote video (main) */}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
          {isVideo ? (
            <video ref={remoteVideoRef} autoPlay playsInline
              style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }} />
          ) : (
            <div style={{ textAlign: 'center' }}>
              <Phone size={64} style={{ opacity: 0.3 }} />
              <div style={{ marginTop: 12, fontSize: '1.2rem', opacity: 0.7 }}>Voice Call</div>
              <div style={{ marginTop: 4, fontFamily: 'monospace', fontSize: '1.5rem' }}>{elapsedStr}</div>
            </div>
          )}

          {/* Waiting room overlay */}
          {callState === 'waiting' && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              background: 'rgba(0,0,0,0.7)', zIndex: 5,
            }}>
              <Loader2 className="spin" size={48} style={{ marginBottom: 16 }} />
              <div style={{ fontSize: '1.3rem', fontWeight: 600, marginBottom: 8 }}>Waiting Room</div>
              <div style={{ opacity: 0.7 }}>Please wait while the provider admits you to the session.</div>
            </div>
          )}
        </div>

        {/* Local video (PIP) */}
        {isVideo && (
          <div style={{
            position: 'absolute', bottom: 80, right: 16, width: 200, height: 150,
            borderRadius: 12, overflow: 'hidden', border: '2px solid rgba(255,255,255,0.3)',
            background: '#000', zIndex: 10,
          }}>
            <video ref={localVideoRef} autoPlay playsInline muted
              style={{ width: '100%', height: '100%', objectFit: 'cover', transform: 'scaleX(-1)' }} />
            {!cameraOn && (
              <div style={{
                position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'rgba(0,0,0,0.8)',
              }}>
                <VideoOff size={32} style={{ opacity: 0.5 }} />
              </div>
            )}
          </div>
        )}

        {/* Chat panel */}
        {chatOpen && (
          <div style={{
            width: 320, background: 'rgba(0,0,0,0.6)', display: 'flex', flexDirection: 'column',
            borderLeft: '1px solid rgba(255,255,255,0.1)',
          }}>
            <div style={{ padding: '8px 12px', fontWeight: 600, borderBottom: '1px solid rgba(255,255,255,0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Chat</span>
              <button onClick={() => setChatOpen(false)} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer' }}>
                <X size={16} />
              </button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '8px 12px' }}>
              {chatMessages.map(m => (
                <div key={m.id} style={{
                  marginBottom: 8,
                  textAlign: m.isMine ? 'right' : 'left',
                }}>
                  <div style={{
                    display: 'inline-block', padding: '6px 12px', borderRadius: 12, maxWidth: '85%',
                    background: m.isMine ? 'var(--color-primary)' : 'rgba(255,255,255,0.15)',
                    fontSize: '0.85rem',
                  }}>
                    {!m.isMine && <div style={{ fontSize: '0.7rem', opacity: 0.7, marginBottom: 2 }}>User #{m.user_id}</div>}
                    {m.content}
                  </div>
                  <div style={{ fontSize: '0.65rem', opacity: 0.5, marginTop: 2 }}>
                    {fmtTime(m.timestamp)}
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>
            <form onSubmit={sendChat} style={{ display: 'flex', gap: 6, padding: '8px 12px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
              <input value={chatInput} onChange={e => setChatInput(e.target.value)}
                placeholder="Type a message…"
                style={{
                  flex: 1, padding: '6px 12px', borderRadius: 20, border: '1px solid rgba(255,255,255,0.2)',
                  background: 'rgba(255,255,255,0.1)', color: '#fff', fontSize: '0.85rem', outline: 'none',
                }} />
              <button type="submit" style={{
                background: 'var(--color-primary)', border: 'none', borderRadius: '50%',
                width: 34, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center',
                cursor: 'pointer', color: '#fff',
              }}><Send size={14} /></button>
            </form>
          </div>
        )}

        {/* Live transcription overlay */}
        {session.transcription_enabled && transcripts.length > 0 && (
          <div style={{
            position: 'absolute', bottom: 80, left: 16, right: chatOpen ? 340 : 230,
            maxHeight: 120, overflowY: 'auto', background: 'rgba(0,0,0,0.6)',
            borderRadius: 8, padding: '6px 12px', fontSize: '0.82rem', zIndex: 8,
          }}>
            {transcripts.slice(-5).map(t => (
              <div key={t.id} style={{ marginBottom: 4 }}>
                <span style={{ opacity: 0.6, fontSize: '0.7rem' }}>Speaker #{t.speaker_id}: </span>
                {t.content}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bottom controls */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12,
        padding: '12px 16px', background: 'rgba(0,0,0,0.5)',
      }}>
        {/* Camera toggle (video only) */}
        {isVideo && (
          <ControlBtn active={cameraOn} onClick={toggleCamera}
            icon={cameraOn ? <Video size={20} /> : <VideoOff size={20} />}
            label={cameraOn ? 'Camera On' : 'Camera Off'} />
        )}

        {/* Mic toggle */}
        <ControlBtn active={micOn} onClick={toggleMic}
          icon={micOn ? <Mic size={20} /> : <MicOff size={20} />}
          label={micOn ? 'Mic On' : 'Mic Off'} />

        {/* Screen share (video only) */}
        {isVideo && session.screen_sharing_enabled && (
          <ControlBtn active={screenShare} onClick={toggleScreenShare}
            icon={screenShare ? <MonitorOff size={20} /> : <Monitor size={20} />}
            label={screenShare ? 'Stop Share' : 'Share Screen'} color={screenShare ? '#4CAF50' : undefined} />
        )}

        {/* Chat */}
        {session.chat_enabled && (
          <ControlBtn active={chatOpen} onClick={() => setChatOpen(!chatOpen)}
            icon={<MessageSquare size={20} />}
            label="Chat" color={chatOpen ? '#2196F3' : undefined} />
        )}

        {/* Fullscreen */}
        <ControlBtn onClick={toggleFullscreen}
          icon={fullscreen ? <Minimize size={20} /> : <Maximize size={20} />}
          label={fullscreen ? 'Exit Fullscreen' : 'Fullscreen'} />

        {/* End call */}
        <button onClick={endCall} style={{
          background: '#f44336', color: '#fff', border: 'none', borderRadius: '50%',
          width: 56, height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center',
          cursor: 'pointer', boxShadow: '0 2px 8px rgba(244,67,54,0.4)',
        }} title="End Call">
          <PhoneOff size={24} />
        </button>
      </div>
    </div>
  );
}

/* ── Call control button ── */
function ControlBtn({ active, onClick, icon, label, color }) {
  return (
    <button onClick={onClick} title={label} style={{
      background: color || (active ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.08)'),
      color: '#fff', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '50%',
      width: 48, height: 48, display: 'flex', alignItems: 'center', justifyContent: 'center',
      cursor: 'pointer', transition: 'background 0.2s',
    }}>
      {icon}
    </button>
  );
}
