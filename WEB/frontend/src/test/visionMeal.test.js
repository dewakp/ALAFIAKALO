// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.
import { describe, it, expect } from 'vitest';
import { mealFromVisionRows } from '../utils/visionMeal';

// The meal that exposed this: corrected to 100/60/80/20 g, saved as names only.
const rows = [
  { name: '3 Pieces of Sardines', estimated_grams: '100' },
  { name: '2 Brioche Bread Slices', estimated_grams: 60 },
  { name: '2 Boiled eggs', estimated_grams: '80' },
  { name: 'Onion slices (raw)', estimated_grams: '20' },
];

describe('mealFromVisionRows', () => {
  it('carries each corrected weight in front of its food, where the parser reads it', () => {
    expect(mealFromVisionRows(rows).food_name).toBe(
      '100 g 3 Pieces of Sardines, 60 g 2 Brioche Bread Slices, 80 g 2 Boiled eggs, 20 g Onion slices (raw)');
  });

  it('gives the serving size as the whole meal, not the first item', () => {
    expect(mealFromVisionRows(rows).serving_size).toBe('composite meal (260 g total)');
  });

  it('leaves the total blank when any weight is unknown, rather than undercounting', () => {
    const r = mealFromVisionRows([...rows.slice(0, 3), { name: 'Onion', estimated_grams: '' }]);
    expect(r.serving_size).toBe('');
    expect(r.food_name.endsWith(', Onion')).toBe(true);
  });

  it('drops empty rows and states a single food in grams', () => {
    expect(mealFromVisionRows([{ name: ' Rice ', estimated_grams: '150.25' }, { name: '', estimated_grams: '5' }]))
      .toEqual({ food_name: '150.3 g Rice', serving_size: '150.3 g' });
  });
});
