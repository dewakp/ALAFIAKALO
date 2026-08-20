import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/* A treatment changes the day's balance, never the dietary limit. These pin
   that the limit renders unchanged and the balance renders beside it — and that
   a withheld removal says so rather than quietly showing nothing. */

const withDialysis = (overrides = {}) => ({
  date: '2026-08-17',
  profile_complete: true,
  energy_kcal: 1928,
  conditions: ['ckd', 'dialysis'],
  dialysis: { had_dialysis: true, session_count: 1, modelled_mg: {}, notes: [] },
  goals: [
    {
      key: 'potassium_mg', name: 'Potassium', unit: 'mg', current: 2000, goal: 3000,
      kind: 'limit', pct: 67, status: 'ok', priority: 2, rationale: 'Dialysis: KDOQI.',
      dialysis_balance: {
        intake: 2000, delta: -1400, net: 600, modelled_mg: 3900,
        direction: 'removed', calibrated: true, reasons: [], withheld: null,
      },
    },
    {
      key: 'calcium_mg', name: 'Calcium', unit: 'mg', current: 400, goal: 1000,
      kind: 'target', pct: 40, status: 'low', priority: 3, rationale: 'Bone health.',
      dialysis_balance: {
        intake: 400, delta: 290, net: 690, modelled_mg: -290,
        direction: 'gained', calibrated: false, reasons: [], withheld: null,
      },
    },
  ],
  ...overrides,
});

let getImpl;
vi.mock('../services/api', () => ({ default: { get: (...a) => getImpl(...a) } }));

import NutrientTracking from '../pages/NutrientTracking';

const renderPage = () => render(<MemoryRouter><NutrientTracking /></MemoryRouter>);

function mock(progress) {
  getImpl = vi.fn((url) => {
    if (url.includes('goal-progress')) return Promise.resolve({ data: progress });
    return Promise.resolve({ data: { meal_count: 1, nutrients: [] } });
  });
}

beforeEach(() => mock(withDialysis()));

describe('dialysis balance', () => {
  it('says a treatment happened', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/Dialysis on this day/i)).toBeInTheDocument());
  });

  it('states plainly that limits are unchanged', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/limits are unchanged/i)).toBeInTheDocument()
    );
  });

  it('still shows the guideline limit, not a moved one', async () => {
    renderPage();
    /* 3000 mg is the KDOQI figure; a treatment must not raise it. */
    await waitFor(() => expect(screen.getAllByText(/3000mg/).length).toBeGreaterThan(0));
  });

  it('shows what treatment removed and what was retained', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getAllByText(/from dialysis/i).length).toBeGreaterThan(0)
    );
    expect(screen.getAllByText(/net 600mg retained today/i).length).toBeGreaterThan(0);
  });

  it('shows a bath gain as an addition, not a removal', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/\+290mg from dialysis/i)).toBeInTheDocument());
    expect(screen.getByText(/net 690mg retained today/i)).toBeInTheDocument();
  });

  it('marks an uncalibrated nutrient as estimated', async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/estimated/i).length).toBeGreaterThan(0));
  });

  it('explains a withheld removal instead of showing nothing', async () => {
    const data = withDialysis();
    data.goals[0].dialysis_balance = {
      intake: 2000, delta: 0, net: 2000, modelled_mg: 3900,
      direction: 'none', calibrated: true, reasons: [],
      withheld: 'Your most recent potassium was 6.2, at or above 5.5. Treatment removal is not deducted while it is high.',
    };
    mock(data);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/not deducted while it is high/i)).toBeInTheDocument()
    );
  });

  it('shows nothing extra on a rest day', async () => {
    const data = withDialysis({ dialysis: { had_dialysis: false, session_count: 0, modelled_mg: {}, notes: [] } });
    data.goals.forEach(g => { g.dialysis_balance = null; });
    mock(data);
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/3000mg/).length).toBeGreaterThan(0));
    expect(screen.queryByText(/Dialysis on this day/i)).toBeNull();
    expect(screen.queryByText(/from dialysis/i)).toBeNull();
  });
});
