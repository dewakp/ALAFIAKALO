import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * The admin console had NO render test, and that is exactly how it shipped
 * broken: a `useEffect` was placed inside `Stat` — a child that renders on every
 * tab — so the page died with "detailId is not defined" before any markup ran.
 *
 * The build succeeded and 147 other tests passed, because a ReferenceError on an
 * out-of-scope variable is a RUNTIME fault: nothing that merely compiles the file
 * can see it. Only rendering the page can.
 */

const USERS = {
  users: [{
    id: 63, email: 'developer@hntsolutions.com', full_name: 'Wole Akpose',
    is_active: true, created_at: '2025-05-22T00:00:00Z', last_login: '2026-08-23T00:00:00Z',
    subscription_status: 'trialing', tokens_used: 0, ai_interactions: 13,
  }],
  total: 1,
};

const DETAIL = {
  id: 63, email: 'developer@hntsolutions.com', full_name: 'Wole Akpose', is_active: true,
  identifiers: {
    // Masked server-side: the DOB and gender segments are blanked in BOTH the
    // raw SID and its decoded form. Masking only the segments moved the
    // disclosure — the raw string sat beside them carrying the same values.
    system_id: 'S1.WOL.AKP.\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022.\u2022.1747887746.PAYLOAD.checksum',
    system_id_segments: { version: 'S1', first3: 'WOL', last3: 'AKP',
                          dob8: '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022', dob_present: true,
                          gender: '\u2022', gender_present: true, epoch10: '1747887746' },
    identity_uid: '1690b893-e650-4b51-a1e6-618b825e3213',
    subject_token: 'alafia-ba9e8bb2f9077c6e',
  },
  // Administrative only. The console used to serve date_of_birth, gender,
  // allergies, height and weight; ADMIN_CONSOLE.md says it returns
  // "counts and metadata only — never clinical records", and now it does.
  profile: { country: 'NG', timezone: 'Africa/Lagos', phone_number: '+234...' },
  activity: {
    meals: { count: 969, last: '2026-08-24' },
    documents: { count: null, last: null, unavailable: true },
  },
  usage: { tokens_used: 0, ai_interactions: 13, last_interaction: null },
};

const OVERVIEW = {
  users: { total: 81, signups_30d: 5, logged_in_24h: 2, logged_in_7d: 6,
           logged_in_30d: 12, never_logged_in: 30 },
  subscriptions: {},
  ai: { interactions_30d: 40, tokens_30d: 1234 },
};

const get = vi.fn();
vi.mock('../services/api', () => ({
  default: {
    get: (...a) => get(...a),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    defaults: { headers: { common: {} } },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

import Admin from '../pages/Admin';

const renderAdmin = () => render(<MemoryRouter><Admin /></MemoryRouter>);

beforeEach(() => {
  get.mockReset();
  get.mockImplementation((url) => {
    if (url.startsWith('/admin/users/')) return Promise.resolve({ data: DETAIL });
    if (url.startsWith('/admin/users')) return Promise.resolve({ data: USERS });
    if (url.startsWith('/admin/overview')) return Promise.resolve({ data: OVERVIEW });
    return Promise.resolve({ data: {} });
  });
});

describe('Admin console', () => {
  it('renders without crashing', async () => {
    renderAdmin();
    expect(await screen.findByText(/ALAFIA Admin/i)).toBeInTheDocument();
    expect(screen.queryByText(/is not defined/i)).toBeNull();
  });

  it('shows the System Identifier that must match FLOWSHEET', async () => {
    renderAdmin();
    fireEvent.click(await screen.findByText(/Users/i));
    const row = await screen.findByText('Wole Akpose');
    fireEvent.click(row.closest('tr'));

    await waitFor(() => expect(screen.getByText(/must match FLOWSHEET/i)).toBeInTheDocument());
    expect(screen.getByText(/S1\.WOL\.AKP/)).toBeInTheDocument();
    expect(screen.getByText('alafia-ba9e8bb2f9077c6e')).toBeInTheDocument();
  });

  it('reports an unavailable domain as unavailable, never as zero', async () => {
    renderAdmin();
    fireEvent.click(await screen.findByText(/Users/i));
    fireEvent.click((await screen.findByText('Wole Akpose')).closest('tr'));

    await waitFor(() => expect(screen.getByText('969')).toBeInTheDocument());
    // The failing domain must say so — a 0 would read as "logs nothing".
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
  });

  it('shows a load error instead of an empty profile', async () => {
    get.mockImplementation((url) => {
      if (url.startsWith('/admin/users/')) return Promise.reject(new Error('boom'));
      if (url.startsWith('/admin/users')) return Promise.resolve({ data: USERS });
      if (url.startsWith('/admin/overview')) return Promise.resolve({ data: OVERVIEW });
      return Promise.resolve({ data: {} });
    });
    renderAdmin();
    fireEvent.click(await screen.findByText(/Users/i));
    fireEvent.click((await screen.findByText('Wole Akpose')).closest('tr'));

    await waitFor(() => expect(screen.getByText(/Couldn.t load this user/i)).toBeInTheDocument());
  });
});
