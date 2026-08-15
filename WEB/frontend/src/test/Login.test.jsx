import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mock the API module before importing the component
vi.mock('../services/api', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    defaults: { headers: { common: {} } },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

// Login calls useAuth(), which throws without a provider. Mocking the context
// is preferable to wrapping in the real AuthProvider here: the provider fetches
// a CSRF cookie and a session on mount, none of which this render is testing.
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ login: vi.fn(), loginWithFirebase: vi.fn(), user: null, loading: false }),
  AuthProvider: ({ children }) => children,
}));

import Login from '../pages/Login';

describe('Login Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders login form with email and password fields', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    // Check for input fields by role or placeholder
    const inputs = document.querySelectorAll('input');
    expect(inputs.length).toBeGreaterThanOrEqual(2);
  });

  it('renders a submit button', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );
    const buttons = document.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });
});
