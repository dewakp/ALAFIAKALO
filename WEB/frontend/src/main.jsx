import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import * as Sentry from '@sentry/react';
import './i18n';  // Initialize i18n before App
import App from './App';
import './index.css';
import { ThemeProvider } from './context/ThemeContext';

// Sentry: initialise only when DSN is configured (production)
const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;
if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
    sendDefaultPii: false,  // Never send PII
    integrations: [
      Sentry.browserTracingIntegration(),
    ],
  });
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>
);

// Vite fires this when a lazy chunk's PRELOAD fails, which can happen before any
// component renders — so the error boundary never sees it and the user gets a
// dead page rather than the recovery screen. Same cause as the boundary's chunk
// handling: the app was redeployed under an open tab.
window.addEventListener('vite:preloadError', (event) => {
  const KEY = 'alafia_chunk_reloaded_at';
  try {
    const at = Number(sessionStorage.getItem(KEY) || 0);
    if (at > 0 && Date.now() - at < 30_000) return;   // loop guard
    sessionStorage.setItem(KEY, String(Date.now()));
  } catch { /* storage blocked — healing still beats a dead page */ }
  event.preventDefault();
  window.location.reload();
});
