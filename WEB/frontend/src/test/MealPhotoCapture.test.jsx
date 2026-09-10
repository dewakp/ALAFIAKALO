import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

/**
 * The camera control on the meal form.
 *
 * Asserted against the source rather than a render: Nutrition.jsx pulls in the
 * whole logging screen (units context, polling, a dozen endpoints), and the
 * facts that broke here are structural — WHICH attributes are on WHICH input.
 * A render test would need so much mocking that it would stop describing the
 * thing that failed.
 */
const src = fs.readFileSync(
  path.resolve(__dirname, '../pages/Nutrition.jsx'), 'utf8');

describe('meal photo capture', () => {
  it('offers a camera control, not only a file picker', () => {
    // The copy has always promised "or take a photo". Nothing did.
    expect(src).toMatch(/Take Photo/);
    expect(src).toMatch(/capture="environment"/);
  });

  it('keeps capture and multiple on SEPARATE inputs', () => {
    // A browser handed both ignores one of them, and which one differs between
    // iOS and Android — so the combination cannot be relied on either way.
    const inputs = src.match(/<input[^>]*type="file"[^>]*>/gs) || [];
    const both = inputs.filter(t => t.includes('capture=') && t.includes('multiple'));
    expect(both).toEqual([]);
    expect(inputs.some(t => t.includes('capture='))).toBe(true);
    expect(inputs.some(t => t.includes('multiple'))).toBe(true);
  });

  it('detaches the bytes on the camera path too', () => {
    // WebKit empties a File when its input is cleared: the chip still shows a
    // filename and the upload arrives with no image. The picker path already
    // guarded this; a camera path that skipped it would reintroduce the exact
    // bug on the platform most likely to use the camera.
    const cameraBlock = src.slice(src.indexOf('capture="environment"'));
    const handler = cameraBlock.slice(0, cameraBlock.indexOf('}}/>'));
    expect(handler).toMatch(/detachFiles/);
  });
});
