import { useState, useId } from 'react';
import { Eye, EyeOff } from 'lucide-react';

/**
 * Password field with a show/hide toggle.
 *
 * Typing a password blind is the main cause of failed logins and mistyped
 * confirmations, so every password field in the app uses this rather than a
 * bare <input type="password">.
 *
 * Notes that matter:
 *  - The toggle is `type="button"`. Inside a <form> a bare <button> defaults to
 *    submit, so revealing the password would post the form.
 *  - It is a real focusable button with an aria-label and aria-pressed, so the
 *    state is announced rather than being an unlabelled icon.
 *  - `tabIndex={-1}` is deliberately NOT set: a keyboard user must be able to
 *    reach it.
 *  - Revealed text still uses autoComplete/autoCorrect settings appropriate to a
 *    password so the browser does not autocapitalise or spell-check it.
 */
export default function PasswordInput({
  value,
  onChange,
  placeholder = '••••••••',
  autoComplete = 'current-password',
  required = false,
  disabled = false,
  id,
  className = 'form-input',
  ...rest
}) {
  const [revealed, setRevealed] = useState(false);
  const generatedId = useId();
  const inputId = id || generatedId;

  return (
    <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
      <input
        id={inputId}
        className={className}
        type={revealed ? 'text' : 'password'}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        required={required}
        disabled={disabled}
        autoComplete={autoComplete}
        autoCorrect="off"
        autoCapitalize="none"
        spellCheck="false"
        style={{ width: '100%', paddingRight: '2.5rem' }}
        {...rest}
      />
      <button
        type="button"
        onClick={() => setRevealed((v) => !v)}
        aria-label={revealed ? 'Hide password' : 'Show password'}
        aria-pressed={revealed}
        aria-controls={inputId}
        title={revealed ? 'Hide password' : 'Show password'}
        disabled={disabled}
        style={{
          position: 'absolute',
          right: '.6rem',
          background: 'none',
          border: 'none',
          padding: 4,
          cursor: disabled ? 'default' : 'pointer',
          color: 'var(--color-text-tertiary)',
          display: 'flex',
          alignItems: 'center',
        }}
      >
        {revealed ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  );
}
