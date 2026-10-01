import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { emptyForm } from '../pages/Hemodialysis';

/**
 * A field the flowsheet SUBMITS but never DECLARES is write-only — and it
 * erases itself on the next save.
 *
 * `startEdit` loads a stored session by copying only the keys `emptyForm()`
 * defines:
 *
 *     const f = emptyForm();
 *     Object.keys(f).forEach(k => { if (session[k] != null) f[k] = session[k]; });
 *
 * so a field absent from that object is never loaded back. The input renders
 * empty with its placeholder showing — which reads as "nothing was ever
 * recorded here" — and on submit the key is still posted, as null, because
 * `formData` holds no value for it. The backend's
 * `model_dump(exclude_unset=True)` cannot filter an explicitly-sent null, so
 * `setattr(db_session, field, None)` overwrites the stored value.
 *
 * The second save of a session therefore DESTROYS the field. That is strictly
 * worse than never saving it, because the first save looked like it worked.
 *
 * Found 2026-10-01 on a real session: Machine Total Time blank on the form and
 * "—" on the printed report — which that report's own footer defines as NOT
 * RECORDED — while Clock Time computed 305 min from the same row. Two fields
 * were affected, `machine_total_time_minutes` and `saline_added_ml`, and the
 * second is why this is a class guard and not two added keys: one omission is
 * an oversight, two is a shape that will recur.
 *
 * §3ar — a control that sets a flag nothing observes does nothing; here the
 * patient's typing is the flag. §3av — the web flowsheet silently eating
 * clinical input, for the second time. §3aa — the empty field and the em-dash
 * are an ERROR wearing an empty state's clothes.
 */

/* Resolved from the vite root, NOT from `import.meta.url`.
 *
 * These tests run under jsdom, where `import.meta.url` is an http:// URL — so
 * `new URL('../pages/…', import.meta.url)` gives an http URL and readFileSync
 * throws "The URL must be of scheme file" at COLLECTION time. The suite then
 * reports the file as a failed SUITE rather than a failed assertion, which
 * looks like a red guard while proving nothing: 266 tests passed beside it and
 * not one line of this file executed. */
const SOURCE = fs.readFileSync(
  path.resolve(process.cwd(), 'src/pages/Hemodialysis.jsx'), 'utf8');

/**
 * Every field name the form binds, reads or posts.
 *
 * Line comments are stripped first: this file documents the fields it fixed by
 * name, and a guard that counts its own prose as evidence measures nothing.
 */
function fieldsTheFormTouches(src) {
  const code = src.split('\n').map((l) => l.replace(/\/\/.*$/, '')).join('\n');
  const names = new Set();
  for (const m of code.matchAll(/formData\.([a-z_0-9]+)/g)) names.add(m[1]);
  for (const m of code.matchAll(/set\('([a-z_0-9]+)'\)/g)) names.add(m[1]);
  for (const m of code.matchAll(/payload\.([a-z_0-9]+)/g)) names.add(m[1]);
  return [...names].sort();
}

describe('the flowsheet declares every field it submits', () => {
  it('finds the fields at all — a scan that matches nothing passes forever', () => {
    // The guard this replaces was written with `^\s+[a-z_0-9]+:` and so read
    // only the FIRST key on each line, while emptyForm declares most of its
    // fields several to a line. It reported 38 declared keys against 77 real
    // ones and produced a 40-item list of "defects" that were plainly declared.
    // A scan is evidence only once it is shown to see what it claims to.
    const touched = fieldsTheFormTouches(SOURCE);
    expect(touched.length).toBeGreaterThan(60);
    expect(touched).toContain('machine_total_time_minutes');
    expect(Object.keys(emptyForm()).length).toBeGreaterThan(60);
  });

  it('declares every field it binds or posts, so nothing is write-only', () => {
    const declared = new Set(Object.keys(emptyForm()));
    const undeclared = fieldsTheFormTouches(SOURCE).filter((f) => !declared.has(f));

    expect(undeclared, [
      'These fields are rendered and POSTed but are not in emptyForm().',
      '',
      'startEdit copies only the keys emptyForm() declares, so each of these is',
      'never loaded back from a saved session — and handleSubmit still posts it',
      'as null, overwriting whatever was stored. The field is write-only and the',
      'second save of a session destroys it.',
      '',
      'Add each to emptyForm() with the group it belongs to.',
    ].join('\n')).toEqual([]);
  });
});

describe('the two fields this guard was written for', () => {
  /* Named individually as well as caught by the scan above: these are the ones
     observed losing a real patient's data, and a named case says what broke
     when the generic assertion goes red for some other reason. */
  it.each([
    ['machine_total_time_minutes', 447],   // 7:27 off the machine
    ['saline_added_ml', 250],              // boluses + rinseback
  ])('%s survives being loaded from a stored session', (field, stored) => {
    const declared = Object.keys(emptyForm());
    expect(declared).toContain(field);

    // Exactly what startEdit does with a session off the API.
    const f = emptyForm();
    const session = { [field]: stored };
    Object.keys(f).forEach((k) => {
      if (k === 'clinical_notes') return;
      if (session[k] != null) f[k] = session[k];
    });
    expect(f[field]).toBe(stored);
  });

  it('a machine time loaded back still reads as the clock the machine showed', () => {
    // The round trip only matters if the value stays usable: 447 must still be
    // the 7:27 the patient read off the machine, not a seven-minute treatment.
    const f = emptyForm();
    const session = { machine_total_time_minutes: 447 };
    Object.keys(f).forEach((k) => { if (session[k] != null) f[k] = session[k]; });
    expect(f.machine_total_time_minutes).toBe(447);
  });
});
