/**
 * What the assistant is doing, while it cannot yet say anything.
 *
 * The tool rounds take tens of seconds and cannot stream — the model has to
 * read each result before it knows what to ask next — so the answer arrives at
 * the end, all at once. Before this, that whole wait was a blinking cursor on
 * an empty bubble, which reads as a hung page.
 *
 * Every line shown here is REPORTED by the server: "Checking your meals" means
 * get_meals actually ran, and "6 found" is the row count it returned. A rotating
 * set of reassuring phrases would have been easier and would have been fiction —
 * and fiction is what this whole surface was rebuilt to stop.
 */
export default function ChatStatus({ step }) {
  // Before the first frame lands there is still a real thing to say: the
  // request is open. Falling back to nothing would reinstate the blank wait.
  const label = step?.label || 'Querying AI…';
  const detail = step?.detail;

  return (
    <span className="chat-status" role="status" aria-live="polite">
      <span className="chat-status-dots" aria-hidden="true">
        <i /><i /><i />
      </span>
      <span key={label} className="chat-status-label">
        {label}
        {detail && <span className="chat-status-detail"> — {detail}</span>}
      </span>
    </span>
  );
}
