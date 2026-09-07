/**
 * The projection, pinned.
 *
 * The first version rendered the country UPSIDE DOWN: the textbook Albers form
 * puts north at a larger y, and SVG y grows downward. Nothing about the code
 * looked wrong — it was the standard formula — and a glance at a map of orange
 * blobs would not necessarily catch it either. Orientation is cheap to assert
 * and expensive to notice.
 */
import { describe, it, expect } from 'vitest';
import { albers } from '../components/USCoverageMap';

// [lon, lat] roughly at each state's centre.
const SEATTLE = [-122.3, 47.6];
const LOS_ANGELES = [-118.2, 34.1];
const MIAMI = [-80.2, 25.8];
const NEW_YORK = [-74.0, 40.7];
const PORTLAND_ME = [-70.3, 43.7];

describe('albers projection', () => {
  it('puts north above south (smaller y)', () => {
    expect(albers(SEATTLE)[1]).toBeLessThan(albers(LOS_ANGELES)[1]);
    expect(albers(NEW_YORK)[1]).toBeLessThan(albers(MIAMI)[1]);
  });

  it('puts west left of east (smaller x)', () => {
    expect(albers(LOS_ANGELES)[0]).toBeLessThan(albers(NEW_YORK)[0]);
    expect(albers(NEW_YORK)[0]).toBeLessThan(albers(PORTLAND_ME)[0]);
  });

  it('keeps the country wider than it is tall', () => {
    const xs = [SEATTLE, LOS_ANGELES, MIAMI, NEW_YORK, PORTLAND_ME].map((p) => albers(p)[0]);
    const ys = [SEATTLE, LOS_ANGELES, MIAMI, NEW_YORK, PORTLAND_ME].map((p) => albers(p)[1]);
    const w = Math.max(...xs) - Math.min(...xs);
    const h = Math.max(...ys) - Math.min(...ys);
    expect(w).toBeGreaterThan(h);
  });

  it('curves a parallel — a conic, not a rectangle', () => {
    // Same latitude, different longitudes. A parallel is an arc centred on the
    // cone's apex, which sits NORTH of the map, so it hangs lowest at the
    // central meridian (-96) and rises toward the edges — the US-Canada border
    // sags in the middle on any Albers map. A plain lon/lat plot would tie.
    const centre = albers([-96, 49]);
    const edge = albers([-124, 49]);
    expect(centre[1]).toBeGreaterThan(edge[1]);
    expect(Math.abs(centre[1] - edge[1])).toBeGreaterThan(0.001);
  });
});
