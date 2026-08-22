import { describe, it, expect } from 'vitest';
import { parseDrugs, formatDrugs } from '../components/DrugsAdministered';

/**
 * Structured capture writes back into the SAME free-text column that already
 * holds 1,964 historical rows. If the round-trip is not exact, a flowsheet
 * opened and re-saved silently rewrites a decade of drug history.
 *
 * The cases are from the real corpus, not invented.
 */

describe('parseDrugs', () => {
  it('does not split on a semicolon inside parentheses', () => {
    // One catheter-lock entry, not two. A plain split(';') invents a drug
    // called "3ml Arterial)".
    const rows = parseDrugs(
      'Sodium Citrate (12 ml  Venous; 3ml Arterial); Epogene (3,000 SQ); Venofer (100 mg)'
    );
    expect(rows.map((r) => r.name)).toEqual(['Sodium Citrate', 'Epogene', 'Venofer']);
    expect(rows[0].dose).toBe('12 ml  Venous; 3ml Arterial');
  });

  it('reads a drug with no dose', () => {
    expect(parseDrugs('Epogene')).toEqual([{ name: 'Epogene', dose: '' }]);
  });

  it('is empty for empty input', () => {
    expect(parseDrugs('')).toEqual([]);
    expect(parseDrugs(null)).toEqual([]);
  });
});

describe('formatDrugs', () => {
  it('omits the parentheses when there is no dose', () => {
    expect(formatDrugs([{ name: 'Epogene', dose: '' }])).toBe('Epogene');
  });

  it('drops a dose with no drug — that is not a fact', () => {
    expect(formatDrugs([{ name: '', dose: '100 mg' }])).toBe('');
  });

  it('strips parentheses from input so the round-trip cannot be broken', () => {
    // The dose delimiter is the parenthesis; letting one through the name
    // would make the value re-parse into something else entirely.
    expect(formatDrugs([{ name: 'Epogene (extra)', dose: '3,000 SQ' }]))
      .toBe('Epogene extra (3,000 SQ)');
  });
});

describe('round-trip against real corpus values', () => {
  it.each([
    'Epogene',
    'Epogene (20,000 SQ)',
    'Venofer (100 mg)',
    'Doxercalcif (4mcg)',
    'Sodium Citrate (1.8 ml x 2); Epogene (3,000 SQ); Venofer (100 mg)',
    'Sodium Citrate (2.5 ml x 2); Epogene (3,000 SQ); Venofer (100 mg); Doxercalcif (2 mcg)',
  ])('survives open-and-save unchanged: %s', (stored) => {
    // Opening a flowsheet and saving it without edits must not rewrite history.
    expect(formatDrugs(parseDrugs(stored))).toBe(stored);
  });
});
