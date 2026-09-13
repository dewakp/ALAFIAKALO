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

describe('the harmonised medication record is NOT printed on this page', () => {
  // It still exists, and the assistant answers from it — /medications/unified
  // is unchanged and covered by tests/test_medications_unified.py. What was
  // wrong was PRINTING it here: this page had three overlapping lists of the
  // same drugs, and it is for recording a dose and seeing what was taken.
  beforeEach(() => { vi.clearAllMocks(); mockApi(); });

  it('leaves the page to the entry form and the day view', async () => {
    renderPage();
    expect(await screen.findByText(/Log New Medication Intake/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText(/Your medication record/i)).not.toBeInTheDocument());
  });

  it('does not re-print the drug catalogue', async () => {
    renderPage();
    await screen.findByText(/Log New Medication Intake/i);
    // The merged-spellings and source chips belonged to the removed listing.
    expect(screen.queryByText(/Also written as/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/days given/i)).not.toBeInTheDocument();
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
