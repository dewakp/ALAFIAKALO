import { describe, it, expect } from 'vitest';
import { newClinicalNote, normalizeTime } from '../pages/Hemodialysis';

/**
 * A session's `clinical_notes` is a LIST of note records; the form field is a
 * box for typing ONE new note. Loading a session for edit copied the list into
 * that field, and the submit handler called .trim() on an array:
 *
 *   Failed to save session: (l.clinical_notes||"").trim is not a function
 *
 * on a completed flowsheet, in production. These pin every shape the field can
 * actually hold.
 */
describe('newClinicalNote', () => {
  it('returns trimmed text for a string', () => {
    expect(newClinicalNote('  Tolerated well.  ')).toBe('Tolerated well.');
  });

  it('returns empty for an ARRAY — the shape that broke production', () => {
    expect(newClinicalNote([{ id: 1, note_text: 'existing note' }])).toBe('');
  });

  it('returns empty for an empty array', () => {
    expect(newClinicalNote([])).toBe('');
  });

  it('returns empty for null and undefined', () => {
    expect(newClinicalNote(null)).toBe('');
    expect(newClinicalNote(undefined)).toBe('');
  });

  it('returns empty for whitespace, so no blank note is posted', () => {
    expect(newClinicalNote('   ')).toBe('');
  });
});

/**
 * The em-dash bug: fmtTime() is a DISPLAY formatter that returns "—" when a
 * value is absent. startEdit used it to populate the form, so a reading with no
 * time became "—", which was POSTed and rejected by the API:
 *
 *   Failed to save session: reading_time: Input should be in a valid time
 *   format, invalid timezone sign
 *
 * Display formatting and form values are not the same job.
 */
describe('normalizeTime', () => {
  it('strips the trailing space that produced "invalid timezone sign"', () => {
    expect(normalizeTime('14:30 ')).toBe('14:30');
    expect(normalizeTime(' 14:30')).toBe('14:30');
    expect(normalizeTime('  14:30  ')).toBe('14:30');
  });

  it('drops seconds and fractions the field may carry', () => {
    expect(normalizeTime('14:30:00')).toBe('14:30');
    expect(normalizeTime('14:30:00.000')).toBe('14:30');
  });

  it('returns null for values the API rejects', () => {
    for (const v of ['14:30 AM', '2:30 PM', '14-30', '1430', '14:30-', '—', '', null, undefined]) {
      expect(normalizeTime(v)).toBeNull();
    }
  });

  it('accepts the 24h range and rejects outside it', () => {
    expect(normalizeTime('00:00')).toBe('00:00');
    expect(normalizeTime('23:59')).toBe('23:59');
    expect(normalizeTime('24:00')).toBeNull();
    expect(normalizeTime('12:60')).toBeNull();
  });

  it('never returns the display em-dash, for any input', () => {
    for (const v of [null, undefined, '', '—', 0, [], {}]) {
      expect(normalizeTime(v)).toBeNull();
    }
  });
});

describe('session start / end times', () => {
  it('reads the clock out of a stored datetime', async () => {
    const { timeOnly } = await import('../pages/Hemodialysis');
    expect(timeOnly('2026-08-15T08:05:00')).toBe('08:05');
    expect(timeOnly('2026-08-15T08:05:00Z')).toBe('08:05');
    expect(timeOnly('08:05')).toBe('08:05');
    for (const v of [null, undefined, '', '—', 0]) expect(timeOnly(v)).toBe('');
  });

  it('measures a treatment that runs past midnight as four hours, not minus twenty', async () => {
    const { minutesBetween } = await import('../pages/Hemodialysis');
    expect(minutesBetween('08:00', '11:30')).toBe(210);
    expect(minutesBetween('21:00', '01:00')).toBe(240);
    expect(minutesBetween('08:00', null)).toBeNull();
    expect(minutesBetween('', '11:30')).toBeNull();
  });
});
