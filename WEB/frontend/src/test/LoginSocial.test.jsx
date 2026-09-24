import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Social sign-in, with Firebase out of the path.
 *
 * What shipped before: "Sign in with Apple" was drawn unconditionally while
 * Apple had never been configured as a provider at all, and the server-side
 * exchange answered 503 because no credential was ever mounted. Both buttons
 * were controls that could not work, and the production screenshot showed
 * `Firebase: Error (auth/internal-error)` sitting above an untouched email form.
 *
 * The rules these pin:
 *   * Apple is offered ONLY when a Services ID is configured — no dead button.
 *   * Google's credential arrives through Google's OWN button, as a callback.
 *   * Both exchange the PROVIDER's token at /auth/oidc, naming the provider.
 *   * A blocked provider script says so rather than leaving silence.
 */

// `vi.mock` factories are hoisted above every top-level declaration, so the
// doubles have to be hoisted too — referencing an ordinary `const` from inside
// one throws "Cannot access 'oidc' before initialization".
const oidc = vi.hoisted(() => ({
  renderGoogleButton: vi.fn(),
  signInWithApple: vi.fn(),
  isAppleConfigured: vi.fn(),
  oidcErrorMessage: vi.fn(),
}));
vi.mock('../services/oidc', () => oidc);

const auth = vi.hoisted(() => ({ loginWithOIDC: vi.fn() }));
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    login: vi.fn(), loginWithOIDC: auth.loginWithOIDC, user: null, loading: false,
  }),
  AuthProvider: ({ children }) => children,
}));

import Login from '../pages/Login';

const renderLogin = () =>
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  );

describe('social sign-in goes straight to the provider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    oidc.renderGoogleButton.mockImplementation(async () => () => {});
    oidc.signInWithApple.mockResolvedValue('apple-id-token');
    oidc.isAppleConfigured.mockReturnValue(true);
    oidc.oidcErrorMessage.mockImplementation((err, fallback) =>
      err?.message === 'script-blocked'
        ? 'The sign-in provider could not be loaded.'
        : fallback);
    auth.loginWithOIDC.mockResolvedValue({});
  });

  it('asks Google to render its own button', async () => {
    renderLogin();
    await waitFor(() => expect(oidc.renderGoogleButton).toHaveBeenCalled());
    // A real element to draw into, not a detached node.
    expect(oidc.renderGoogleButton.mock.calls[0][0]).toBeInstanceOf(HTMLElement);
  });

  it("exchanges Google's credential for our session, naming the provider", async () => {
    renderLogin();
    await waitFor(() => expect(oidc.renderGoogleButton).toHaveBeenCalled());

    // Google calls back with the credential; there is no click to simulate.
    const onToken = oidc.renderGoogleButton.mock.calls[0][1];
    onToken('google-id-token');

    await waitFor(() =>
      expect(auth.loginWithOIDC).toHaveBeenCalledWith('google', 'google-id-token'));
  });

  it('signs in with Apple from our own button', async () => {
    renderLogin();
    fireEvent.click(screen.getByRole('button', { name: /apple/i }));

    await waitFor(() => expect(oidc.signInWithApple).toHaveBeenCalled());
    await waitFor(() =>
      expect(auth.loginWithOIDC).toHaveBeenCalledWith('apple', 'apple-id-token'));
  });

  it('does NOT offer Apple when no Services ID is configured', () => {
    oidc.isAppleConfigured.mockReturnValue(false);
    renderLogin();

    // The state production was actually in: a button that could never work.
    expect(screen.queryByRole('button', { name: /apple/i })).not.toBeInTheDocument();
  });

  it('notes a blocked provider quietly — NOT as a sign-in error', async () => {
    // Reported from production: an extension blocks accounts.google.com, and
    // this was rendered in the form's error slot — red, above the email field —
    // telling someone whose email login worked perfectly that sign-in was
    // broken. A blocked optional provider is an unavailable extra, not a
    // failure the user must act on.
    oidc.renderGoogleButton.mockImplementation(async (_el, _onToken, onError) => {
      onError(new Error('script-blocked'));
      return () => {};
    });

    renderLogin();

    expect(await screen.findByText(/isn't available in this browser/i)).toBeInTheDocument();
    // The form's error path is for a FAILED SIGN-IN. This must never reach it.
    expect(oidc.oidcErrorMessage).not.toHaveBeenCalled();
  });

  it('reports a refusal from our own API rather than a provider message', async () => {
    const err = new Error('request failed');
    err.response = { status: 403, data: { detail: 'That account is not permitted.' } };
    auth.loginWithOIDC.mockRejectedValueOnce(err);

    renderLogin();
    fireEvent.click(screen.getByRole('button', { name: /apple/i }));

    expect(await screen.findByText(/not permitted/i)).toBeInTheDocument();
  });
});
