import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/* What a drug, supplement or treatment did to a nutrient, beside its intake
   figure. The sibling of DialysisBalance.test.jsx, for everything that is not
   gradient transfer.

   The failure these exist to prevent is silence. A decade of IV iron reached
   nutrient tracking as zero because the effect was computed and then dropped —
   first by the schema, then by a client-side remap that picked fields. An
   effect that cannot be counted must still SAY so: "given, amount not
   recorded", or "not confirmed", is a finding. A blank line is not. */

const withEffects = (overrides = {}) => ({
  date: '2026-09-21',
  profile_complete: true,
  energy_kcal: 1928,
  conditions: ['ckd', 'dialysis'],
  dialysis: { had_dialysis: true, session_count: 1, modelled_mg: {}, notes: [] },
  effects: {
    agents: ['Hemodialysis', 'Iron sucrose'],
    applied: [],
    notes: [],
  },
  goals: [
    {
      key: 'protein_g', name: 'Protein', unit: 'g', current: 70, goal: 90,
      kind: 'target', pct: 78, status: 'low', priority: 1, rationale: 'Dialysis: KDOQI.',
      dialysis_balance: null,
      nutrient_effects: [{
        agent: 'Hemodialysis', direction: 'removes', delta: -10.32, modelled: -10.32,
        applied: true, mechanism: 'Free amino acids leave in the effluent.',
        withheld: null,
      }],
    },
    {
      key: 'iron_mg', name: 'Iron', unit: 'mg', current: 8, goal: 8,
      kind: 'target', pct: 100, status: 'ok', priority: 2, rationale: 'Anaemia.',
      dialysis_balance: null,
      nutrient_effects: [{
        agent: 'Iron sucrose', direction: 'adds', delta: 0, modelled: 200,
        applied: false, mechanism: 'IV iron delivers elemental iron directly.',
        withheld: 'Iron sucrose affects this, but the amount comes from an automated source and has not been confirmed, so it is shown rather than counted.',
      }],
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

beforeEach(() => mock(withEffects()));

describe('agent effects on a nutrient', () => {
  it('names the agent and what it did', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/-10\.3g from Hemodialysis/i)).toBeInTheDocument()
    );
  });

  it('gives the mechanism, so the number is readable', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/amino acids leave in the effluent/i)).toBeInTheDocument()
    );
  });

  it('explains a withheld effect instead of showing nothing', async () => {
    /* The IV iron case: the record states 200 mg, the figure behind it came
       from an automated source, and crediting it against an iron TARGET would
       tell an anaemic patient they had met their needs. It is shown with the
       reason, never counted. */
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/has not been confirmed/i)).toBeInTheDocument()
    );
  });

  it('does not show a withheld effect as an amount', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/has not been confirmed/i)).toBeInTheDocument());
    /* delta is 0 and must not render as "+0mg from Iron sucrose". */
    expect(screen.queryByText(/from Iron sucrose/i)).toBeNull();
  });

  it('leaves the goal figure untouched', async () => {
    /* An effect reports beside the intake; it never rewrites it. A protein
       target of 90 g stays 90 g whatever dialysis removed. */
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/70g \/ 90g/).length).toBeGreaterThan(0));
  });

  it('shows nothing extra when a goal has no effects', async () => {
    const data = withEffects();
    data.goals.forEach(g => { g.nutrient_effects = []; });
    data.effects = { agents: [], applied: [], notes: [] };
    mock(data);
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/70g \/ 90g/).length).toBeGreaterThan(0));
    expect(screen.queryByText(/from Hemodialysis/i)).toBeNull();
    expect(screen.queryByText(/has not been confirmed/i)).toBeNull();
  });

  it('survives a response that omits the field entirely', async () => {
    /* An older backend, or a cached response from before the field existed.
       A missing key must not blank the page. */
    const data = withEffects();
    delete data.effects;
    data.goals.forEach(g => { delete g.nutrient_effects; });
    mock(data);
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/70g \/ 90g/).length).toBeGreaterThan(0));
  });
});
