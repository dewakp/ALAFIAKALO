import { useState, useRef } from 'react';
import { detachFile } from '../utils/fileInput';
import { useNavigate } from 'react-router-dom';
import { Send, Mic, Square, Camera, Loader2, Apple, Pill, BookOpen, Bot } from 'lucide-react';
import api from '../services/api';
import { apiErrorMessage } from '../utils/apiError';

// Basis.md: "Use prompt as entry point. voice, text or image will determine
// interface to surface." This screen is that entry point — it classifies the
// user's input and surfaces the matching existing screen, pre-filled.

const QUICK_ACTIONS = [
  { label: 'Log a meal', icon: Apple, seed: 'I ate ' },
  { label: 'Log medication', icon: Pill, seed: 'I took ' },
  { label: 'Journal', icon: BookOpen, seed: '' },
  { label: 'Ask a question', icon: Bot, seed: '' },
];

export default function PromptHub() {
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [recording, setRecording] = useState(false);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const cameraInputRef = useRef(null);
  const recognitionRef = useRef(null);

  // Local CPU inference (Ollama) can take 20-60s+ — give these calls room.
  const LONG_TIMEOUT = 180000;

  // ── Core: classify text/transcript, then surface the matching screen ──
  async function routeText(text, modality = 'text') {
    const trimmed = (text || '').trim();
    if (!trimmed) return;
    setBusy(true);
    setStatus('Understanding…');
    try {
      const { data } = await api.post('/ai/route', { text: trimmed, modality }, { timeout: LONG_TIMEOUT });
      setStatus(data.assistant_message || '');
      // A general question goes straight into the chat, answered by the GP agent
      // (no persona picker). Logging intents open their screen pre-filled.
      const navState =
        data.intent === 'ask_question'
          ? { fromPrompt: true, intent: data.intent, autoAsk: trimmed }
          : { prefill: data.prefill, fromPrompt: true, intent: data.intent };
      navigate(data.route, { state: navState });
    } catch (err) {
      setStatus(apiErrorMessage(err, 'Could not understand that. Try the AI assistant.'));
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (!busy) routeText(input);
  }

  function handleQuickAction(seed) {
    setInput(seed);
    if (!seed) document.getElementById('prompt-input')?.focus();
  }

  // ── Voice ──────────────────────────────────────────────────────────
  // Dev: prefer the browser's built-in Web Speech API (free, on-device, no
  // server STT needed). Fall back to recording + server /ai/voice (Whisper)
  // when the browser doesn't support it.
  function getSpeechRecognition() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function toggleRecording() {
    if (recording) {
      recognitionRef.current?.stop();
      mediaRecorderRef.current?.stop();
      return;
    }
    const SR = getSpeechRecognition();
    if (SR) {
      startBrowserRecognition(SR);
    } else {
      startServerRecording();
    }
  }

  function startBrowserRecognition(SR) {
    try {
      const recognition = new SR();
      recognition.lang = 'en-US';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.onresult = (event) => {
        const transcript = event.results?.[0]?.[0]?.transcript || '';
        setInput(transcript);
        if (transcript) routeText(transcript, 'voice');
        else setStatus('Did not catch that — please try again.');
      };
      recognition.onerror = (e) => {
        setRecording(false);
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
          setStatus('Microphone permission denied. You can type instead.');
        } else if (e.error === 'no-speech') {
          setStatus('Did not hear anything — please try again.');
        } else {
          setStatus('Voice recognition error. You can type instead.');
        }
      };
      recognition.onend = () => setRecording(false);
      recognitionRef.current = recognition;
      recognition.start();
      setRecording(true);
      setStatus('Listening… tap the stop button when done.');
    } catch {
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
        await transcribeAndRoute(new Blob(chunksRef.current, { type: 'audio/webm' }));
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setStatus('Listening… tap the stop button when done.');
    } catch {
      setStatus('Microphone unavailable. You can type instead.');
    }
  }

  async function transcribeAndRoute(blob) {
    setBusy(true);
    setStatus('Transcribing…');
    try {
      const form = new FormData();
      form.append('file', blob, 'note.webm');
      form.append('task', 'transcribe');
      const { data } = await api.post('/ai/voice', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: LONG_TIMEOUT,
      });
      const transcript = data.transcript || data.text || '';
      if (transcript) {
        setInput(transcript);
        await routeText(transcript, 'voice');
      } else {
        setStatus('Did not catch that — please try again.');
      }
    } catch (err) {
      setStatus(apiErrorMessage(err, 'Voice transcription is unavailable. Please type instead.'));
    } finally {
      setBusy(false);
    }
  }

  // ── Camera: capture → /ai/vision → surface nutrition or capture flow ──
  function handleCameraClick() {
    cameraInputRef.current?.click();
  }

  async function handleImageSelected(e) {
    // Detach BEFORE clearing: the reset strips the data off the original File
    // in WebKit, and it would upload as an empty part.
    const file = await detachFile(e.target.files);
    e.target.value = '';
    if (!file) return;
    setBusy(true);
    setStatus('Looking at your photo…');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('task', 'food_photo_nutrition');
      const { data } = await api.post('/ai/vision', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: LONG_TIMEOUT,
      });
      const items = data.items || [];
      if (items.length) {
        navigate('/nutrition', {
          state: { prefill: { vision: data, items }, fromPrompt: true, intent: 'log_meal' },
        });
        return;
      }
      // Nothing recognized — fall back to manual capture, keeping the photo.
      setStatus('Saved to Capture for manual review.');
      navigate('/capture', { state: { fromPrompt: true, intent: 'vision_capture' } });
    } catch (err) {
      // Vision backend not configured → graceful fallback to manual capture.
      setStatus(apiErrorMessage(err, 'Image AI unavailable — opening manual capture.'));
      navigate('/capture', { state: { fromPrompt: true, intent: 'vision_capture' } });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', paddingTop: '8vh' }}>
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <h1 style={{ fontSize: '1.9rem', marginBottom: 6 }}>How are you doing today?</h1>
        <p style={{ color: 'var(--text-secondary)' }}>
          Type, speak, or snap a photo — ALAFIA will take it from there.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="card" style={{ padding: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            type="button"
            className="btn btn-outline"
            onClick={toggleRecording}
            disabled={busy && !recording}
            title={recording ? 'Stop recording' : 'Speak'}
            aria-label={recording ? 'Stop recording' : 'Speak'}
            style={recording ? { color: '#d50000', borderColor: '#d50000' } : undefined}
          >
            {recording ? <Square size={18} /> : <Mic size={18} />}
          </button>

          <button
            type="button"
            className="btn btn-outline"
            onClick={handleCameraClick}
            disabled={busy}
            title="Take or upload a photo"
            aria-label="Take or upload a photo"
          >
            <Camera size={18} />
          </button>
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleImageSelected}
            style={{ display: 'none' }}
          />

          <input
            id="prompt-input"
            className="form-input"
            style={{ flex: 1 }}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. I ate jollof rice and took my 10mg lisinopril"
            disabled={busy}
            autoFocus
          />

          <button className="btn btn-primary" type="submit" disabled={busy || !input.trim()}>
            {busy ? <Loader2 size={18} className="spin" /> : <Send size={18} />}
          </button>
        </div>

        {status && (
          <div style={{ marginTop: 10, fontSize: '.85rem', color: 'var(--text-secondary)' }}>
            {status}
          </div>
        )}
      </form>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', marginTop: 18 }}>
        {QUICK_ACTIONS.map(({ label, icon: Icon, seed }) => (
          <button
            key={label}
            type="button"
            className="btn btn-outline btn-sm"
            onClick={() => handleQuickAction(seed)}
            disabled={busy}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>
    </div>
  );
}
