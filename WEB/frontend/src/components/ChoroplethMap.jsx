/**
 * Disease-surveillance choropleth — dependency-free + offline. Renders the bundled
 * world GeoJSON (public/world-countries.geojson) with an equirectangular projection
 * and shades each country 0-4 by burden level. Countries with data are clickable
 * (drill-down). Works with React 19 (no map library).
 */
import { useEffect, useMemo, useState } from 'react';
import { NUM_TO_A2 } from '../data/isoCountries';

// Burden ramp: 0 = no data (grey), 1-4 = increasing intensity.
export const LEVEL_COLORS = ['#e2e8f0', '#fde68a', '#fbbf24', '#f97316', '#dc2626'];
export const LEVEL_LABELS = ['No data', 'Low', 'Moderate', 'High', 'Very high'];

const W = 800, H = 400;
const proj = (lon, lat) => [((lon + 180) / 360) * W, ((90 - lat) / 180) * H];

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

/**
 * @param {object}   data      map of ISO2 -> { level, label, name }
 * @param {function} onSelect  (iso2, entry) => void
 * @param {string}   selected  currently selected ISO2
 */
export default function ChoroplethMap({ data = {}, onSelect, selected }) {
  const [features, setFeatures] = useState(null);
  useEffect(() => {
    let on = true;
    fetch('/world-countries.geojson')
      .then((r) => r.json())
      .then((d) => { if (on) setFeatures(d.features || []); })
      .catch(() => { if (on) setFeatures([]); });
    return () => { on = false; };
  }, []);

  // Precompute each feature's iso2 + path once.
  const shapes = useMemo(() => {
    if (!features) return [];
    return features.map((f) => ({
      iso2: NUM_TO_A2[String(f.id)],
      name: f.properties?.name,
      d: pathFor(f.geometry),
    })).filter((s) => s.d);
  }, [features]);

  if (features === null) {
    return <div style={{ fontSize: '.85rem', color: 'var(--color-text-tertiary)', padding: '2rem', textAlign: 'center' }}>Loading map…</div>;
  }

  // Draw low levels first so high-burden / selected countries paint on top.
  const ordered = [...shapes].sort((a, b) => {
    if (a.iso2 === selected) return 1;
    if (b.iso2 === selected) return -1;
    return (data[a.iso2]?.level || 0) - (data[b.iso2]?.level || 0);
  });

  return (
    <div>
      <svg viewBox="0 28 800 300"
           style={{ width: '100%', background: '#eff3f8', borderRadius: 10 }}
           role="img" aria-label="World disease-surveillance map">
        {ordered.map((s, i) => {
          const entry = s.iso2 ? data[s.iso2] : undefined;
          const level = entry?.level || 0;
          const hasData = !!entry && (level > 0 || entry.hasInward);
          const isSel = s.iso2 && s.iso2 === selected;
          return (
            <path key={i} d={s.d}
              fill={LEVEL_COLORS[level] || LEVEL_COLORS[0]}
              stroke={isSel ? '#0f172a' : '#cbd5e1'}
              strokeWidth={isSel ? 1.6 : 0.3}
              style={{ cursor: entry ? 'pointer' : 'default', transition: 'fill .15s' }}
              onClick={() => entry && onSelect && onSelect(s.iso2, entry)}>
              <title>{entry?.name || s.name}{entry ? ` — ${entry.label || LEVEL_LABELS[level]}` : ''}</title>
            </path>
          );
        })}
      </svg>

      <div style={{ display: 'flex', gap: '.9rem', marginTop: '.6rem', fontSize: '.74rem', color: 'var(--color-text-secondary)', flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontWeight: 600 }}>Burden:</span>
        {LEVEL_LABELS.map((lbl, i) => (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: '.3rem' }}>
            <span style={{ width: 13, height: 13, borderRadius: 3, background: LEVEL_COLORS[i], border: '1px solid #cbd5e1', display: 'inline-block' }} />
            {lbl}
          </span>
        ))}
      </div>
    </div>
  );
}
