// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

/**
 * The dashboard rendered every elimination event as the same wrong time.
 *
 * Reported 2026-10-14 with a screenshot: two bowel movements logged at 00:40
 * and 10:30, both drawn as "08:00 PM", beside an Elimination Log showing the
 * true times. Three faults in one line — see the comment at
 * `buildEliminationEvents`.
 *
 * ⚠️ **Run this against the OLD code first.** The three tests that fail there
 * are the regression guards; the rest are coverage, and calling them all
 * guards would be the §3al mistake of counting a test that passes against the
 * broken implementation.
 */

import { describe, expect, it } from 'vitest';
import { buildEliminationEvents } from '../pages/Dashboard';

// Exactly what `GET /elimination/bowel-movements` returns: `log_time`, and no
// `time` field — which is the whole reason the old code fell back to the date.
const bowel = (id, log_time, notes = 'Regular') => ({
  id, user_id: 63, log_date: '2026-10-14', log_time, notes,
});

describe('elimination events carry the time the patient logged', () => {
  it('reads log_time, which is the only time field these rows have', () => {
    const [a, b] = buildEliminationEvents(
      [bowel(1, '00:40:00'), bowel(2, '10:30:00')], []);
    expect(a.logTime).toBe('00:40');
    expect(b.logTime).toBe('10:30');
  });

  it('never derives a time from the DATE', () => {
    // The old code did `new Date(e.log_date).toTimeString()`, and an ISO
    // date-only string is parsed as UTC MIDNIGHT then printed LOCAL — so in
    // EDT every event read 20:00 and rendered "08:00 PM". The time shown was a
    // function of the viewer's timezone rather than of the event.
    const [e] = buildEliminationEvents([bowel(1, '00:40:00')], []);
    expect(e.logTime).not.toBe('20:00');
    expect(e.logTime).toBe('00:40');
  });

  it('two events at different times do not collapse to one value', () => {
    // The symptom exactly as it was reported.
    const events = buildEliminationEvents(
      [bowel(1, '00:40:00'), bowel(2, '10:30:00')], []);
    const times = events.map(e => e.logTime);
    expect(new Set(times).size).toBe(2);
  });

  it('a row with NO time says so rather than inventing one', () => {
    // §3av measured the cost of the opposite choice on 3,662 intradialytic
    // readings: an import defaulted a missing timestamp to midnight, and "the
    // measurement is real and the time is not" had to be reconstructed from
    // the population afterwards.
    const [e] = buildEliminationEvents([bowel(1, null)], []);
    expect(e.logTime).toBeNull();
  });

  it('sorts by the real time, and untimed rows never claim the top of the day',
    () => {
      const events = buildEliminationEvents(
        [bowel(3, null), bowel(2, '10:30:00'), bowel(1, '00:40:00')], []);
      expect(events.map(e => e.logTime)).toEqual(['00:40', '10:30', null]);
    });

  it('the computed fields are not clobbered by the row', () => {
    // `...e` used to come AFTER the computed keys, so anything the API grew
    // with a matching name would silently overrule this function. The spread
    // goes first now.
    const rogue = { ...bowel(1, '00:40:00'), type: 'WRONG', logTime: 'WRONG' };
    const [e] = buildEliminationEvents([rogue], []);
    expect(e.type).toBe('Bowel');
    expect(e.logTime).toBe('00:40');
  });

  it('vomiting rows are read the same way', () => {
    // The same line carried the same bug for both models, and `VomitingLog`
    // also has `log_time`.
    const [e] = buildEliminationEvents([], [
      { id: 9, log_date: '2026-10-14', log_time: '14:05:00', contents: 'bile' },
    ]);
    expect(e.type).toBe('Vomiting');
    expect(e.logTime).toBe('14:05');
    expect(e.note).toBe('bile');
  });

  it('accepts HH:MM as well as HH:MM:SS', () => {
    const [e] = buildEliminationEvents([bowel(1, '09:05')], []);
    expect(e.logTime).toBe('09:05');
  });

  it('handles an empty record without inventing an event', () => {
    expect(buildEliminationEvents([], [])).toEqual([]);
    expect(buildEliminationEvents()).toEqual([]);
  });
});

describe('what the patient actually reads', () => {
  it('renders the logged times, not the viewer timezone', async () => {
    // The end-to-end assertion. `logTime` being right is not enough — the bug
    // lived in the COMPOSITION, where a correct date met a formatter that
    // turned it into "08:00 PM".
    const { buildEliminationEvents: build, fmtTime } =
      await import('../pages/Dashboard');
    const rendered = build(
      [bowel(1, '00:40:00'), bowel(2, '10:30:00')], []
    ).map(e => (e.logTime ? fmtTime(e.logTime) : 'time not recorded'));

    expect(rendered).toEqual(['12:40 AM', '10:30 AM']);
    expect(rendered).not.toContain('08:00 PM');   // the reported symptom
  });

  it('says so when the row carries no time', async () => {
    const { buildEliminationEvents: build, fmtTime } =
      await import('../pages/Dashboard');
    const [e] = build([bowel(1, null)], []);
    expect(e.logTime ? fmtTime(e.logTime) : 'time not recorded')
      .toBe('time not recorded');
  });
});
