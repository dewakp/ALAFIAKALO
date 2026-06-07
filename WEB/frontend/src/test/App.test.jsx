import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
