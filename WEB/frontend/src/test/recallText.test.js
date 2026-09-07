import { describe, it, expect } from 'vitest';
import { summariseRecall } from '../utils/recallText';

describe('summariseRecall', () => {
  it('separates the product from its package configurations', () => {
    const { title, items } = summariseRecall(
      'Grade A White In-shell Chicken eggs packaged in the following configurations: ' +
      '1. Kroger, Medium, 12 Eggs, Net Wt 21 oz (1lb 5oz) 596g, UPC 0 11110-60902 1. ' +
      '2. Kroger, Medium, 30 Eggs, Net Wt 52.5 oz, UPC 0 11110-60980 9. ' +
      '3. Kroger, Large 12 Eggs, Net Wt 24 oz, UPC 0 11110-60903 8.');
    expect(title).toBe('Grade A White In-shell Chicken eggs');
    expect(items.length).toBeGreaterThanOrEqual(3);
    expect(items[0]).toMatch(/^1\./);
  });

  it('keeps a short description whole', () => {
    const { title, items } = summariseRecall('Peanut butter, 16 oz jar');
    expect(title).toBe('Peanut butter, 16 oz jar');
    expect(items).toEqual([]);
  });

  it('does not split on a decimal inside a weight', () => {
    const text = 'Chocolate bar Net Wt 1.5 oz distributed nationwide';
    expect(summariseRecall(text).title).toBe(text);
  });

  it('caps a long description that has no list', () => {
    const long = 'A '.repeat(200) + 'end';
    const { title } = summariseRecall(long);
    expect(title.length).toBeLessThan(200);
    expect(title.endsWith('…')).toBe(true);
  });

  it('never returns an empty title', () => {
    expect(summariseRecall('').title).toBeTruthy();
    expect(summariseRecall(null).title).toBeTruthy();
  });
});
