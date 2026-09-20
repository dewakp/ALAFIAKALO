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

/**
 * The clock card read 515 min for a 275-min treatment, in production entry.
 *
 * `ClockVsMachine` did `new Date(end) - new Date(start)`. The API's datetime
 * middleware stamps a trailing `Z` on every naive datetime, so a session
 * loaded from the server carries `…T16:25:00Z` — asserting UTC for a wall
 * clock the patient typed — while an end time just entered in the form is
 * written zone-less by `setSessionTime`. Date arithmetic then subtracted a
 * UTC-read 12:25 from a local-read 21:00: 8h35m instead of 4h35m.
 *
 * Two things hid it. `timeOnly` is a regex over the string, so both fields
 * displayed 04:25 PM and 09:00 PM correctly either way; and once the session is
 * SAVED both values carry the same spurious Z and the error cancels. It fires
 * only mid-entry — every time someone types an end time.
 *
 * The suite could not have caught it: these tests exercise `timeOnly` and
 * `minutesBetween`, which were always right, while the component that bypassed
 * them was not exported. §3af's lesson — a suite that cannot reach the thing it
 * tests is not evidence.
 */
describe('clockMinutes — the mixed-representation case', () => {
  /**
   * The test container runs UTC with `TZ` unset, and under UTC the BROKEN
   * implementation returns 275 too — the right answer for the wrong reason.
   * Every assertion below would have passed against `new Date(end) -
   * new Date(start)`, catching nothing.
   *
   * The defect IS a UTC/local divergence, so the test has to create one rather
   * than inherit whatever the host happens to be. Pinned to a zone with a real
   * offset; `America/New_York` was UTC-4 on the date in question, which is the
   * 4 hours that turned 275 into 515.
   */
  const realTZ = process.env.TZ;
  beforeAll(() => { process.env.TZ = 'America/New_York'; });
  afterAll(() => { process.env.TZ = realTZ; });

  it('measures the wall clock when only ONE side carries the spurious Z', async () => {
    const { clockMinutes } = await import('../pages/Hemodialysis');
    // Exactly the screenshot: stored start (Z-stamped), end typed into the form.
    expect(clockMinutes('2026-09-19T16:25:00Z', '2026-09-19T21:00:00')).toBe(275);
    // `new Date(end) - new Date(start)` returned 515 here, and the derived
    // figure then claimed 269 min not dialysing against a 246 min machine
    // total, instead of 29.
    expect(clockMinutes('2026-09-19T16:25:00Z', '2026-09-19T21:00:00')).not.toBe(515);
  });

  it('agrees with itself however each side happens to be zoned', async () => {
    const { clockMinutes } = await import('../pages/Hemodialysis');
    const cases = [
      ['2026-09-19T16:25:00Z', '2026-09-19T21:00:00Z'],   // both saved
      ['2026-09-19T16:25:00', '2026-09-19T21:00:00'],     // both typed
      ['2026-09-19T16:25:00', '2026-09-19T21:00:00Z'],    // the other way round
    ];
    for (const [a, b] of cases) expect(clockMinutes(a, b)).toBe(275);
  });

  it('still measures a session that runs past midnight', async () => {
    const { clockMinutes } = await import('../pages/Hemodialysis');
    expect(clockMinutes('2026-09-19T21:00:00Z', '2026-09-20T01:00:00')).toBe(240);
  });

  it('returns null when either end is missing, so the card stays blank', async () => {
    const { clockMinutes } = await import('../pages/Hemodialysis');
    expect(clockMinutes(null, '2026-09-19T21:00:00')).toBeNull();
    expect(clockMinutes('2026-09-19T16:25:00Z', '')).toBeNull();
    expect(clockMinutes('2026-09-19T21:00:00Z', '2026-09-19T21:00:00Z')).toBeNull();
  });
});
