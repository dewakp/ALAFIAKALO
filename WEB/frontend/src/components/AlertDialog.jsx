import { useEffect, useRef } from 'react';
import { t } from '../i18n';

/**
 * A modal that interrupts.
 *
 * Signup errors were rendered into an inline `.auth-error` strip above a long
 * form. On a phone that strip is off-screen by the time someone presses the
 * button at the bottom, so the form appeared to do nothing — which is exactly
 * what a person who has already signed up once experiences, and it is why they
 * try again instead of signing in.
 *
 * `role="alertdialog"` (not "dialog") is deliberate: it tells assistive tech
 * this interrupts with a message, and the description is announced on open.
 *
 * There was no modal anywhere in this codebase, so this is the first one. It is
 * kept small and dependency-free for that reason.
 */
export default function AlertDialog({ open, title, message, onClose, actions = null }) {
  const closeRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    // Focus moves into the dialog, or a keyboard user is left tabbing through
    // the form behind it with no idea anything appeared.
    closeRef.current?.focus();

    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    document.addEventListener('keydown', onKey);

    // Lock the page behind it — the same rule the mobile nav drawer follows.
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div
        className="dialog-panel"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby="dialog-message"
        /* The backdrop closes; a click INSIDE must not bubble up to it and
           dismiss the message the person is still reading. */
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="dialog-title" id="dialog-title">{title}</h2>
        <p className="dialog-message" id="dialog-message">{message}</p>
        <div className="dialog-actions">
          {actions}
          <button type="button" ref={closeRef} className="btn-secondary" onClick={onClose}>
            {t('AlertDialog.dismiss')}
          </button>
        </div>
      </div>
    </div>
  );
}
