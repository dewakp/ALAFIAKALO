import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '../services/api';
import Notifications from '../pages/Notifications';

function renderPage() {
  return render(
    <MemoryRouter>
      <Notifications />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Notifications', () => {
  it('asks for the collection WITH a trailing slash', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();

    // '/notifications' 307s to '/notifications/', and behind the proxy that
    // Location came back as http:// — which the browser blocks as mixed
    // content. The redirect must never be provoked in the first place.
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(api.get).toHaveBeenCalledWith('/notifications/', expect.anything());
  });

  it('says the load FAILED instead of claiming there is nothing', async () => {
    // The production bug exactly: 18 unread rows in the database, a failed
    // fetch, and a page that reported "No notifications".
    api.get.mockRejectedValue(new Error('Network Error'));
    renderPage();

    const err = await screen.findByTestId('notifications-error');
    expect(err).toHaveTextContent(/couldn’t load/i);
    expect(screen.queryByText('No notifications')).not.toBeInTheDocument();
  });

  it('still shows the empty state when the load genuinely returns nothing', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();

    expect(await screen.findByText('No notifications')).toBeInTheDocument();
    expect(screen.queryByTestId('notifications-error')).not.toBeInTheDocument();
  });

  it('renders the notifications it was given', async () => {
    api.get.mockResolvedValue({
      data: [{
        id: 1, category: 'lab_anomaly', title: 'Potassium is high',
        message: 'K 6.1 mmol/L', is_read: false,
        created_at: new Date().toISOString(), action_url: null,
      }],
    });
    renderPage();

    expect(await screen.findByText('Potassium is high')).toBeInTheDocument();
  });
});
