import { Component } from 'react';

/**
 * App-wide error boundary. Prevents a blank white screen when a render throws
 * or a lazy-loaded route chunk fails to load (which happens when the app is
 * redeployed with new asset hashes while a stale index.html is cached).
 *
 * - Chunk-load failures self-heal: reload to fetch the fresh assets, rate
 *   limited so a genuinely broken build cannot loop.
 * - Any other render error shows a recoverable message (with the error text,
 *   which is invaluable for diagnosing field issues) instead of a blank page.
 */
const CHUNK_ERROR_RE =
  /Loading chunk|loading dynamically imported module|Failed to fetch dynamically imported module|Importing a module script failed/i;
const RELOAD_FLAG = 'alafia_chunk_reloaded_at';
// Guard against a RELOAD LOOP, not against reloading twice in a session.
//
// This used to be a once-per-session flag, so the first deploy healed and every
// deploy after it showed the error page instead — the flag was set and never
// expired. On a day with several deploys that is most of them. A short window
// still makes a genuine loop impossible (a broken build cannot reload faster
// than this) while letting each new deploy self-heal.
const RELOAD_COOLDOWN_MS = 30_000;

function reloadedRecently() {
  try {
    const at = Number(sessionStorage.getItem(RELOAD_FLAG) || 0);
    return at > 0 && Date.now() - at < RELOAD_COOLDOWN_MS;
  } catch {
    return false;   // private mode / storage blocked: healing beats erroring
  }
}

export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    const msg = String(error?.message || error);
    if (CHUNK_ERROR_RE.test(msg) && !reloadedRecently()) {
      // A chunk failure means the app was redeployed under this tab: the loaded
      // index.html names asset hashes that no longer exist. Reload to pull the
      // fresh ones.
      try { sessionStorage.setItem(RELOAD_FLAG, String(Date.now())); } catch { /* ignore */ }
      window.location.reload();
    }
  }

  handleReload = () => {
    try { sessionStorage.removeItem(RELOAD_FLAG); } catch { /* ignore */ }
    window.location.reload();
  };

  render() {
    if (this.state.error) {
      return (
        <div style={{ maxWidth: 560, margin: '4rem auto', padding: '2rem', textAlign: 'center' }}>
          <h2 style={{ marginBottom: '.5rem' }}>Something went wrong</h2>
          <p style={{ color: 'var(--color-text-secondary, #666)', marginBottom: '1.25rem' }}>
            This page hit an error. If the app was just updated, reloading usually fixes it.
          </p>
          <button className="btn btn-primary" onClick={this.handleReload}>Reload</button>
          <pre style={{
            textAlign: 'left', marginTop: '1.5rem', padding: '0.75rem',
            background: 'rgba(0,0,0,.05)', borderRadius: 8, overflow: 'auto',
            fontSize: '.72rem', color: 'var(--color-danger, #b91c1c)', whiteSpace: 'pre-wrap',
          }}>
            {String(this.state.error?.message || this.state.error)}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}
