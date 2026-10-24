// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

/**
 * TASKS 25: an item with no amount is offered the amounts THIS patient stated
 * before, and nothing is written until they press Save.
 */

const get = vi.fn();
const post = vi.fn();
vi.mock('../services/api', () => ({
  default: {
    get: (...a) => get(...a),
    post: (...a) => post(...a),
    defaults: { headers: { common: {} } },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

import MissingAmounts from '../components/MissingAmounts';

const ITEMS = { data: { log_id: 7, items: [
  { food_name: 'smoothie', suggestions: [{ amount: '350 ml', times: 4, last_date: '2026-10-02' }] },
  { food_name: 'egusi', suggestions: [] },
] } };

beforeEach(() => { get.mockReset(); post.mockReset(); });

describe('MissingAmounts', () => {
  it('offers the patient’s own earlier amounts and saves only what they chose', async () => {
    get.mockResolvedValue(ITEMS);
    post.mockResolvedValue({ data: {} });
    const onSaved = vi.fn();
    render(<MissingAmounts logId={7} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole('button', { name: /add amounts/i }));

    await screen.findByText('smoothie');
    expect(get).toHaveBeenCalledWith('/nutrition/7/missing-amounts');
    expect(screen.getByText(/haven't given an amount for this before/i)).toBeTruthy();
    expect(post).not.toHaveBeenCalled();                       // proposing writes nothing

    fireEvent.click(screen.getByRole('button', { name: '350 ml · 4×' }));
    fireEvent.click(screen.getByRole('button', { name: /save amounts/i }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(post).toHaveBeenCalledWith('/nutrition/7/amounts', { amounts: { smoothie: '350 ml' } });
  });

  it('names the item when the amount is not a measure', async () => {
    get.mockResolvedValue(ITEMS);
    post.mockRejectedValue({ response: { status: 422, data: { detail: {
      code: 'not_a_measure', food_name: 'egusi', message: 'egusi: …' } } } });
    render(<MissingAmounts logId={7} />);
    fireEvent.click(screen.getByRole('button', { name: /add amounts/i }));
    fireEvent.change(await screen.findByLabelText('egusi'), { target: { value: 'lots' } });
    fireEvent.click(screen.getByRole('button', { name: /save amounts/i }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/weight or measure for egusi/);
  });

  it('a failed load says so — it never claims nothing is missing', async () => {
    get.mockRejectedValue(new Error('500'));
    render(<MissingAmounts logId={7} />);
    fireEvent.click(screen.getByRole('button', { name: /add amounts/i }));
    expect((await screen.findByText(/could not load/i))).toBeTruthy();
    expect(screen.queryByText(/already has an amount/i)).toBeNull();
  });
});
