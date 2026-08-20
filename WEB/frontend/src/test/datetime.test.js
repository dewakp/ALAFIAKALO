import { describe, it, expect } from 'vitest';
import { parseServer, fmtDate, toDateInput, fmtCalendarDate } from '../utils/datetime';

/* A treatment entered on the 19th was reported as the 18th.
 *
 * `therapy_sessions.scheduled_date` is a CALENDAR DATE stored in a datetime
 * column. It serializes as "2026-08-19T00:00:00" — indistinguishable from a
 * naive instant — and was parsed as midnight UTC. Rendered anywhere west of
 * UTC that is the previous day.
 *
 * These assertions read the LOCAL date components, so they hold in any
 * timezone rather than passing only on the machine that wrote them. */

const localParts = (d) => [d.getFullYear(), d.getMonth() + 1, d.getDate()];

describe('parseServer', () => {
  it('keeps a naive-midnight datetime on its own calendar day', () => {
    // The regression: this must be the 19th everywhere, not the 18th.
    expect(localParts(parseServer('2026-08-19T00:00:00'))).toEqual([2026, 8, 19]);
  });

  it('keeps a date-only string on its own day', () => {
    expect(localParts(parseServer('2026-08-19'))).toEqual([2026, 8, 19]);
  });

  it.each([
    '2026-08-19T00:00',
    '2026-08-19T00:00:00',
    '2026-08-19T00:00:00.000',
  ])('treats %s as a calendar date', (value) => {
    expect(localParts(parseServer(value))).toEqual([2026, 8, 19]);
  });

  it('still treats a naive datetime with a real time as UTC', () => {
    /* Only exact midnight is a calendar date; anything carrying a time of day
       is a genuine instant and keeps the existing behaviour. */
    expect(parseServer('2026-08-19T14:30:00').toISOString()).toBe('2026-08-19T14:30:00.000Z');
  });

  it('respects an explicit timezone', () => {
    expect(parseServer('2026-08-19T00:00:00Z').toISOString()).toBe('2026-08-19T00:00:00.000Z');
    expect(parseServer('2026-08-19T00:00:00+00:00').toISOString()).toBe('2026-08-19T00:00:00.000Z');
  });

  it('returns null for empty input', () => {
    expect(parseServer(null)).toBeNull();
    expect(parseServer('')).toBeNull();
  });
});

describe('formatting a stored session date', () => {
  it('renders the day it was entered', () => {
    expect(fmtDate('2026-08-19T00:00:00')).toContain('19');
  });

  it('round-trips through a date input unchanged', () => {
    /* Edit a session and the picker must show the date that was saved. */
    expect(toDateInput('2026-08-19T00:00:00')).toBe('2026-08-19');
  });
});

describe('fmtCalendarDate — engine-independent', () => {
  it.each([
    '2026-08-19T00:00:00',      // naive (what the API sends)
    '2026-08-19T00:00:00Z',     // if a serializer ever adds a Z
    '2026-08-19T00:00:00+00:00',
    '2026-08-19',
  ])('renders %s as the 19th', (value) => {
    /* A calendar date's meaning is its date part. Never let a timezone decide
       it — that is how a session entered on the 19th was reported as the 18th. */
    expect(fmtCalendarDate(value)).toContain('19');
  });

  it('returns empty for empty input', () => {
    expect(fmtCalendarDate(null)).toBe('');
    expect(fmtCalendarDate('')).toBe('');
  });
});
