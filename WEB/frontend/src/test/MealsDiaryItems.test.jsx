// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { localToday } from '../utils/datetime';

/**
 * A meal shows the items it was estimated from, and "Re-analyze" corrects the
 * meal it is pressed on.
 *
 * A 3,090 kcal breakfast hid that 2,706 kcal of it was ONE item — "sardines",
 * resolved to USDA "Fish oil, sardine". Per item, the wrong match is on screen.
 * And Re-analyze used to POST /nutrition/estimate-meal with the meal's date and
 * type, which SAVES A NEW LOG: re-analysing added a duplicate and left the
 * original untouched.
 */

const TODAY = localToday();
const LOG = { id: 1114, log_date: TODAY, meal_type: 'breakfast', calories: 3090,
  food_name: '3 Pieces of Sardines, 2 Brioche Bread Slices', nutrient_status: 'done' };

const get = vi.fn();
const post = vi.fn(() => Promise.resolve({ data: {} }));
vi.mock('../services/api', () => ({
  default: {
    get: (...a) => get(...a),
    post: (...a) => post(...a),
    defaults: { headers: { common: {} } },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

import MealsDiary from '../pages/MealsDiary';

let components;

beforeEach(() => {
  post.mockClear();
  components = { estimated: true, components: [
    { position: 0, food_name: 'sardines', matched_name: 'Fish oil, sardine', qty_g: 300,
      source: 'usda', counted: true, nutrients: { calories: 2706, protein_g: 0 } },
    { position: 1, food_name: 'raw', matched_name: null, qty_g: 30, source: null,
      counted: false, nutrients: {} },
  ] };
  get.mockReset();
  get.mockImplementation((url) => {
    if (url.startsWith('/nutrition/?')) return Promise.resolve({ data: [LOG] });
    if (url === `/nutrition/${LOG.id}/components`) return Promise.resolve({ data: components });
    if (url === `/nutrition/${LOG.id}`) return Promise.resolve({ data: { ...LOG } });
    return Promise.resolve({ data: {} });
  });
});

const renderDiary = () => render(<MemoryRouter><MealsDiary /></MemoryRouter>);

describe('meal items', () => {
  it('shows each item with the record it resolved to', async () => {
    renderDiary();
    fireEvent.click(await screen.findByText('Items'));
    expect(await screen.findByText('sardines')).toBeTruthy();
    expect(screen.getByText(/matched to Fish oil, sardine/)).toBeTruthy();
    expect(screen.getByText(/2706 kcal/)).toBeTruthy();
    // An excluded component is still shown, and says it was not counted.
    expect(screen.getByText(/Not counted in the total/)).toBeTruthy();
  });

  it('says a meal was not estimated rather than showing an empty list', async () => {
    components = { estimated: false, components: [] };
    renderDiary();
    fireEvent.click(await screen.findByText('Items'));
    expect(await screen.findByText(/No item breakdown/)).toBeTruthy();
  });

  it('says the load failed — an error is not an empty meal', async () => {
    get.mockImplementation((url) => {
      if (url.startsWith('/nutrition/?')) return Promise.resolve({ data: [LOG] });
      if (url.endsWith('/components')) return Promise.reject(new Error('500'));
      return Promise.resolve({ data: {} });
    });
    renderDiary();
    fireEvent.click(await screen.findByText('Items'));
    expect(await screen.findByText(/Could not load this meal/)).toBeTruthy();
  });
});

describe('Re-analyze', () => {
  it('re-estimates THIS meal in place and never creates another', async () => {
    renderDiary();
    fireEvent.click(await screen.findByText('Re-analyze'));
    await waitFor(() => expect(post).toHaveBeenCalledWith(`/nutrition/${LOG.id}/reestimate`));
    expect(post.mock.calls.some(([url]) => url === '/nutrition/estimate-meal')).toBe(false);
  });
});
