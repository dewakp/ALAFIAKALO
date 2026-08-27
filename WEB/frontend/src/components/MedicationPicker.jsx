import { useState, useMemo, useRef, useId } from 'react';

/**
 * Type-ahead over what this patient actually takes.
 *
 * The field was a plain input backed by a `<datalist>` fed from PRESCRIPTIONS
 * only. On an account holding 943 dose logs and zero prescriptions, typing
 * "Calcium" offered nothing — while its own history held Calcium carbonate 489
 * times (canon 3aa: prescribed and taken are different facts).
 *
 * `<datalist>` was the wrong instrument regardless: matching differs between
 * browsers, it cannot show provenance, and it is unreliable on mobile. This
 * matches on substring, shows how often and how recently each drug was taken,
 * and still accepts a free-typed name for something genuinely new.
 *
 * Worth stating plainly: a picker is also a SAFETY control. The 422 that blocked
 * a real dose was "Calcium Carbonated" — one letter off a drug the patient had
 * logged hundreds of times. Choosing from history cannot produce that typo.
 */
export default function MedicationPicker({
  value,
  onChange,
  options = [],          // [{ name, times_logged, last_taken, source }]
  placeholder = 'Start typing — your medications appear as you type',
  inputId,
}) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const blurTimer = useRef(null);
  const listboxId = `${useId()}-meds`;

  const matches = useMemo(() => {
    const q = (value || '').trim().toLowerCase();
    if (!q) return options.slice(0, 8);
    return options.filter((o) => o.name.toLowerCase().includes(q)).slice(0, 8);
  }, [value, options]);

  // An exact hit needs no dropdown — it would just cover the next field.
  const exact = (value || '').trim().toLowerCase();
  const showList = open && matches.length > 0
    && !(matches.length === 1 && matches[0].name.toLowerCase() === exact);

  function choose(option) {
    onChange(option.name);
    setOpen(false);
    setHighlight(0);
  }

  function onKeyDown(e) {
    if (!showList) {
      if (e.key === 'ArrowDown') { setOpen(true); e.preventDefault(); }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, matches.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter' && matches[highlight]) {
      // Only swallow Enter when a suggestion is actually highlighted, or the
      // form can never be submitted by keyboard.
      e.preventDefault();
      choose(matches[highlight]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  }

  return (
    <div style={{ position: 'relative' }}>
      <input
        id={inputId}
        className="form-input"
        type="text"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listboxId}
        aria-autocomplete="list"
        autoComplete="off"
        data-testid="medication-picker-input"
        value={value}
        placeholder={placeholder}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setHighlight(0); }}
        onFocus={() => setOpen(true)}
        // Deferred so a click on an option lands before the list unmounts.
        onBlur={() => { blurTimer.current = setTimeout(() => setOpen(false), 120); }}
        onKeyDown={onKeyDown}
      />

      {showList && (
        <ul
          id={listboxId}
          role="listbox"
          data-testid="medication-suggestions"
          style={{
            position: 'absolute', zIndex: 30, left: 0, right: 0, margin: '4px 0 0',
            padding: 0, listStyle: 'none', maxHeight: 260, overflowY: 'auto',
            background: 'var(--color-surface, #fff)', border: '1px solid #ddd',
            borderRadius: 4, boxShadow: '0 6px 18px rgba(0,0,0,0.12)',
          }}
        >
          {matches.map((o, i) => (
            <li
              key={o.name}
              role="option"
              aria-selected={i === highlight}
              onMouseEnter={() => setHighlight(i)}
              onMouseDown={() => { clearTimeout(blurTimer.current); choose(o); }}
              style={{
                padding: '8px 12px', cursor: 'pointer',
                background: i === highlight ? 'var(--color-bg-secondary, #f2f4f7)' : 'transparent',
              }}
            >
              <div style={{ fontWeight: 500 }}>{o.name}</div>
              <div style={{ fontSize: '.75rem', color: 'var(--color-text-tertiary, #667)' }}>
                {/* Provenance, always: "489 times" is the difference between a
                    drug they take and one they typed once by mistake. */}
                {o.source === 'prescription'
                  ? 'On your prescription list'
                  : `Taken ${o.times_logged}×${o.last_taken ? ` · last ${o.last_taken}` : ''}`}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
