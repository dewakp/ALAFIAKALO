import { describe, it, expect } from 'vitest';
import {
  normalizeTime, readingHasData, parseMachineTime, formatMachineTime,
} from '../pages/Hemodialysis';

/**
 * The form was silently eating intradialytic readings.
 *
 * A row whose time did not normalise was `continue`d past in the save loop, so
 * it was never POSTed and simply vanished — no error, nothing in the list
 * afterwards. It bit the FIRST reading most often, because the form seeds one
 * blank row and a half-typed or empty time is exactly what that row has.
 */

describe('normalizeTime', () => {
  it('accepts a single-digit hour, which is what people type', () => {
    // The old pattern demanded two digits, so this returned null and the
    // reading it belonged to was dropped.
    expect(normalizeTime('9:30')).toBe('09:30');
    expect(normalizeTime('7:05')).toBe('07:05');
  });

  it('still accepts the padded and seconds forms', () => {
    expect(normalizeTime('09:30')).toBe('09:30');
    expect(normalizeTime('14:30:00')).toBe('14:30');
    expect(normalizeTime(' 14:30 ')).toBe('14:30');
    expect(normalizeTime('00:00:00')).toBe('00:00');
  });

  it('refuses what is genuinely not a time', () => {
    expect(normalizeTime('')).toBeNull();
    expect(normalizeTime('—')).toBeNull();
    expect(normalizeTime('25:00')).toBeNull();
    expect(normalizeTime('9:70')).toBeNull();
    expect(normalizeTime(null)).toBeNull();
  });
});

describe('readingHasData — what must never be dropped silently', () => {
  it('an untouched row holds nothing', () => {
    expect(readingHasData({ reading_time: '', systolic_bp: '', pulse: '' })).toBe(false);
  });

  it('a row with a blood pressure holds a clinical observation', () => {
    expect(readingHasData({ reading_time: '', systolic_bp: '140', pulse: '' })).toBe(true);
  });

  it('a time alone is not data — it is the thing the row is missing', () => {
    // Otherwise an empty row with a time typed into it would block the save.
    expect(readingHasData({ reading_time: '09:30' })).toBe(false);
  });

  it('ignores identifiers', () => {
    expect(readingHasData({ id: 12, session_id: 3, systolic_bp: '' })).toBe(false);
  });

  it('counts a remark, because a nurse wrote it down for a reason', () => {
    expect(readingHasData({ remarks: 'cramping' })).toBe(true);
  });
});

describe('parseMachineTime — the machine shows HR:MIN', () => {
  it('reads the machine format', () => {
    expect(parseMachineTime('7:27')).toBe(447);
    expect(parseMachineTime('4:00')).toBe(240);
    expect(parseMachineTime('0:45')).toBe(45);
  });

  it('still reads bare minutes, which is every stored value', () => {
    expect(parseMachineTime('447')).toBe(447);
    expect(parseMachineTime(447)).toBe(447);
  });

  it('never reads "7:27" as 7', () => {
    // parseInt would, and would record a seven-minute treatment — a figure
    // Kt/V is computed from.
    expect(parseMachineTime('7:27')).not.toBe(7);
  });

  it('refuses what it cannot read rather than storing a wrong number', () => {
    expect(parseMachineTime('7:99')).toBeNull();
    expect(parseMachineTime('abc')).toBeNull();
    expect(parseMachineTime('')).toBeNull();
    expect(parseMachineTime(null)).toBeNull();
  });

  it('round-trips back to the machine format', () => {
    expect(formatMachineTime(447)).toBe('7:27');
    expect(formatMachineTime(240)).toBe('4:00');
    expect(formatMachineTime(parseMachineTime('7:27'))).toBe('7:27');
  });
});
