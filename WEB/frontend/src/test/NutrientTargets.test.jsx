import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/* The page previously rendered a hardcoded TARGETS table and never called the
   goals endpoint at all, so a dialysis patient was shown a healthy adult's
   phosphorus target under the heading "Your Personalized Daily Targets".
   These tests assert the backend's numbers actually reach the screen. */

const GOAL_PROGRESS = {
  date: '2026-08-17',
  profile_complete: true,
  energy_kcal: 1928,
  conditions: ['ckd', 'dialysis'],
  goals: [
    {
      key: 'phosphorus_mg', name: 'Phosphorus', unit: 'mg',
      current: 373, goal: 900, kind: 'limit', pct: 41, status: 'ok', priority: 3,
      rationale: 'CKD: limit phosphorus (~800–1,000 mg/day) to protect bones & vessels.',
    },
    {
      key: 'potassium_mg', name: 'Potassium', unit: 'mg',
      current: 518, goal: 2800, kind: 'limit', pct: 19, status: 'ok', priority: 2,
      rationale: 'Dialysis: individualized ~40 mg/kg/day (KDOQI).',
    },
    {
      key: 'vitamin_b12_mcg', name: 'Vitamin B12', unit: 'mcg',
      current: 2.3, goal: 2.4, kind: 'target', pct: 96, status: 'ok', priority: 90,
      rationale: 'RDA 2.4 mcg/day.',
    },
  ],
};

const DAILY_SUMMARY = {
  date: '2026-08-17', total_calories: 552, total_protein_g: 42,
  total_carbs_g: 28, total_fat_g: 30, meal_count: 1, nutrients: [],
};

let getImpl;
vi.mock('../services/api', () => ({
  default: { get: (...args) => getImpl(...args) },
}));

import NutrientTracking from '../pages/NutrientTracking';

const renderPage = () =>
  render(<MemoryRouter><NutrientTracking /></MemoryRouter>);

beforeEach(() => {
  getImpl = vi.fn((url) => {
    if (url.includes('goal-progress')) return Promise.resolve({ data: GOAL_PROGRESS });
    return Promise.resolve({ data: DAILY_SUMMARY });
  });
});

describe('personalized nutrient targets', () => {
  it('requests the goals endpoint rather than using built-in constants', async () => {
    renderPage();
    await waitFor(() =>
      expect(getImpl).toHaveBeenCalledWith(expect.stringContaining('/nutrition/goal-progress'))
    );
  });

  it("renders the backend's renal limits, not the generic reference values", async () => {
    renderPage();

    // 900 mg is the CKD phosphorus limit. 700 mg was the hardcoded healthy-adult
    // RDA the page used to show a dialysis patient.
    await waitFor(() => expect(screen.getAllByText(/900mg/).length).toBeGreaterThan(0));
    expect(screen.queryByText(/700mg/)).toBeNull();
  });

  it('marks a limit as a limit instead of showing it as a goal to reach', async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/limit/i).length).toBeGreaterThan(0));
  });

  it('shows the conditions that shaped the numbers', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Dialysis')).toBeInTheDocument());
    expect(screen.getByText('Chronic kidney disease')).toBeInTheDocument();
  });

  it('shows the clinical rationale for a limit', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/protect bones & vessels/i)).toBeInTheDocument()
    );
  });

  it('renders mcg as µg', async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText(/µg/).length).toBeGreaterThan(0));
    expect(screen.queryByText(/2\.4mcg/)).toBeNull();
  });

  it('says so when personalization fails instead of passing off generic values', async () => {
    getImpl = vi.fn((url) => {
      if (url.includes('goal-progress')) return Promise.reject(new Error('boom'));
      return Promise.resolve({ data: DAILY_SUMMARY });
    });
    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/could not be loaded/i)).toBeInTheDocument()
    );
    expect(screen.getByText(/not personalized to your profile/i)).toBeInTheDocument();
  });
});
