/**
 * World coverage map — dependency-free. Renders a bundled GeoJSON (public/
 * world-countries.geojson) with a plain equirectangular projection and highlights
 * the covered countries. No map library (works with React 19, offline).
 */
import { useEffect, useState } from 'react';

// ISO 3166-1 alpha-2 → numeric (the GeoJSON feature `id`). Covers the countries
// our sources emit plus common others; unknown codes simply won't highlight.
const A2_TO_NUM = {
  US: '840', CA: '124', GB: '826', MX: '484', BR: '076', AR: '032', CL: '152',
  IE: '372', FR: '250', DE: '276', IT: '380', ES: '724', PT: '620', NL: '528',
  BE: '056', CH: '756', AT: '040', SE: '752', NO: '578', DK: '208', FI: '246',
  PL: '616', GR: '300', CZ: '203', RO: '642', HU: '348', RU: '643', UA: '804',
  IN: '356', CN: '156', JP: '392', KR: '410', AU: '036', NZ: '554', ZA: '710',
  NG: '566', GH: '288', KE: '404', EG: '818', MA: '504', AE: '784', SA: '682',
  IL: '376', TR: '792', ID: '360', MY: '458', SG: '702', TH: '764', PH: '608',
  VN: '704', PK: '586', BD: '050', CO: '170', PE: '604',
};

const W = 800, H = 400;
const proj = (lon, lat) => [(lon + 180) / 360 * W, (90 - lat) / 180 * H];

function ringPath(ring) {
  return ring.map(([lon, lat], i) => {
    const [x, y] = proj(lon, lat);
    return `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join('') + 'Z';
}

function pathFor(geom) {
  if (!geom) return '';
  if (geom.type === 'Polygon') return geom.coordinates.map(ringPath).join('');
  if (geom.type === 'MultiPolygon') return geom.coordinates.flatMap((p) => p.map(ringPath)).join('');
  return '';
}

export default function WorldCoverageMap({ covered = [] }) {
  const [features, setFeatures] = useState(null);
  useEffect(() => {
    let on = true;
    fetch('/world-countries.geojson')
      .then((r) => r.json())
      .then((d) => { if (on) setFeatures(d.features || []); })
      .catch(() => { if (on) setFeatures([]); });
    return () => { on = false; };
  }, []);

  const coveredNum = new Set(
    (covered || []).map((c) => A2_TO_NUM[String(c).toUpperCase()]).filter(Boolean));

  if (features === null) {
    return <div style={{ fontSize: '.8rem', color: 'var(--color-text-tertiary)' }}>Loading map…</div>;
  }
  // Draw uncovered first, covered last (so highlights sit on top).
  const ordered = [...features].sort(
    (a, b) => (coveredNum.has(String(a.id)) ? 1 : 0) - (coveredNum.has(String(b.id)) ? 1 : 0));

  return (
    <div>
      <svg viewBox="0 28 800 300" style={{ width: '100%', maxWidth: 760, background: '#f1f5f9', borderRadius: 8 }}
           role="img" aria-label="World map of covered countries">
        {ordered.map((f, i) => {
          const on = coveredNum.has(String(f.id));
          return (
            <path key={i} d={pathFor(f.geometry)}
              fill={on ? '#f97316' : '#e2e6ea'} stroke={on ? '#ea580c' : '#cbd2d9'}
              strokeWidth={on ? 0.6 : 0.3}>
              <title>{f.properties?.name}{on ? ' — covered' : ''}</title>
            </path>
          );
        })}
      </svg>
      <div style={{ display: 'flex', gap: '1rem', marginTop: '.5rem', fontSize: '.78rem', color: 'var(--color-text-secondary)' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '.35rem' }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: '#f97316', display: 'inline-block' }} /> Covered
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '.35rem' }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: '#e2e6ea', display: 'inline-block' }} /> Not covered
        </span>
      </div>
    </div>
  );
}

/** "US" → "🇺🇸". */
export function flagEmoji(code) {
  if (!code || code.length !== 2) return '';
  return String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
}

export const COUNTRY_NAMES = {
  US: 'United States', CA: 'Canada', GB: 'United Kingdom', MX: 'Mexico', IE: 'Ireland',
  FR: 'France', DE: 'Germany', IT: 'Italy', ES: 'Spain', PT: 'Portugal', NL: 'Netherlands',
  BE: 'Belgium', CH: 'Switzerland', AT: 'Austria', SE: 'Sweden', NO: 'Norway', DK: 'Denmark',
  FI: 'Finland', PL: 'Poland', GR: 'Greece', RO: 'Romania', HU: 'Hungary', RU: 'Russia',
  UA: 'Ukraine', IN: 'India', CN: 'China', JP: 'Japan', KR: 'South Korea', AU: 'Australia',
  NZ: 'New Zealand', ZA: 'South Africa', NG: 'Nigeria', GH: 'Ghana', KE: 'Kenya', EG: 'Egypt',
  MA: 'Morocco', AE: 'UAE', SA: 'Saudi Arabia', IL: 'Israel', TR: 'Turkey', ID: 'Indonesia',
  MY: 'Malaysia', SG: 'Singapore', TH: 'Thailand', PH: 'Philippines', VN: 'Vietnam',
  PK: 'Pakistan', BD: 'Bangladesh', CO: 'Colombia', PE: 'Peru', AR: 'Argentina', CL: 'Chile',
  BR: 'Brazil', PR: 'Puerto Rico', GU: 'Guam',
};
