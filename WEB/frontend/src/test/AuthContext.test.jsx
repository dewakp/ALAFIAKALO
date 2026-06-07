import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider, useAuth } from '../context/AuthContext';

// ── Mock api module ──────────────────────────────────────────────────────────

const mockApi = {
  get: vi.fn(),
  post: vi.fn(),
  defaults: { headers: { common: {} } },
  interceptors: {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  },
};

vi.mock('../services/api', () => ({ default: mockApi }));

// ── Helper: render with AuthProvider ─────────────────────────────────────────

function TestConsumer() {
  const { user, loading, login, logout } = useAuth();
  if (loading) return <div>loading</div>;
  if (!user) return (
    <div>
      <span data-testid="no-user">not logged in</span>
      <button onClick={() => login('a@b.com', 'pass')}>login</button>
    </div>
  );
  return (
    <div>
      <span data-testid="user-email">{user.email}</span>
      <button onClick={logout}>logout</button>
    </div>
  );
}

function renderWithAuth() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    </MemoryRouter>
  );
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    // Default: CSRF cookie call succeeds; no stored token → /users/me not called
    mockApi.get.mockResolvedValue({ data: {} });
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('shows not-logged-in state when no token in localStorage', async () => {
    renderWithAuth();
    await waitFor(() => screen.getByTestId('no-user'));
    expect(screen.getByTestId('no-user')).toBeTruthy();
  });

  it('loads user from API when token exists in localStorage', async () => {
    localStorage.setItem('token', 'fake-token');
    mockApi.get.mockImplementation((url) => {
      if (url.includes('/users/me')) {
        return Promise.resolve({ data: { id: 1, email: 'stored@example.com' } });
      }
      return Promise.resolve({ data: {} });
    });

    renderWithAuth();
    await waitFor(() => screen.getByTestId('user-email'));
    expect(screen.getByTestId('user-email').textContent).toBe('stored@example.com');
  });

  it('clears token and shows logged-out if /users/me fails', async () => {
    localStorage.setItem('token', 'bad-token');
    mockApi.get.mockImplementation((url) => {
      if (url.includes('/users/me')) return Promise.reject(new Error('401'));
      return Promise.resolve({ data: {} });
    });

    renderWithAuth();
    await waitFor(() => screen.getByTestId('no-user'));
    expect(localStorage.getItem('token')).toBeNull();
  });

  it('login() stores token and loads user', async () => {
    mockApi.post.mockResolvedValueOnce({ data: { access_token: 'new-token' } });
    mockApi.get.mockImplementation((url) => {
      if (url.includes('/users/me')) {
        return Promise.resolve({ data: { id: 2, email: 'a@b.com' } });
      }
      return Promise.resolve({ data: {} });
    });

    renderWithAuth();
    await waitFor(() => screen.getByText('login'));
    await userEvent.click(screen.getByText('login'));

    await waitFor(() => screen.getByTestId('user-email'));
    expect(screen.getByTestId('user-email').textContent).toBe('a@b.com');
    expect(localStorage.getItem('token')).toBe('new-token');
  });

  it('logout() clears token and user', async () => {
    localStorage.setItem('token', 'tok');
    mockApi.get.mockImplementation((url) => {
      if (url.includes('/users/me')) {
        return Promise.resolve({ data: { id: 3, email: 'bye@example.com' } });
      }
      return Promise.resolve({ data: {} });
    });

    renderWithAuth();
    await waitFor(() => screen.getByTestId('user-email'));
    await userEvent.click(screen.getByText('logout'));

    await waitFor(() => screen.getByTestId('no-user'));
    expect(localStorage.getItem('token')).toBeNull();
  });

  it('useAuth throws outside AuthProvider', () => {
    const BadConsumer = () => { useAuth(); return null; };
    expect(() => render(<BadConsumer />)).toThrow('useAuth must be used within AuthProvider');
  });
});
