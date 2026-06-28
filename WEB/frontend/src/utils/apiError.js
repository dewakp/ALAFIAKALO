/**
 * Turn any axios/FastAPI error into a safe, human-readable string.
 *
 * FastAPI validation errors return `detail` as an array of objects
 * ({type, loc, msg, input}). Rendering that array directly as a React child
 * throws "Objects are not valid as a React child" (React #31). Always run error
 * details through this before putting them in state/JSX.
 */
export function apiErrorMessage(err, fallback = 'Something went wrong.') {
  const detail = err?.response?.data?.detail ?? err?.response?.data;

  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    const parts = detail
      .map((e) => {
        if (typeof e === 'string') return e;
        const field = Array.isArray(e?.loc) ? e.loc[e.loc.length - 1] : null;
        const msg = e?.msg || '';
        return field && field !== 'body' ? `${field}: ${msg}` : msg;
      })
      .filter(Boolean);
    if (parts.length) return parts.join('; ');
  }

  if (detail && typeof detail === 'object') {
    return detail.msg || detail.message || fallback;
  }

  return err?.message || fallback;
}
