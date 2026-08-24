import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '../services/api';
import Medications from '../pages/Medications';

// The two rows this production account actually holds: SMART-sandbox EHR
// imports from 2017, both stopped. They were the ONLY choices the picker
// offered for "what are you taking today".
const STALE_2017 = [
  { id: 14, name: 'Ibuprofen 200 MG Oral Tablet', dosage: '', dosage_unit: '',
    frequency: '', is_active: false, source: 'ehr' },
  { id: 15, name: 'Meperidine Hydrochloride 50 MG Oral Tablet', dosage: '1',
    dosage_unit: '', frequency: '', is_active: false, source: 'ehr' },
];

const CURRENT = { id: 21, name: 'Calcitriol', dosage: '0.5', dosage_unit: 'mcg',
                  frequency: 'daily', is_active: true };

function mockApi(meds) {
  api.get.mockImplementation((url) => {
    if (url === '/medications/') return Promise.resolve({ data: meds });
    if (url === '/medications/dose-logs') return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
}

function renderPage() {
  return render(<MemoryRouter><Medications /></MemoryRouter>);
}

function pickerOptions() {
  return Array.from(document.querySelectorAll('#med-catalog option')).map(o => o.value);
}

beforeEach(() => { vi.clearAllMocks(); });

describe('Medications picker', () => {
  it('does not offer prescriptions that were stopped in 2017', async () => {
    mockApi(STALE_2017);
    renderPage();

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/medications/'));
    await waitFor(() => expect(pickerOptions()).toEqual([]));
    expect(pickerOptions()).not.toContain('Ibuprofen 200 MG Oral Tablet');
  });

  it('explains why the picker is empty instead of just being empty', async () => {
    mockApi(STALE_2017);
    renderPage();

    const hint = await screen.findByTestId('stale-meds-hint');
    expect(hint).toHaveTextContent(/stopped/i);
    expect(hint).toHaveTextContent(/Prescriptions/);
  });

  it('offers a current prescription', async () => {
    mockApi([...STALE_2017, CURRENT]);
    renderPage();

    await waitFor(() => expect(pickerOptions()).toContain('Calcitriol'));
    expect(pickerOptions()).toHaveLength(1);
    expect(screen.queryByTestId('stale-meds-hint')).not.toBeInTheDocument();
  });

  it('opens the Prescriptions manager when there is nothing current to pick', async () => {
    // The complaint was "no options to enter list of medications being taken".
    // The manager existed, collapsed, below a long form.
    mockApi(STALE_2017);
    renderPage();

    // Header states the split, so "2 prescriptions" cannot read as "2 available".
    expect(await screen.findByText(/Prescriptions \(0 active of 2\)/)).toBeInTheDocument();
    // And the manager is expanded, not collapsed behind a disclosure: its table
    // lists both stopped rows with their status.
    await waitFor(() =>
      expect(screen.getByText('Ibuprofen 200 MG Oral Tablet')).toBeInTheDocument());
    expect(screen.getAllByText(/Inactive/i)).toHaveLength(2);
  });
});

describe('"I take X" quick log', () => {
  it('shows the proposed dose WITH where it came from', async () => {
    mockApi([CURRENT]);
    api.post.mockResolvedValue({ data: {
      medication_name: 'Calcitriol', dose_amount: 0.5, dose_unit: 'mcg',
      dose_source: 'history', confidence: 1.0,
      provenance: '0.5 mcg — your last 6 doses, most recently 25 Feb 2026',
      needs_confirmation: true, alternatives: [], findings: [],
    }});
    const user = userEvent.setup();
    renderPage();

    await user.type(await screen.findByPlaceholderText(/I take Calcitriol/i), 'I take Calcitriol');
    await user.click(screen.getByRole('button', { name: /read this/i }));

    const card = await screen.findByTestId('intake-proposal');
    expect(card).toHaveTextContent('Calcitriol');
    expect(card).toHaveTextContent('0.5 mcg');
    // Provenance is not optional: an inferred dose with no stated origin is
    // indistinguishable from one the app made up.
    expect(card).toHaveTextContent(/your last 6 doses/);
    expect(api.post).toHaveBeenCalledWith('/medications/intake-intent', { text: 'I take Calcitriol' });
  });

  it('never logs anything on its own', async () => {
    mockApi([CURRENT]);
    api.post.mockResolvedValue({ data: {
      medication_name: 'Calcitriol', dose_amount: 0.5, dose_unit: 'mcg',
      dose_source: 'history', provenance: 'x', needs_confirmation: true,
      alternatives: [], findings: [],
    }});
    const user = userEvent.setup();
    renderPage();

    await user.type(await screen.findByPlaceholderText(/I take Calcitriol/i), 'I take Calcitriol');
    await user.click(screen.getByRole('button', { name: /read this/i }));
    await screen.findByTestId('intake-proposal');

    const wrote = api.post.mock.calls.some(([url]) => url === '/medications/dose-logs');
    expect(wrote).toBe(false);
  });

  it('surfaces a dose the guard refused, and pre-fills nothing', async () => {
    mockApi([CURRENT]);
    api.post.mockResolvedValue({ data: {
      medication_name: 'calcium calcitriol', dose_amount: null, dose_unit: null,
      dose_source: 'unknown', confidence: 0,
      provenance: 'Your past entries for this look wrong — please confirm the dose.',
      needs_confirmation: true, alternatives: [],
      findings: [{ level: 'error', code: 'unknown_medication',
                   message: '“calcium calcitriol” isn’t a medication in RxNorm. The closest match is “Calcitriol”.',
                   suggestion: 'Calcitriol' }],
    }});
    const user = userEvent.setup();
    renderPage();

    await user.type(await screen.findByPlaceholderText(/I take Calcitriol/i), 'calcium calcitriol');
    await user.click(screen.getByRole('button', { name: /read this/i }));

    expect(await screen.findByTestId('intake-finding')).toHaveTextContent(/isn.t a medication in RxNorm/);
    expect(screen.getByTestId('intake-proposal')).not.toHaveTextContent(/1000/);
  });
});
