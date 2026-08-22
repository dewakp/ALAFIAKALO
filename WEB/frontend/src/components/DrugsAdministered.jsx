import React, { useEffect, useState } from 'react';
import { Plus, X } from 'lucide-react';
import api from '../services/api';

/**
 * Structured capture for drugs given DURING a dialysis session.
 *
 * The field behind this was a single free-text box, and on the HD flowsheet it
 * did not exist at all — a decade of Epogene, Venofer and Doxercalciferol
 * reached the database only by import. Nothing else in the app could see it.
 *
 * It still SERIALISES to the same `Name (dose); Name (dose)` string the 1,964
 * historical rows use. One format means a row typed in 2019 and a row captured
 * here parse identically, and no migration is needed to make history readable.
 *
 * Free text remains reachable: a unit that gives something not on the list must
 * be able to record it, and an unrecognised drug is kept verbatim rather than
 * forced into the nearest match.
 */

/** `Name (dose); Name` → [{ name, dose }] — mirrors the backend parser. */
export function parseDrugs(text) {
  if (!text || !text.trim()) return [];
  const items = [];
  let depth = 0;
  let current = '';
  for (const ch of text) {
    if (ch === '(') depth += 1;
    else if (ch === ')') depth = Math.max(0, depth - 1);
    // A semicolon inside parentheses is part of a dose, not a separator:
    // "Sodium Citrate (12 ml Venous; 3ml Arterial)" is ONE drug.
    if (ch === ';' && depth === 0) { items.push(current); current = ''; }
    else current += ch;
  }
  items.push(current);

  return items
    .map((raw) => raw.trim())
    .filter(Boolean)
    .map((raw) => {
      const m = raw.match(/^([^(]+?)\s*(?:\((.*)\))?\s*$/s);
      if (!m) return null;
      const name = (m[1] || '').trim();
      if (!name) return null;
      return { name, dose: (m[2] || '').trim() };
    })
    .filter(Boolean);
}

/** [{ name, dose }] → `Name (dose); Name` — round-trips with parseDrugs. */
export function formatDrugs(rows) {
  return (rows || [])
    .map(({ name, dose }) => ({
      name: (name || '').replace(/[()]/g, '').trim(),
      dose: (dose || '').replace(/[()]/g, '').trim(),
    }))
    .filter((r) => r.name)
    .map((r) => (r.dose ? `${r.name} (${r.dose})` : r.name))
    .join('; ');
}

export default function DrugsAdministered({ value, onChange, label = 'Drugs Administered' }) {
  const [rows, setRows] = useState(() => parseDrugs(value));
  const [options, setOptions] = useState([]);
  const [optionsError, setOptionsError] = useState(false);

  // Re-seed when the caller swaps sessions (edit a different flowsheet).
  useEffect(() => { setRows(parseDrugs(value)); }, [value]);

  useEffect(() => {
    let cancelled = false;
    api.get('/chronic/flowsheet-drugs')
      .then(({ data }) => { if (!cancelled) { setOptions(data.drugs || []); setOptionsError(false); } })
      .catch((err) => {
        // Losing the picker must not block recording a drug — the field still
        // takes free text. Say the list is missing rather than showing none.
        console.error('Could not load flowsheet drug list:', err);
        if (!cancelled) setOptionsError(true);
      });
    return () => { cancelled = true; };
  }, []);

  const push = (next) => { setRows(next); onChange(formatDrugs(next)); };
  const setRow = (i, patch) => push(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const addRow = () => push([...rows, { name: '', dose: '' }]);
  const removeRow = (i) => push(rows.filter((_, j) => j !== i));

  const hintFor = (name) =>
    options.find((o) => o.label.toLowerCase() === (name || '').toLowerCase())?.dose_hint || 'dose';
  const classFor = (name) =>
    options.find((o) => o.label.toLowerCase() === (name || '').toLowerCase())?.class;

  return (
    <div>
      <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>{label}</label>

      {optionsError && (
        <div data-testid="drug-options-error"
             style={{ fontSize: '.75rem', color: '#c62828', marginBottom: '.4rem' }}>
          Could not load the drug list — you can still type a name and dose.
        </div>
      )}

      {rows.length === 0 && (
        <div style={{ fontSize: '.8rem', color: 'var(--color-text-tertiary, #888)', marginBottom: '.4rem' }}>
          No drugs recorded for this session.
        </div>
      )}

      {rows.map((row, i) => (
        <div key={i} style={{ display: 'flex', gap: '.5rem', marginBottom: '.4rem', alignItems: 'center' }}>
          <input
            list="flowsheet-drug-options"
            aria-label={`Drug ${i + 1} name`}
            value={row.name}
            onChange={(e) => setRow(i, { name: e.target.value })}
            placeholder="Drug"
            style={{ flex: 2, padding: '8px', borderRadius: 4, border: '1px solid #ddd' }}
          />
          <input
            aria-label={`Drug ${i + 1} dose`}
            value={row.dose}
            onChange={(e) => setRow(i, { dose: e.target.value })}
            placeholder={hintFor(row.name)}
            style={{ flex: 1, padding: '8px', borderRadius: 4, border: '1px solid #ddd' }}
          />
          {classFor(row.name) && (
            <span style={{ fontSize: '.7rem', color: 'var(--color-text-tertiary, #888)', whiteSpace: 'nowrap' }}>
              {classFor(row.name)}
            </span>
          )}
          <button type="button" onClick={() => removeRow(i)} aria-label={`Remove drug ${i + 1}`}
                  style={{ border: 'none', background: 'none', cursor: 'pointer', color: '#888' }}>
            <X size={14} />
          </button>
        </div>
      ))}

      <datalist id="flowsheet-drug-options">
        {options.map((o) => <option key={o.label} value={o.label}>{o.class}</option>)}
      </datalist>

      <button type="button" onClick={addRow} className="btn btn-secondary btn-sm"
              style={{ marginTop: '.2rem' }}>
        <Plus size={12} /> Add drug
      </button>
    </div>
  );
}
