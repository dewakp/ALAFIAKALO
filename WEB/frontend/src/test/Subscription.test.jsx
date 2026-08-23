import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import api from '../services/api';
import Subscription from '../pages/Subscription';

const PLANS = {
  product_name: 'ALAFIA Membership',
  plan: 'plus_monthly',
  interval: 'month',
  // The catalog no longer carries a paypal rail; the page must not invent one.
  rails: [
    { provider: 'stripe', price_usd: 12 },
    { provider: 'google_play', price_usd: 14 },
    { provider: 'apple', price_usd: 14 },
  ],
  plans: [
    { interval: 'month', plan: 'plus_monthly', rails: [{ provider: 'stripe', price_usd: 12 }] },
    { interval: 'year', plan: 'plus_annual', rails: [{ provider: 'stripe', price_usd: 129 }] },
  ],
};

function status(overrides = {}) {
  return {
    status: 'none', provider: 'none', plan: 'plus_monthly', entitled: false,
    product_name: 'ALAFIA Membership', price_usd: 12, current_period_end: null,
    cancel_at_period_end: false, ...overrides,
  };
}

function mockApi(statusBody) {
  api.get.mockImplementation((url) => {
    if (url === '/subscription/plans') return Promise.resolve({ data: PLANS });
    if (url === '/subscription/status') return Promise.resolve({ data: statusBody });
    return Promise.resolve({ data: {} });
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <Subscription />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Subscription paywall', () => {
  it('offers card checkout and no PayPal button', async () => {
    mockApi(status());
    renderPage();

    expect(await screen.findByRole('button', { name: /pay with card/i })).toBeInTheDocument();
    // PayPal was drawn here for as long as it was unconfigured in production,
    // so every tap answered 503 "PayPal billing is not configured".
    expect(screen.queryByRole('button', { name: /paypal/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/paypal/i)).not.toBeInTheDocument();
  });

  it('tells a user whose card was declined that it was declined', async () => {
    mockApi(status({ status: 'incomplete' }));
    renderPage();

    const alert = await screen.findByTestId('payment-failed');
    expect(alert).toHaveTextContent(/didn’t go through/i);
    expect(alert).toHaveTextContent(/declined/i);
    // …and they can still try again.
    expect(screen.getByRole('button', { name: /pay with card/i })).toBeInTheDocument();
  });

  it('does not cry payment-failure at a first-time visitor', async () => {
    mockApi(status());
    renderPage();

    await screen.findByRole('button', { name: /pay with card/i });
    expect(screen.queryByTestId('payment-failed')).not.toBeInTheDocument();
  });

  it('does not cry payment-failure at a member in renewal grace', async () => {
    // past_due while STILL entitled is a renewal retry, not a dead end.
    mockApi(status({
      status: 'past_due', provider: 'stripe', entitled: true,
      current_period_end: new Date(Date.now() + 3 * 86400000).toISOString(),
    }));
    renderPage();

    await waitFor(() => expect(screen.getByText(/You’re subscribed/i)).toBeInTheDocument());
    expect(screen.queryByTestId('payment-failed')).not.toBeInTheDocument();
  });
});
