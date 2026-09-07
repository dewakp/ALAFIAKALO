/**
 * US coverage map — real state geometry, no map library, works offline.
 *
 * This was a grid of labelled squares ("statebins"). Squares are legible but
 * they are not a map: they cannot show that a recall covers the Gulf coast, or
 * the Pacific Northwest, or everything east of the Mississippi — which is the
 * only question a coverage map exists to answer.
 *
 * Alaska and Hawaii are drawn as INSETS, as every printed US map does. Left in
 * place they own the projection: Alaska's Aleutians cross the antimeridian
 * (this file reaches longitude -188.9), so a naive fit squeezes the contiguous
 * 48 into a third of the frame and puts the states anyone is looking for into
 * an unreadable strip.
 */
import { useEffect, useState } from 'react';

// Albers-style conic for the contiguous 48. A plain lon/lat plot leans the
// country visibly — Maine ends up level with Washington — because a degree of
// longitude shortens as you go north. This costs ten lines and looks right.
const LAT0 = (23 * Math.PI) / 180;   // standard parallels
const LAT1 = (45 * Math.PI) / 180;
const LON0 = (-96 * Math.PI) / 180;  // central meridian
const N = Math.sin(LAT0) + Math.sin(LAT1) === 0
  ? Math.sin(LAT0)
  : (Math.sin(LAT0) + Math.sin(LAT1)) / 2;
const C = Math.cos(LAT0) ** 2 + 2 * N * Math.sin(LAT0);
const RHO0 = Math.sqrt(C - 2 * N * Math.sin((39 * Math.PI) / 180)) / N;

export function albers([lon, lat]) {
  const theta = N * ((lon * Math.PI) / 180 - LON0);
  const rho = Math.sqrt(C - 2 * N * Math.sin((lat * Math.PI) / 180)) / N;
  // y grows DOWNWARD in SVG, so north must map to a smaller y. The textbook
  // form (RHO0 - rho·cosθ) gives the opposite and renders the country upside
  // down — Washington below California.
  return [rho * Math.sin(theta), rho * Math.cos(theta) - RHO0];
}

/** Flatten Polygon / MultiPolygon rings to arrays of [lon,lat]. */
function rings(geometry) {
  if (!geometry) return [];
  return geometry.type === 'Polygon' ? geometry.coordinates
    : geometry.type === 'MultiPolygon' ? geometry.coordinates.flat()
    : [];
}

function fit(features, project, box) {
  const pts = features.flatMap((f) => rings(f.geometry).flat().map(project));
  if (!pts.length) return null;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const k = Math.min(box.w / (x1 - x0 || 1), box.h / (y1 - y0 || 1));
  return (pt) => {
    const [x, y] = project(pt);
    return [
      box.x + (x - x0) * k + (box.w - (x1 - x0) * k) / 2,
      box.y + (y - y0) * k + (box.h - (y1 - y0) * k) / 2,
    ];
  };
}

function pathFor(feature, place) {
  return rings(feature.geometry)
    .map((ring) => ring.map(place).map(([x, y], i) =>
      `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join('') + 'Z')
    .join(' ');
}

const W = 640;
const H = 380;

export default function USCoverageMap({ covered = [], nationwide = false }) {
  const [states, setStates] = useState(null);

  useEffect(() => {
    let alive = true;
    fetch('/us-states.geojson')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
      .then((d) => alive && setStates(d.features || []))
      // A failed fetch must not render an empty frame that reads as
      // "no coverage" — the caller keeps showing its text summary either way.
      .catch(() => alive && setStates([]));
    return () => { alive = false; };
  }, []);

  if (states === null) {
    return <div style={{ height: H, display: 'grid', placeItems: 'center',
                         color: 'var(--color-text-secondary)', fontSize: '.85rem' }}>
      Loading map…
    </div>;
  }
  if (!states.length) return null;

  const isCovered = (code) =>
    nationwide || covered.map((s) => String(s).toUpperCase()).includes(code);

  const by = (codes) => states.filter((f) => codes.includes(f.properties.code));
  const not = (codes) => states.filter((f) => !codes.includes(f.properties.code));

  const lower48 = not(['AK', 'HI', 'PR']);
  const placeMain = fit(lower48, albers, { x: 8, y: 8, w: W - 16, h: H - 70 });
  // Insets get their own fit, so each is drawn at a readable size rather than
  // at true relative scale — Alaska at true scale would dwarf Texas.
  const placeAK = fit(by(['AK']), ([lon, lat]) => [lon < -168 ? lon + 360 : lon, lat],
                      { x: 10, y: H - 118, w: 150, h: 105 });
  const placeHI = fit(by(['HI']), (p) => p, { x: 176, y: H - 86, w: 92, h: 70 });

  const fill = (f) => (isCovered(f.properties.code) ? '#f97316' : '#e5e7eb');

  const draw = (feature, place) => place && (
    <path key={feature.properties.code} d={pathFor(feature, place)}
          fill={fill(feature)} stroke="#fff" strokeWidth={0.6}>
      <title>{feature.properties.name}{isCovered(feature.properties.code) ? ' — covered' : ''}</title>
    </path>
  );

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" style={{ width: '100%', height: 'auto' }}
         aria-label={nationwide ? 'Nationwide distribution'
                                : `Distribution in ${covered.length} states`}>
      {lower48.map((f) => draw(f, placeMain))}
      {by(['AK']).map((f) => draw(f, placeAK))}
      {by(['HI']).map((f) => draw(f, placeHI))}
      <text x={10} y={H - 6} fontSize={11} fill="var(--color-text-secondary, #64748b)">Alaska</text>
      <text x={176} y={H - 6} fontSize={11} fill="var(--color-text-secondary, #64748b)">Hawaii</text>
    </svg>
  );
}
