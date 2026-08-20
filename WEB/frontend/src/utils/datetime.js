// Date/time helpers — display EVERYTHING in the user's machine locale + timezone.
//
// The backend stores timestamps in UTC. Some columns serialize with a 'Z'/offset,
// some are naive (no designator). `new Date('2026-07-22T01:00:00')` would read a
// naive string as LOCAL time, which makes UTC values "race ahead" of the user's
// clock. So we normalize: strings without a timezone are treated as UTC, and every
// formatter uses the browser locale (toLocale*), never a hardcoded zone.

/** A naive datetime at exactly midnight — a calendar date in a datetime column. */
const NAIVE_MIDNIGHT = /^(\d{4}-\d{2}-\d{2})T00:00(?::00(?:\.0+)?)?$/;

/** Parse a server value to a Date, interpreting naive (no-offset) strings as UTC.
 *
 * With one exception, and it is the reason a treatment entered on the 19th was
 * reported as the 18th:
 *
 * Some columns are *calendar dates* stored in a DATETIME column —
 * `therapy_sessions.scheduled_date`, `condition_metrics.measured_date`. They
 * serialize as `2026-08-19T00:00:00`, look exactly like a naive instant, and so
 * were parsed as midnight UTC. Rendered anywhere west of UTC that is the
 * *previous day*: 8/18 in New York, and worse the further west you go.
 *
 * A real instant landing on exactly 00:00:00.000 is vanishingly rare; a date
 * stored as midnight is routine. So exact midnight is read as a calendar date
 * and kept as written, while anything carrying a real time of day is still
 * treated as UTC.
 */
export function parseServer(v) {
  if (v == null || v === '') return null;
  if (v instanceof Date) return v;
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return new Date(`${s}T00:00:00`); // date-only → local midnight
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(s)) return new Date(s);           // already has a timezone
  const calendarDate = NAIVE_MIDNIGHT.exec(s);
  if (calendarDate) return new Date(`${calendarDate[1]}T00:00:00`);    // date, not an instant
  return new Date(`${s}Z`);                                           // naive datetime → assume UTC
}

const _ok = (d) => d instanceof Date && !Number.isNaN(d.getTime());

/** Locale date + time, e.g. "7/22/2026, 3:45 AM" (machine locale + timezone). */
export function fmtDateTime(v, opts) {
  const d = parseServer(v);
  return _ok(d) ? d.toLocaleString(undefined, opts) : '';
}

/** Locale date only. */
export function fmtDate(v, opts) {
  const d = parseServer(v);
  return _ok(d) ? d.toLocaleDateString(undefined, opts) : '';
}

/** Locale time only (defaults to HH:MM). */
export function fmtTime(v, opts = { hour: '2-digit', minute: '2-digit' }) {
  const d = parseServer(v);
  return _ok(d) ? d.toLocaleTimeString(undefined, opts) : '';
}

/** YYYY-MM-DD in the LOCAL timezone — for <input type="date"> and calendars. */
export function toDateInput(v) {
  const d = v instanceof Date ? v : parseServer(v);
  if (!_ok(d)) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Today's date, LOCAL, as YYYY-MM-DD. Use instead of new Date().toISOString(). */
export const localToday = () => toDateInput(new Date());

/** YYYY-MM-DDTHH:MM (local) — for <input type="datetime-local">. */
export function toDateTimeInput(v) {
  const d = v instanceof Date ? v : parseServer(v);
  if (!_ok(d)) return '';
  const p = (n) => String(n).padStart(2, '0');
  return `${toDateInput(d)}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Current LOCAL time as HH:MM — for <input type="time"> defaults. */
export function localNowTime() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** Format a CALENDAR DATE — a value whose date part is the whole meaning.
 *
 * `therapy_sessions.scheduled_date` and friends are dates that happen to live
 * in a datetime column. The safe way to render them is to never let a Date
 * object near the timezone question: take the YYYY-MM-DD prefix and build the
 * date from its parts.
 *
 * This is deliberately independent of how any given engine parses
 * "2026-08-19T00:00:00" — ES5 said UTC, ES2015 says local, and a value that
 * arrives with a 'Z' is a third case again. iOS and Android already read these
 * with prefix(10)/take(10), which is why neither ever showed the wrong day.
 */
export function fmtCalendarDate(v, opts) {
  if (v == null || v === '') return '';
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v));
  if (!match) return fmtDate(v, opts);
  const [, y, m, d] = match;
  // Month is 0-based; constructing from parts is always local, never shifted.
  const local = new Date(Number(y), Number(m) - 1, Number(d));
  return local.toLocaleDateString(undefined, opts);
}
