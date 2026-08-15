import { describe, it, expect } from 'vitest';
import { newClinicalNote } from '../pages/Hemodialysis';

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
