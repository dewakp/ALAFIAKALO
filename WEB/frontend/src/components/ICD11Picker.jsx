import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import api from '../services/api';

/**
 * Type-ahead for ICD-11 codes, backed by GET /chronic/icd11/search.
 *
 * The patient types what they know — "ESRD", "sickle cell", "kidney" — and
 * picks an entity; the backend stores WHO's official title alongside the code,
 * so nothing here needs to send a title.
 *
 * A failed lookup renders as its own message, never as "no matches". Silently
 * turning an error into an empty state is the recurring bug on this app's
 * clinical surfaces (CLAUDE.md §3aa) and it reads to the patient as "my
 * condition is not in the catalog".
 */
const DEBOUNCE_MS = 250;

export default function ICD11Picker({
  code,
  title,
  onChange,
  disabled = false,
  inputStyle,
  label = 'ICD-11 Code',
  hint = 'Search by name, abbreviation or code — e.g. "kidney", "ESRD", "GB61.5"',
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [highlight, setHighlight] = useState(0);

  const boxRef = useRef(null);
  const requestSeq = useRef(0);
  const listboxId = useId();
  const inputId = useId();

  // Close when focus leaves the whole widget (not merely the input, or
  // clicking a suggestion would dismiss the list before it registered).
  useEffect(() => {
    const onDocPointerDown = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDocPointerDown);
    return () => document.removeEventListener('mousedown', onDocPointerDown);
  }, []);

  const runSearch = useCallback(async (text) => {
    const term = text.trim();
    if (!term) {
      setResults([]);
      setLoadError(null);
      setLoading(false);
      return;
    }

    // Out-of-order responses would otherwise let a stale, slower request
    // overwrite the results for what the user has actually typed.
    const seq = ++requestSeq.current;
    setLoading(true);
    try {
      const { data } = await api.get('/chronic/icd11/search', {
        params: { q: term, limit: 12 },
      });
      if (seq !== requestSeq.current) return;
      setResults(data.results || []);
      setLoadError(null);
      setHighlight(0);
    } catch (err) {
      if (seq !== requestSeq.current) return;
      console.error('ICD-11 search failed:', err);
      setResults([]);
      setLoadError(
        err?.response?.status === 401
          ? 'Your session expired — sign in again to search ICD-11.'
          : 'Could not reach the ICD-11 catalog. Your condition may still be there.',
      );
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const timer = setTimeout(() => runSearch(query), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, open, runSearch]);

  const select = (entry) => {
    onChange({ code: entry.code, title: entry.title });
    setQuery('');
    setResults([]);
    setOpen(false);
  };

  const clear = () => {
    onChange({ code: '', title: '' });
    setQuery('');
    setResults([]);
    setLoadError(null);
  };

  const onKeyDown = (e) => {
    if (!open || (!results.length && !loadError)) {
      if (e.key === 'ArrowDown') setOpen(true);
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter' && results[highlight]) {
      // Only swallow Enter when a suggestion is actually being taken, so the
      // key still submits the surrounding form otherwise.
      e.preventDefault();
      select(results[highlight]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  const baseInput = inputStyle || {
    width: '100%',
    padding: '8px',
    borderRadius: '4px',
    border: '1px solid #ddd',
  };

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      <label
        htmlFor={inputId}
        style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}
      >
        {label}
      </label>

      {code ? (
        <div
          data-testid="icd11-selected"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '8px',
            borderRadius: '4px',
            border: '1px solid #c8e6c9',
            backgroundColor: '#f1f8e9',
          }}
        >
          <code
            style={{
              fontWeight: 700,
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              whiteSpace: 'nowrap',
            }}
          >
            {code}
          </code>
          <span style={{ flex: 1, fontSize: '0.9rem', color: '#33691e' }}>{title}</span>
          {!disabled && (
            <button
              type="button"
              onClick={clear}
              aria-label={`Remove ICD-11 code ${code}`}
              style={{
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                fontSize: '1.1rem',
                lineHeight: 1,
                color: '#666',
              }}
            >
              ×
            </button>
          )}
        </div>
      ) : (
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-autocomplete="list"
          autoComplete="off"
          disabled={disabled}
          value={query}
          placeholder={hint}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          style={baseInput}
        />
      )}

      {open && !code && (loading || loadError || results.length > 0 || query.trim()) && (
        <ul
          id={listboxId}
          role="listbox"
          style={{
            position: 'absolute',
            zIndex: 30,
            left: 0,
            right: 0,
            margin: '4px 0 0',
            padding: 0,
            listStyle: 'none',
            maxHeight: '260px',
            overflowY: 'auto',
            background: 'var(--color-surface, #fff)',
            border: '1px solid #ddd',
            borderRadius: '4px',
            boxShadow: '0 6px 18px rgba(0,0,0,0.12)',
          }}
        >
          {loadError ? (
            <li
              data-testid="icd11-error"
              style={{ padding: '10px 12px', color: '#c62828', fontSize: '0.88rem' }}
            >
              {loadError}{' '}
              <button
                type="button"
                onClick={() => runSearch(query)}
                style={{
                  border: 'none',
                  background: 'transparent',
                  color: '#1565c0',
                  cursor: 'pointer',
                  textDecoration: 'underline',
                  padding: 0,
                }}
              >
                Retry
              </button>
            </li>
          ) : loading ? (
            <li style={{ padding: '10px 12px', color: '#666', fontSize: '0.88rem' }}>
              Searching…
            </li>
          ) : results.length === 0 ? (
            <li
              data-testid="icd11-empty"
              style={{ padding: '10px 12px', color: '#666', fontSize: '0.88rem' }}
            >
              No ICD-11 match for “{query.trim()}”. You can still save the condition
              by name.
            </li>
          ) : (
            results.map((entry, idx) => (
              <li key={entry.code}>
                <button
                  type="button"
                  role="option"
                  aria-selected={idx === highlight}
                  onMouseEnter={() => setHighlight(idx)}
                  onClick={() => select(entry)}
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    padding: '8px 12px',
                    border: 'none',
                    cursor: 'pointer',
                    background: idx === highlight ? '#e3f2fd' : 'transparent',
                  }}
                >
                  <code
                    style={{
                      fontWeight: 700,
                      marginRight: '8px',
                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    }}
                  >
                    {entry.code}
                  </code>
                  <span>{entry.title}</span>
                  <span
                    style={{
                      display: 'block',
                      fontSize: '0.76rem',
                      color: '#777',
                      marginTop: '2px',
                    }}
                  >
                    {entry.chapter_title}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
