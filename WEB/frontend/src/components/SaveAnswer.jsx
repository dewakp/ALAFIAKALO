import { useState } from 'react';
import { Bookmark, BookmarkCheck } from 'lucide-react';
import api from '../services/api';

/**
 * Keep an AI answer, so it can be found again.
 *
 * An answer used to disappear the moment the screen changed. It was being
 * recorded all along — but a record nobody can reach is not a record, and a
 * patient who wants to show a clinician what the assistant said had nothing to
 * show.
 *
 * Saving flips a flag on the interaction that already exists. It does NOT copy
 * the text: a second copy is a second thing to keep in step, and the answer is
 * already stored.
 */
export default function SaveAnswer({ interactionId, initiallySaved = false }) {
  const [saved, setSaved] = useState(initiallySaved);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  if (!interactionId) return null;   // nothing to point at yet

  async function toggle() {
    setBusy(true);
    setFailed(false);
    const next = !saved;
    try {
      if (next) await api.post(`/ai/history/${interactionId}/save`);
      else await api.delete(`/ai/history/${interactionId}/save`);
      setSaved(next);
    } catch {
      // Say it failed rather than flipping the icon and lying about it — the
      // whole point is that the patient can rely on finding this again.
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      title={failed ? 'Could not save — try again' : saved ? 'Saved — click to remove' : 'Save this answer'}
      aria-pressed={saved}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '.35rem',
        background: 'none', border: 'none', cursor: busy ? 'wait' : 'pointer',
        padding: '2px 4px', fontSize: '.78rem',
        color: failed ? 'var(--color-danger, #dc2626)'
             : saved ? 'var(--color-primary, #f97316)'
             : 'var(--color-text-secondary, #64748b)',
      }}
    >
      {saved ? <BookmarkCheck size={14} /> : <Bookmark size={14} />}
      {failed ? 'Not saved' : saved ? 'Saved' : 'Save'}
    </button>
  );
}
