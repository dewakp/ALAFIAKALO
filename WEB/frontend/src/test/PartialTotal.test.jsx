// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

// A PARTIAL meal total must say what it left out.
//
// Operator, 2026-10-18, after being offered the choice between fixing the bands
// and making the loss visible: *"do 54a first."*
//
// Until 2026-10-18 a meal with one component the plausibility guard refused was
// discarded whole and the screen read "unavailable". That is now kept minus the
// flagged component — which introduces the risk this test exists to close. On
// "Organic Milk (Pasteurized, Nonfat), Protein Drink …" the real milk was
// dropped as a wrong match, so the row reads 193 kcal and would otherwise
// render exactly like a complete total. A number that omits an item reads as
// the whole meal (§3aa).

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockApi = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  defaults: { headers: { common: {} } },
  interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
}));
// The module exports AI_TIMEOUT_MS alongside the default client; a
// default-only mock makes every importer throw at load time.
vi.mock('../services/api', () => ({ default: mockApi, AI_TIMEOUT_MS: 285000 }));

import Nutrition from '../pages/Nutrition';

const LOGS = [
  {
    id: 1, log_date: '2026-10-17', meal_type: 'snack',
    food_name: 'Organic Milk (Pasteurized, Nonfat), Protein Drink',
    calories: 193.4, protein_g: 12.0, carbs_g: 20.0, fat_g: 3.0,
    nutrient_status: 'done',
    nutrients_excluded: ['milk', 'carton'],
  },
  {
    id: 2, log_date: '2026-10-17', meal_type: 'breakfast',
    food_name: 'Goat meat in pepper soup',
    calories: 355.1, protein_g: 30.0, carbs_g: 10.0, fat_g: 20.0,
    nutrient_status: 'done',
    nutrients_excluded: null,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation((url) => {
    if (url.includes('/nutrition')) return Promise.resolve({ data: LOGS });
    return Promise.resolve({ data: [] });
  });
});

describe('a partial meal total', () => {
  it('NAMES what was not counted', async () => {
    render(<MemoryRouter><Nutrition /></MemoryRouter>);
    await waitFor(() => {
      expect(screen.getByText(/Not counted: milk, carton/)).toBeInTheDocument();
    });
  });

  it('says nothing when the total is complete', async () => {
    render(<MemoryRouter><Nutrition /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('355')).toBeInTheDocument());
    // Only the partial row carries a caveat — a complete total must not be
    // decorated with one, or the label stops meaning anything.
    expect(screen.queryAllByText(/Not counted:/)).toHaveLength(1);
  });
});
