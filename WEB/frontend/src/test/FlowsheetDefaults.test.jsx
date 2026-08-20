import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/* Starting a new treatment should already know what hasn't changed. The risk is
   pre-filling something wrong, so these pin the two that matter: needle fields
   must be disabled for a catheter (and re-enable the moment the access changes),
   and the carried-forward values must be visibly attributed, not silent. */

const DEFAULTS = {
  target_weight_kg: 70.2,
  target_weight_basis: 'Average of your last 7 post-treatment weights.',
  target_weight_sample_size: 7,
  access_type: 'Catheter. URJ',
  access_kind: 'catheter',
  disabled_fields: ['needle_gauge', 'needle_length', 'buttonhole_technique', 'access_thrill_bruit'],
  carried_forward: {
    attending_physician: 'Desai, Anand MD',
    dialysis_access_type: 'Catheter. URJ',
    dialysate_potassium_meq: 1.0,
    sak_number: 4,
  },
  carried_from_date: '2026-08-18',
  notes: ['Your last treatment used a catheter, so the needle and bruit fields are switched off.'],
};

let getImpl;
vi.mock('../services/api', () => ({
  default: {
    get: (...a) => getImpl(...a),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    put: vi.fn(() => Promise.resolve({ data: {} })),
  },
}));

import Hemodialysis from '../pages/Hemodialysis';

const renderPage = () => render(<MemoryRouter><Hemodialysis /></MemoryRouter>);

function mock(defaults = DEFAULTS) {
  getImpl = vi.fn((url) => {
    if (url.includes('therapy-sessions/defaults')) return Promise.resolve({ data: defaults });
    if (url.includes('therapy-sessions')) return Promise.resolve({ data: [] });
    return Promise.resolve({ data: {} });
  });
}

async function openNewSession() {
  renderPage();
  const button = await screen.findByText(/\+ New Session/i);
  fireEvent.click(button);
  await waitFor(() =>
    expect(getImpl).toHaveBeenCalledWith(expect.stringContaining('therapy-sessions/defaults'))
  );
}

beforeEach(() => mock());

describe('new treatment defaults', () => {
  it('asks the backend what to pre-fill', async () => {
    await openNewSession();
  });

  it("says where the pre-filled values came from", async () => {
    await openNewSession();
    await waitFor(() =>
      expect(screen.getByText(/Pre-filled from your treatment on 2026-08-18/i)).toBeInTheDocument()
    );
  });

  it('explains why needle fields are off', async () => {
    await openNewSession();
    await waitFor(() =>
      expect(screen.getByText(/needle and bruit fields are switched off/i)).toBeInTheDocument()
    );
  });

  it('disables the needle fields for a catheter', async () => {
    await openNewSession();
    await waitFor(() => expect(screen.getByLabelText(/Buttonhole/i)).toBeDisabled());
    expect(screen.getByText(/Needle Length/i).closest('div').querySelector('input')).toBeDisabled();
  });

  it('re-enables them as soon as the access changes to a fistula', async () => {
    await openNewSession();
    await waitFor(() => expect(screen.getByLabelText(/Buttonhole/i)).toBeDisabled());

    const accessSelect = screen.getByText(/Access Type/i).closest('div').querySelector('select');
    fireEvent.change(accessSelect, { target: { value: 'AV Fistula' } });

    await waitFor(() => expect(screen.getByLabelText(/Buttonhole/i)).not.toBeDisabled());
  });

  it('leaves needle fields enabled for a graft', async () => {
    /* A graft is cannulated like a fistula — needles apply. */
    mock({ ...DEFAULTS, access_kind: 'needled', disabled_fields: [],
           carried_forward: { ...DEFAULTS.carried_forward, dialysis_access_type: 'AV Graft' } });
    await openNewSession();
    await waitFor(() => expect(screen.getByLabelText(/Buttonhole/i)).not.toBeDisabled());
  });

  it('still opens the form when defaults cannot be loaded', async () => {
    /* A failed pre-fill means an empty form, never a blocked one. */
    getImpl = vi.fn((url) => {
      if (url.includes('therapy-sessions/defaults')) return Promise.reject(new Error('boom'));
      if (url.includes('therapy-sessions')) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPage();
    fireEvent.click(await screen.findByText(/\+ New Session/i));
    await waitFor(() => expect(screen.getByText(/Vascular Access & Weights/i)).toBeInTheDocument());
  });
});
