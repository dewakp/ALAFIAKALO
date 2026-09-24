import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Someone who already has an account used to get "a verification link has been
 * sent" — for mail that by definition was never sent — and no way to learn that
 * the thing to do was sign in. The backend now answers 409 and says so.
 *
 * The message has to INTERRUPT. Rendered into the inline `.auth-error` strip it
 * sits above a long form, off-screen on a phone by the time the button at the
 * bottom is pressed, so the form appears to do nothing to exactly the person
 * who is already confused.
 */

vi.mock('../services/api', () => ({
  default: { post: vi.fn(), get: vi.fn(), defaults: { headers: { common: {} } },
             interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } } },
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: null, loading: false }),
  AuthProvider: ({ children }) => children,
}));

import api from '../services/api';
import SignupFlow from '../pages/SignupFlow';

const renderFlow = () =>
  render(
    <MemoryRouter>
      <SignupFlow />
    </MemoryRouter>,
  );

// Queried by id, not by label. The labels are translated — asserting on English
// copy makes this fail the day someone runs it in another language — and
// PasswordInput renders both a label and a show/hide control, so /password/i
// matches more than one element.
function fillDetails() {
  const set = (id, value) =>
    fireEvent.change(document.getElementById(id), { target: { value } });
  set('su-first', 'Ada');
  set('su-last', 'Demo');
  set('su-email', 'ada@example.com');
  set('su-dob', '1980-01-01');
  set('su-password', 'a-long-enough-password');
}

const submit = () => fireEvent.submit(document.querySelector('form'));

const refusal = (status, detail) => {
  const err = new Error('request failed');
  err.response = { status, data: { detail } };
  return err;
};

describe('signing up with an address that already has an account', () => {
  beforeEach(() => vi.clearAllMocks());

  it('interrupts with a dialog rather than an inline strip', async () => {
    api.post.mockRejectedValueOnce(refusal(409,
      'An account already exists for this email address. Try signing in, or '
      + 'reset your password if you have forgotten it.'));

    renderFlow();
    fillDetails();
    submit();

    const dialog = await screen.findByRole('alertdialog');
    // The server's own sentence, not a generic "something went wrong".
    expect(dialog).toHaveTextContent(/already exists for this email address/i);
  });

  it('offers a way forward, because a refusal with no route sends them back to the same form', async () => {
    api.post.mockRejectedValueOnce(refusal(409, 'An account already exists.'));

    renderFlow();
    fillDetails();
    submit();

    const dialog = await screen.findByRole('alertdialog');
    const signIn = within(dialog).getByRole('link');
    expect(signIn).toHaveAttribute('href', '/login');
  });

  it('shows any other registration error the same way, minus the sign-in route', async () => {
    api.post.mockRejectedValueOnce(refusal(422, 'Date of birth is required to create an account.'));

    renderFlow();
    fillDetails();
    submit();

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent(/date of birth is required/i);
    // Sending someone to sign in when the problem was their date of birth
    // would be worse than saying nothing.
    expect(within(dialog).queryByRole('link')).not.toBeInTheDocument();
  });

  it('closes on dismiss so the form can be corrected', async () => {
    api.post.mockRejectedValueOnce(refusal(409, 'An account already exists.'));

    renderFlow();
    fillDetails();
    submit();

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button'));
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  });

  it('does not open on a successful start', async () => {
    api.post.mockResolvedValueOnce({ data: { message: 'ok' } });

    renderFlow();
    fillDetails();
    submit();

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });
});
