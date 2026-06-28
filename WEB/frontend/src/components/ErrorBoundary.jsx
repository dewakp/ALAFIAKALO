import { Component } from 'react';

/**
 * App-wide error boundary. Prevents a blank white screen when a render throws
 * or a lazy-loaded route chunk fails to load (which happens when the app is
 * redeployed with new asset hashes while a stale index.html is cached).
 *
 * - Chunk-load failures self-heal: reload once to fetch the fresh assets.
 * - Any other render error shows a recoverable message (with the error text,
 *   which is invaluable for diagnosing field issues) instead of a blank page.
 */
const CHUNK_ERROR_RE =
  /Loading chunk|loading dynamically imported module|Failed to fetch dynamically imported module|Importing a module script failed/i;
const RELOAD_FLAG = 'alafia_chunk_reloaded';

export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    const msg = String(error?.message || error);
    if (CHUNK_ERROR_RE.test(msg) && !sessionStorage.getItem(RELOAD_FLAG)) {
      // First chunk failure after a deploy → reload once to pull fresh assets.
      sessionStorage.setItem(RELOAD_FLAG, '1');
      window.location.reload();
    }
  }

  handleReload = () => {
    sessionStorage.removeItem(RELOAD_FLAG);
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
