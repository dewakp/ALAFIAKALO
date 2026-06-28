import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import api, { ensureCsrfToken, refreshAccessToken } from '../services/api';
import { apiErrorMessage } from '../utils/apiError';
import { Send, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react';
import BackButton from '../components/BackButton';

const REGION_ORDER = ['africa', 'middle_east', 'south_asia', 'europe', 'north_america'];
const REGION_LABELS = {
  africa: '🌍 Africa',
  middle_east: '🕌 Middle East',
  south_asia: '🕉 South Asia',
  europe: '🏰 Europe',
  north_america: '🗽 North America',
};

const SPECIALIST_DESCRIPTIONS = {
  nephrologist: 'CKD staging, dialysis adequacy (KtV/URR), electrolytes, lab interpretation.',
  renal_dietitian: 'Kidney-friendly meal planning, phosphorus & potassium restriction, protein targets.',
  cardiologist: 'Blood pressure trends, cardiovascular risk, fluid management.',
  mental_health_counselor: 'Emotional wellbeing, mood patterns, coping with chronic illness.',
  exercise_physiologist: 'Safe exercise for dialysis patients, fatigue management, strength goals.',
  dialysis_coordinator: 'Session monitoring, AV fistula care, daily dialysis guidance.',
  general_practitioner: 'Comprehensive health overview, medication review, all-in-one evaluation.',
  pharmacologist: 'Medication explanations, drug interactions, dosage review.',
};

const FALLBACK_SPECIALISTS = [
  { key: 'nephrologist', title: 'Dr. Nephros', origin: 'Nephrology · Kidney & Dialysis', region: 'specialist', greeting: 'Good day', icon: '🔬', specialty: 'nephrology', description: SPECIALIST_DESCRIPTIONS.nephrologist },
  { key: 'renal_dietitian', title: 'Dietitian Rena', origin: 'Renal Nutrition · Clinical Dietitian', region: 'specialist', greeting: 'Hi there', icon: '🥗', specialty: 'renal_nutrition', description: SPECIALIST_DESCRIPTIONS.renal_dietitian },
  { key: 'cardiologist', title: 'Dr. Cardio', origin: 'Cardiology · Heart & Vascular', region: 'specialist', greeting: 'Good day', icon: '❤️', specialty: 'cardiology', description: SPECIALIST_DESCRIPTIONS.cardiologist },
  { key: 'mental_health_counselor', title: 'Dr. Solace', origin: 'Psychology · Mental Health', region: 'specialist', greeting: 'Welcome', icon: '🧠', specialty: 'mental_health', description: SPECIALIST_DESCRIPTIONS.mental_health_counselor },
  { key: 'exercise_physiologist', title: 'Coach Vitalis', origin: 'Exercise Physiology · Fitness', region: 'specialist', greeting: "Let's work on this together", icon: '🏃', specialty: 'exercise_physiology', description: SPECIALIST_DESCRIPTIONS.exercise_physiologist },
  { key: 'dialysis_coordinator', title: 'Coordinator Adaeze', origin: 'Dialysis Nursing · Renal Care', region: 'specialist', greeting: 'Hello', icon: '💉', specialty: 'dialysis_nursing', description: SPECIALIST_DESCRIPTIONS.dialysis_coordinator },
  { key: 'general_practitioner', title: 'Dr. Holista', origin: 'General Practice · Primary Care', region: 'specialist', greeting: 'Welcome', icon: '🩺', specialty: 'general_practice', description: SPECIALIST_DESCRIPTIONS.general_practitioner },
  { key: 'pharmacologist', title: 'Pharmacologist', origin: 'Clinical Pharmacology · Global', region: 'specialist', greeting: 'Hello', icon: '💊', specialty: 'pharmacology', description: SPECIALIST_DESCRIPTIONS.pharmacologist },
];

const FALLBACK_CULTURAL = [
  { key: 'babalawo', title: 'Babalawo', origin: 'Yoruba · Nigeria', region: 'africa', greeting: 'Ẹ kú àárọ̀', icon: '🪄', description: 'Yoruba healing wisdom — body, spirit, and destiny in balance.' },
  { key: 'dibia', title: 'Dibia', origin: 'Igbo · Nigeria', region: 'africa', greeting: 'Nnọọ', icon: '🌿', description: 'Igbo holistic healer — practical, warm, grounded in nature.' },
  { key: 'boka', title: 'Boka', origin: 'Hausa · Nigeria', region: 'africa', greeting: 'Sannu', icon: '🌙', description: 'Hausa healing wisdom — respectful and spiritually grounded.' },
  { key: 'sage', title: 'Sage', origin: 'English · UK / Ireland', region: 'europe', greeting: 'Welcome', icon: '🎓', description: 'British sage — articulate, evidence-based, and reassuring.' },
  { key: 'medicine_keeper', title: 'Medicine Keeper', origin: 'Native American · US / Canada', region: 'north_america', greeting: 'Aho', icon: '🦅', description: 'Native American healer — all is connected: body, mind, and spirit.' },
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
  const [showCultural, setShowCultural] = useState(false);
  const messagesEndRef = useRef(null);
  const { state } = useLocation();
  const autoAskHandled = useRef(false);

  useEffect(() => {
    api.get('/ai/personas')
      .then(({ data }) => {
        setAllPersonas(data);
        setSpecialists(data.filter((p) => p.region === 'specialist'));
      })
      .catch(() => {
        setAllPersonas([...FALLBACK_SPECIALISTS, ...FALLBACK_CULTURAL]);
        setSpecialists(FALLBACK_SPECIALISTS);
      });
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Prompt Hub hand-off: a general health question arrives here as autoAsk. Skip
  // the persona picker, default to the general practitioner, and answer it.
  useEffect(() => {
    if (autoAskHandled.current || !state?.autoAsk || !allPersonas.length) return;
    autoAskHandled.current = true;
    const gp =
      allPersonas.find((p) => p.key === 'general_practitioner') ||
      FALLBACK_SPECIALISTS.find((p) => p.key === 'general_practitioner');
    if (!gp) return;
    setSelectedPersona(gp);
    setMessages([]);
    sendMessage(state.autoAsk, gp, []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, allPersonas]);

  function pickPersona(persona) {
    setSelectedPersona(persona);
    const isSpecialist = persona.region === 'specialist';
    const intro = isSpecialist
      ? `${persona.greeting}! I'm ${persona.title}. ${persona.description || ''} What can I help you with today?`
      : `${persona.greeting}! I'm ${persona.title} — your personal health guide. What's on your mind today?`;
    setMessages([{ role: 'assistant', content: intro }]);
  }

  function handleSend(e) {
    e.preventDefault();
    if (!input.trim() || loading || !selectedPersona) return;
    const userMessage = input.trim();
    setInput('');
    sendMessage(userMessage, selectedPersona, messages);
  }

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
            const { content, error } = JSON.parse(payload);
            if (error) {
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = { role: 'assistant', content: `⚠️ ${error}` };
                return next;
              });
              break;
            }
            if (content) {
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
    }
  }

  // ── Persona / Agent picker ──────────────────────────────────────
  if (!selectedPersona) {
    const culturalPersonas = allPersonas.filter((p) => p.region !== 'specialist');
    const displaySpecialists = specialists.length ? specialists : FALLBACK_SPECIALISTS;
    const culturalGroups = groupByRegion(culturalPersonas.length ? culturalPersonas : FALLBACK_CULTURAL);

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
                ({culturalPersonas.length || FALLBACK_CULTURAL.length} guides)
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
            <div key={i} className={`chat-message ${msg.role}`}>
              <div className="chat-bubble">
                {msg.content}
                {loading && i === messages.length - 1 && msg.role === 'assistant' && (
                  <span className="typing-cursor" />
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
            placeholder={isSpecialist ? `Ask ${selectedPersona.title} about your health data...` : 'Ask about your health...'}
            disabled={loading}
          />
          <button className="btn btn-primary" type="submit" disabled={loading}>
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
}

