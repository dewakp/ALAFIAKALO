import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import api, { ensureCsrfToken, refreshAccessToken } from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Send, RefreshCw, ChevronDown, ChevronRight, Mic, MicOff } from 'lucide-react';
import BackButton from '../components/BackButton';
import AssistantMarkdown from '../components/AssistantMarkdown';
import ChatStatus from '../components/ChatStatus';

const REGION_ORDER = ['africa', 'middle_east', 'south_asia', 'europe', 'north_america'];
const REGION_LABELS = {
  africa: '🌍 Africa',
  middle_east: '🕌 Middle East',
  south_asia: '🕉 South Asia',
  europe: '🏰 Europe',
  north_america: '🗽 North America',
};

// The persona roster is backend-owned (AI stays server-driven — no named guides
// baked into the app). If /ai/personas can't be reached, fall back to a single
// neutral assistant so chat still works; cultural guides render only when fetched.
const FALLBACK_PERSONAS = [
  { key: 'general_practitioner', title: 'Assistant', origin: '', region: 'specialist', greeting: 'Welcome', icon: '🩺', description: 'Your personal health guide.' },
];

function groupByRegion(personas) {
  const map = {};
  personas.forEach((p) => {
    const r = p.region || 'other';
    if (!map[r]) map[r] = [];
    map[r].push(p);
  });
  return REGION_ORDER.filter((r) => map[r]?.length).map((r) => ({ region: r, label: REGION_LABELS[r] || r, items: map[r] }));
}

export default function AIChat() {
  const [allPersonas, setAllPersonas] = useState([]);
  const [specialists, setSpecialists] = useState([]);
  const [selectedPersona, setSelectedPersona] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  // What the server is doing right now. The tool rounds take tens of seconds and
  // cannot stream, so without this the patient watches a blinking cursor. Every
  // value here is REPORTED by the backend — never a guessed sequence.
  const [status, setStatus] = useState(null);
  const [showCultural, setShowCultural] = useState(false);
  const messagesEndRef = useRef(null);
  const lastUserRef = useRef(null);
  const { state } = useLocation();
  const autoAskHandled = useRef(false);

  // Voice input (speak your question to the agent)
  const [recording, setRecording] = useState(false);
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  // Number of user turns — drives the "anchor the question to the top" scroll.
  const userTurnCount = messages.reduce((n, m) => n + (m.role === 'user' ? 1 : 0), 0);
  const lastUserIndex = messages.map((m) => m.role).lastIndexOf('user');

  useEffect(() => {
    api.get('/ai/personas')
      .then(({ data }) => {
        setAllPersonas(data);
        setSpecialists(data.filter((p) => p.region === 'specialist'));
      })
      .catch(() => {
        setAllPersonas(FALLBACK_PERSONAS);
        setSpecialists(FALLBACK_PERSONAS);
      });
  }, []);

  // When a new question is asked, bring THAT question to the top of the view so the
  // streamed answer flows beneath it — instead of jumping to the bottom of a long reply
  // and burying what was asked (the "disappearing prompt" complaint).
  useEffect(() => {
    if (lastUserRef.current) {
      lastUserRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userTurnCount]);

  // Prompt Hub hand-off: a general health question arrives here as autoAsk. Skip
  // the persona picker, default to the general practitioner, and answer it.
  useEffect(() => {
    if (autoAskHandled.current || !state?.autoAsk || !allPersonas.length) return;
    autoAskHandled.current = true;
    const gp =
      allPersonas.find((p) => p.key === 'general_practitioner') ||
      FALLBACK_PERSONAS.find((p) => p.key === 'general_practitioner');
    if (!gp) return;
    setSelectedPersona(gp);
    setMessages([]);
    sendMessage(state.autoAsk, gp, []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, allPersonas]);

  function pickPersona(persona) {
    setSelectedPersona(persona);
    // Opening line comes from the backend (persona.opening) so the AI's voice is
    // server-controlled; only fall back to a neutral generic if absent.
    const intro = persona.opening || 'Welcome — how can I help with your health today?';
    setMessages([{ role: 'assistant', content: intro }]);
  }

  function handleSend(e) {
    e.preventDefault();
    if (!input.trim() || loading || !selectedPersona) return;
    const userMessage = input.trim();
    setInput('');
    sendMessage(userMessage, selectedPersona, messages);
  }

  // ── Voice input ─────────────────────────────────────────────────
  // Prefer the browser's on-device Web Speech API; fall back to recording +
  // the server Whisper endpoint (/ai/voice). A finished transcript is sent
  // straight to the agent as the next question.
  function handleVoiceResult(transcript) {
    const t = (transcript || '').trim();
    if (!t || !selectedPersona) return;
    setInput('');
    sendMessage(t, selectedPersona, messages);
  }

  function toggleRecording() {
    if (recording) {
      recognitionRef.current?.stop();
      mediaRecorderRef.current?.stop();
      return;
    }
    if (loading || !selectedPersona) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition || null;
    if (SR) {
      try {
        const recognition = new SR();
        recognition.lang = 'en-US';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.onresult = (event) => handleVoiceResult(event.results?.[0]?.[0]?.transcript || '');
        recognition.onerror = () => setRecording(false);
        recognition.onend = () => setRecording(false);
        recognitionRef.current = recognition;
        recognition.start();
        setRecording(true);
      } catch {
        startServerRecording();
      }
    } else {
      startServerRecording();
    }
  }

  async function startServerRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        try {
          const form = new FormData();
          form.append('file', new Blob(chunksRef.current, { type: 'audio/webm' }), 'note.webm');
          form.append('task', 'transcribe');
          const { data } = await api.post('/ai/voice', form, {
            headers: { 'Content-Type': 'multipart/form-data' },
            timeout: 180000,
          });
          handleVoiceResult(data.transcript || data.text || '');
        } catch { /* transcription unavailable — user can type instead */ }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch { /* mic permission denied / unavailable — user can type instead */ }
  }

  // Stop any in-flight capture when leaving the chat.
  useEffect(() => () => {
    recognitionRef.current?.stop();
    mediaRecorderRef.current?.stop();
  }, []);

  async function sendMessage(userMessage, persona, baseMessages) {
    if (!userMessage.trim() || !persona) return;

    const updatedMessages = [...baseMessages, { role: 'user', content: userMessage }];
    setMessages(updatedMessages);
    setLoading(true);
    setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

    const history = updatedMessages.map((m) => ({ role: m.role, content: m.content }));
    const requestBody = JSON.stringify({
      query: userMessage,
      messages: history,
      persona: persona.key,
    });

    async function sendStreamRequest(accessToken) {
      const csrfToken = await ensureCsrfToken();
      return fetch('/api/v1/ai/chat/stream', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
          'X-CSRF-Token': csrfToken,
          // This fetch bypasses the axios interceptor, so it sets the header
          // itself — the chat is the surface where "today" matters most.
          ...(Intl.DateTimeFormat().resolvedOptions().timeZone
            ? { 'X-Client-Timezone': Intl.DateTimeFormat().resolvedOptions().timeZone }
            : {}),
        },
        body: requestBody,
      });
    }

    async function getResponseError(response) {
      try {
        const data = await response.json();
        if (data?.detail) return apiErrorMessage({ response: { data } }, `HTTP ${response.status}`);
      } catch {
        // Non-JSON errors fall through to the status text.
      }
      return response.statusText || `HTTP ${response.status}`;
    }

    try {
      let token = localStorage.getItem('token');
      let res = await sendStreamRequest(token);

      if (res.status === 401) {
        token = await refreshAccessToken();
        res = await sendStreamRequest(token);
      }

      if (!res.ok) throw new Error(await getResponseError(res));

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (payload === '[DONE]') break;
          try {
            const { content, error, status: step, retract } = JSON.parse(payload);
            if (step) setStatus(step);
            if (retract) {
              // That text came from a round that turned out to be a data fetch,
              // not the answer — the model narrates before calling a tool. Drop
              // exactly what the server took back, or its preamble is spliced
              // onto the front of the real answer.
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                next[next.length - 1] = {
                  ...last,
                  content: last.content.slice(0, Math.max(0, last.content.length - retract)),
                };
                return next;
              });
            }
            if (error) {
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = { role: 'assistant', content: `⚠️ ${error}` };
                return next;
              });
              break;
            }
            if (content) {
              setStatus(null);
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = {
                  role: 'assistant',
                  content: (next[next.length - 1].content || '') + content,
                };
                return next;
              });
            }
          } catch {
            // malformed chunk — skip
          }
        }
      }
    } catch (error) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: 'assistant', content: error.message || 'Sorry, something went wrong. Please try again.' };
        return next;
      });
    } finally {
      setLoading(false);
      setStatus(null);
    }
  }

  // ── Persona / Agent picker ──────────────────────────────────────
  if (!selectedPersona) {
    const culturalPersonas = allPersonas.filter((p) => p.region !== 'specialist');
    const displaySpecialists = specialists.length ? specialists : FALLBACK_PERSONAS;
    const culturalGroups = groupByRegion(culturalPersonas.length ? culturalPersonas : []);

    return (
      <div className="chat-container">
        <div className="page-header">
          <div className="page-header-left">
            <BackButton />
            <h1 className="page-title">AI Health Assistant</h1>
          </div>
          <p style={{ color: 'var(--text-secondary)', marginTop: 4 }}>
            Choose a specialist agent or a cultural health guide
          </p>
        </div>

        <div style={{ maxWidth: 600, margin: '0 auto' }}>

          {/* ── Specialist Agents ── */}
          <div style={{ marginBottom: 32 }}>
            <h3 style={{ marginBottom: 4, fontSize: '1rem', color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: 8 }}>
              🏥 Specialist Agents
            </h3>
            <p style={{ marginBottom: 12, fontSize: '.8rem', color: 'var(--text-secondary)' }}>
              Clinically-trained agents that read your full health record and answer from their specialty
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
              {displaySpecialists.map((p) => (
                <button
                  key={p.key}
                  className="card"
                  onClick={() => pickPersona(p)}
                  style={{
                    cursor: 'pointer',
                    textAlign: 'left',
                    border: '2px solid var(--primary)',
                    borderRadius: 10,
                    padding: '14px 16px',
                    transition: 'background .15s, transform .1s',
                    background: 'var(--surface)',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--primary-light, #e8f4fd)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--surface)'; e.currentTarget.style.transform = ''; }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                    <span style={{ fontSize: '1.6rem', lineHeight: 1 }}>{p.icon || '🩺'}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <strong style={{ fontSize: '.95rem' }}>{p.title}</strong>
                        {p.specialty && (
                          <span style={{
                            fontSize: '.65rem', padding: '1px 7px', borderRadius: 10,
                            background: 'var(--primary)', color: '#fff', fontWeight: 600,
                            textTransform: 'uppercase', letterSpacing: '.5px',
                          }}>
                            Specialist
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '.75rem', color: 'var(--text-secondary)', marginTop: 2 }}>{p.origin}</div>
                      {p.description && (
                        <div style={{ fontSize: '.78rem', color: 'var(--text-primary)', marginTop: 5, lineHeight: 1.4 }}>
                          {p.description}
                        </div>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* ── Cultural Guides (collapsible) ── */}
          <div>
            <button
              onClick={() => setShowCultural((v) => !v)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--primary)', fontSize: '1rem', fontWeight: 600,
                marginBottom: showCultural ? 12 : 0, padding: '4px 0',
              }}
            >
              {showCultural ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
              🌍 Cultural Health Guides
              <span style={{ fontSize: '.75rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
                ({culturalPersonas.length} guides)
              </span>
            </button>

            {showCultural && (
              <>
                <p style={{ marginBottom: 14, fontSize: '.8rem', color: 'var(--text-secondary)' }}>
                  A culturally-named health guide that reads your record and responds in its own voice
                </p>
                {culturalGroups.map((g) => (
                  <div key={g.region} style={{ marginBottom: 20 }}>
                    <h4 style={{ marginBottom: 8, fontSize: '.9rem', color: 'var(--text-secondary)', fontWeight: 600 }}>{g.label}</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {g.items.map((p) => (
                        <button
                          key={p.key}
                          className="card"
                          onClick={() => pickPersona(p)}
                          style={{ cursor: 'pointer', textAlign: 'left', border: '2px solid transparent', transition: 'border-color .15s', padding: '10px 14px' }}
                          onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--primary)')}
                          onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'transparent')}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            {p.icon && <span style={{ fontSize: '1.2rem' }}>{p.icon}</span>}
                            <div>
                              <strong style={{ fontSize: '.9rem' }}>{p.title}</strong>
                              <span style={{ marginLeft: 8, fontSize: '.72rem', color: 'var(--text-secondary)' }}>{p.origin}</span>
                              {p.description && (
                                <div style={{ fontSize: '.75rem', color: 'var(--text-secondary)', marginTop: 2 }}>{p.description}</div>
                              )}
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── Chat UI ──────────────────────────────────────────────────────
  const isSpecialist = selectedPersona?.region === 'specialist';
  return (
    <div className="chat-container">
      <div className="page-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 className="page-title">AI Health Assistant</h1>
          <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '.85rem', display: 'flex', alignItems: 'center', gap: 6 }}>
            {selectedPersona.icon && <span>{selectedPersona.icon}</span>}
            Speaking with <strong style={{ marginLeft: 4 }}>{selectedPersona.title}</strong>
            {isSpecialist && (
              <span style={{
                fontSize: '.65rem', padding: '1px 7px', borderRadius: 10,
                background: 'var(--primary)', color: '#fff', fontWeight: 600,
                textTransform: 'uppercase', letterSpacing: '.5px',
              }}>
                Specialist
              </span>
            )}
            <span style={{ fontSize: '.75rem', color: 'var(--text-secondary)' }}>({selectedPersona.origin})</span>
          </p>
        </div>
        <button
          className="btn btn-outline"
          onClick={() => { setSelectedPersona(null); setMessages([]); }}
          title="Change agent"
        >
          <RefreshCw size={16} /> Change
        </button>
      </div>

      <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div className="chat-messages">
          {messages.map((msg, i) => (
            <div
              key={i}
              ref={i === lastUserIndex ? lastUserRef : null}
              className={`chat-message ${msg.role}`}
              style={i === lastUserIndex ? { scrollMarginTop: '0.5rem' } : undefined}
            >
              <div className="chat-bubble">
                {msg.role === 'assistant'
                  ? <AssistantMarkdown content={msg.content} />
                  : msg.content}
                {loading && i === messages.length - 1 && msg.role === 'assistant' && (
                  msg.content
                    ? <span className="typing-cursor" />
                    : <ChatStatus step={status} />
                )}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <form className="chat-input-area" onSubmit={handleSend}>
          <input
            className="form-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={recording
              ? 'Listening… speak your question'
              : (isSpecialist ? `Ask ${selectedPersona.title} about your health data...` : 'Ask about your health...')}
            disabled={loading}
          />
          <button
            type="button"
            className="btn btn-secondary"
            onClick={toggleRecording}
            disabled={loading}
            title={recording ? 'Stop recording' : 'Speak your question'}
            aria-label={recording ? 'Stop recording' : 'Speak your question'}
            style={recording ? { background: '#ef4444', color: '#fff', borderColor: '#ef4444' } : undefined}
          >
            {recording ? <MicOff size={18} /> : <Mic size={18} />}
          </button>
          <button className="btn btn-primary" type="submit" disabled={loading}>
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
}

