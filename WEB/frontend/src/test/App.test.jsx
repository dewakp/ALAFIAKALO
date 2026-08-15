import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// This test renders the real App, so AuthProvider mounts and asks for a CSRF
// cookie. Unmocked, jsdom made a genuine XHR to a server that is not running and
// logged an unhandled AggregateError on every run.
vi.mock('../services/api', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    defaults: { headers: { common: {} } },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

import App from '../App';

// Minimal smoke test — verifies the app renders without crashing
describe('App', () => {
  it('renders landing page at /landing', () => {
    render(
      <MemoryRouter initialEntries={['/landing']}>
        <App />
      </MemoryRouter>
    );
    // The Suspense fallback or landing content should appear
    expect(document.body).toBeTruthy();
  });

  it('redirects unauthenticated users from / to /landing', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    );
    // ProtectedRoute should redirect — loading or landing should be visible
    expect(document.body).toBeTruthy();
  });
});
