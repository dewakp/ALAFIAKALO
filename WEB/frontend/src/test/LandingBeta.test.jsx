import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Landing calls useAuth() to decide the hero CTA. The real provider fetches a
// CSRF cookie and a session on mount, neither of which this file tests.
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: null, loading: false }),
  AuthProvider: ({ children }) => children,
}));

// SnowCanvas animates on a <canvas>. jsdom returns null from getContext('2d'),
// so the draw loop throws inside the effect and takes the whole render with it.
// The chrome is not what this file tests.
vi.mock('../components/MarketingChrome', () => ({
  SnowCanvas: () => null,
  Angel: () => null,
  Orb: () => null,
  MarketingNav: () => null,
  MarketingFooter: () => null,
}));

import Landing from '../pages/Landing';

const renderLanding = () =>
  render(
    <MemoryRouter>
      <Landing />
    </MemoryRouter>,
  );

const openForm = () =>
  fireEvent.click(screen.getByRole('button', { name: /Get it in Beta/i }));

function fillAndSubmit({ notes = '' } = {}) {
  fireEvent.change(screen.getByLabelText(/Your name/i), { target: { value: 'Ada Demo' } });
  fireEvent.change(screen.getByLabelText(/^Email$/i), { target: { value: 'ada@example.com' } });
  if (notes) {
    fireEvent.change(screen.getByLabelText(/Notes/i), { target: { value: notes } });
  }
  fireEvent.click(screen.getByRole('button', { name: /Request beta/i }));
}

const okResponse = (body = {}) => ({
  ok: true,
  json: async () => ({ ok: true, desk: 'iOS Beta Request', reference: 'ALF-A1B2C3', ...body }),
});

describe('the landing page asks for the iOS beta', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // A token already in the jar, so the component takes the single-fetch path
    // and the assertions below see the contact POST as the only call.
    document.cookie = 'csrf_token=test-token';
    global.fetch = vi.fn().mockResolvedValue(okResponse());
  });

  it('offers the beta instead of the inert "coming soon" label', () => {
    renderLanding();
    // The store line stays — it is still true — but it is no longer the only
    // thing the iPhone card says.
    expect(screen.getByText(/Coming to App Store/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Get it in Beta/i })).toBeInTheDocument();
  });

  it('shows no form until someone asks for it', () => {
    renderLanding();
    expect(screen.queryByLabelText(/Your name/i)).not.toBeInTheDocument();
    openForm();
    expect(screen.getByLabelText(/Your name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Email$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Notes/i)).toBeInTheDocument();
  });

  it('sends the TOPIC KEY and never an address', async () => {
    renderLanding();
    openForm();
    fillAndSubmit({ notes: 'Subscribed in August on the web.' });

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());

    const [url, init] = global.fetch.mock.calls.at(-1);
    expect(url).toBe('/api/v1/contact');
    expect(init.headers['X-CSRF-Token']).toBe('test-token');

    const body = JSON.parse(init.body);
    expect(body.topic).toBe('beta_ios');
    expect(body.name).toBe('Ada Demo');
    expect(body.email).toBe('ada@example.com');
    // The server resolves the desk from the topic. A client that could name a
    // recipient would be an open relay (CLAUDE.md §3d).
    expect(body).not.toHaveProperty('to');
    expect(body.message).toMatch(/Subscribed in August/);
  });

  it('composes a message over the endpoint\'s 10-character minimum when notes are blank', async () => {
    renderLanding();
    openForm();
    fillAndSubmit();   // notes left empty — they are optional

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    const body = JSON.parse(global.fetch.mock.calls.at(-1)[1].body);
    // ContactRequest.message is min_length=10; a bare "" would 422 the form
    // for every person who types nothing in the optional box.
    expect(body.message.length).toBeGreaterThanOrEqual(10);
  });

  it('quotes the reference back, because the row exists under it', async () => {
    renderLanding();
    openForm();
    fillAndSubmit();
    expect(await screen.findByText(/ALF-A1B2C3/)).toBeInTheDocument();
    expect(screen.getByText(/Request received/i)).toBeInTheDocument();
  });

  it("shows the server's own sentence when it refuses", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'Too many requests. Please try again in a minute.' }),
    });
    renderLanding();
    openForm();
    fillAndSubmit();

    // A generic "something went wrong" hides the one useful thing — whether to
    // retry or write to someone.
    expect(await screen.findByText(/try again in a minute/i)).toBeInTheDocument();
  });

  it('fetches a CSRF cookie when the jar is empty', async () => {
    document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) })   // csrf-cookie
      .mockResolvedValueOnce(okResponse());

    renderLanding();
    openForm();
    fillAndSubmit();

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
    expect(global.fetch.mock.calls[0][0]).toBe('/api/v1/auth/csrf-cookie');
    expect(global.fetch.mock.calls[1][0]).toBe('/api/v1/contact');
  });
});
