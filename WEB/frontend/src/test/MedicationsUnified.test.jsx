import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '../services/api';
import Medications from '../pages/Medications';

// What /medications/unified returns for a patient on ONE iron product that is
// written three ways across four tables. The screen used to render the sources
// as separate lists, so this read as several different drugs.
const ONE_IRON = [{
  name: 'Iron sucrose', drug_class: 'IV iron',
  written_as: ['Venofer', 'Iron sucrose', 'venofer'],
  sources: ['prescribed', 'imported', 'logged', 'administered'],
  active: true, dose: '100 mg', first: '2026-09-01', last: '2026-09-03',
  days: 2, by_source: { prescribed: 1, imported: 1, logged: 1, administered: 2 },
  detail: 'IV iron · 3 records',
}];

function mockApi(unified) {
  api.get.mockImplementation((url) => {
    if (url === '/medications/unified') return Promise.resolve({ data: unified });
    return Promise.resolve({ data: [] });
  });
}

const renderPage = () => render(<MemoryRouter><Medications /></MemoryRouter>);

beforeEach(() => { vi.clearAllMocks(); });

describe('the harmonised medication record', () => {
  it('shows one drug once, under its canonical name', async () => {
    mockApi(ONE_IRON);
    renderPage();
    await waitFor(() => expect(screen.getByText('Iron sucrose')).toBeInTheDocument());
    // The brand names must NOT appear as separate rows.
    expect(screen.queryAllByText('Venofer')).toHaveLength(0);
  });

  it('shows every source that attests to the drug', async () => {
    mockApi(ONE_IRON);
    renderPage();
    await waitFor(() => expect(screen.getByText('Prescribed')).toBeInTheDocument());
    for (const label of ['From your clinic record', 'You logged it', 'Given at a treatment']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('tells the patient which spellings were merged, rather than merging silently', async () => {
    mockApi(ONE_IRON);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/also recorded as/i)).toHaveTextContent('Venofer'));
  });

  it('counts days given, never the sum of records', async () => {
    mockApi(ONE_IRON);
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText('Iron sucrose')).toBeInTheDocument());
    // 5 records across the sources, but Sep 1 is on the flowsheet AND in the
    // dose log — that is one administration written twice. Two days.
    expect(container.textContent).toContain('2 days given');
    expect(container.textContent).not.toMatch(/[345] days given/);
  });

  it('never tells a patient a drug was given by "the unit"', async () => {
    // On home haemodialysis the patient self-administers, and the schema does
    // not record the setting — so the screen must not assert one.
    mockApi(ONE_IRON);
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText('Iron sucrose')).toBeInTheDocument());
    expect(container.textContent).not.toMatch(/the unit|your unit/i);
  });

  it('says a load failure is a display problem, not an empty record', async () => {
    api.get.mockImplementation((url) => (
      url === '/medications/unified'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: [] })
    ));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/not a record of nothing/i)).toBeInTheDocument());
  });
});

describe('the day list', () => {
  // A treatment day whose only record is the flowsheet. This used to render
  // "No intake logged for this date" — the screen that makes a patient log a
  // dose they had already been given.
  const FLOWSHEET_ONLY = [{
    date: '2026-09-11', name: 'Iron sucrose', written_as: 'Venofer',
    dose: '100 mg', time: null, drug_class: 'IV iron',
    sources: ['administered'], dose_log_id: null,
  }];

  function mockDay(record, doseLogs = []) {
    api.get.mockImplementation((url) => {
      if (url === '/medications/day-record') return Promise.resolve({ data: record });
      if (url === '/medications/dose-logs') return Promise.resolve({ data: doseLogs });
      if (url === '/medications/administration-days') {
        return Promise.resolve({ data: ['2026-09-11'] });
      }
      return Promise.resolve({ data: [] });
    });
  }

  it('shows a drug given at a treatment even when no dose log backs it', async () => {
    mockDay(FLOWSHEET_ONLY);
    renderPage();
    await waitFor(() => expect(screen.getByText(/Iron sucrose/)).toBeInTheDocument());
    expect(screen.getByText('On your flowsheet')).toBeInTheDocument();
    expect(screen.queryByText(/No intake logged/i)).toBeNull();
  });

  it('tells the patient a flowsheet dose does not need logging', async () => {
    mockDay(FLOWSHEET_ONLY);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/already on your record, no need to log it/i))
        .toBeInTheDocument());
  });

  it('offers no delete for a dose this screen does not own', async () => {
    mockDay(FLOWSHEET_ONLY);
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText(/Iron sucrose/)).toBeInTheDocument());
    expect(container.querySelectorAll('button[title="Delete"]')).toHaveLength(0);
  });

  it('still says so plainly when a day genuinely holds nothing', async () => {
    mockDay([]);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/Nothing recorded for this date/i)).toBeInTheDocument());
  });
});
