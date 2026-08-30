import { useEffect, useMemo, useState } from 'react';
import api from '../services/api';

/**
 * Every nutrient recorded for one meal, paginated.
 *
 * The meals diary rendered a literal list of 15 nutrients with fixed colour
 * thresholds — `phosphorus danger: 1000` applied to every patient, dialysis or
 * not. Meanwhile the backend already holds a 116-nutrient catalog carrying each
 * one's USDA FoodData Central id, and a log carries ~109 values across its
 * typed columns and `extended_nutrients`. Ninety-odd of them were unreachable.
 *
 * Names, units and categories come from `/nutrition/nutrient-catalog`, so there
 * is ONE catalog rather than a second copy maintained by hand here; adding a
 * nutrient upstream shows up with no frontend change. Thresholds come from that
 * same response's `goal`/`goal_kind`, which are computed for THIS patient.
 */

const PAGE_SIZE = 12;

// Fetched once per session — the catalog is reference data, identical for
// every meal on the page, and re-fetching it per card would be 116 rows a time.
let catalogPromise = null;
function loadCatalog() {
  if (!catalogPromise) {
    catalogPromise = api
      .get('/nutrition/nutrient-catalog', { params: { page: 1, page_size: 200 } })
      .then(({ data }) => data)
      .catch((e) => { catalogPromise = null; throw e; });
  }
  return catalogPromise;
}

function fmt(value, unit) {
  if (value == null) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const rounded = n >= 100 ? Math.round(n) : Math.round(n * 100) / 100;
  return `${rounded}${unit ? ` ${unit}` : ''}`;
}

/** Colour against the patient's OWN figure, or neutral when they have none. */
function toneFor(item, value) {
  if (value == null || item.goal == null) return null;
  const ratio = Number(value) / Number(item.goal);
  if (item.goal_kind === 'limit') {
    if (ratio > 1) return { bg: 'rgba(239,68,68,.14)', fg: '#b91c1c' };
    if (ratio > 0.8) return { bg: 'rgba(245,158,11,.14)', fg: '#b45309' };
    return { bg: 'rgba(34,197,94,.12)', fg: '#15803d' };
  }
  if (ratio >= 0.8) return { bg: 'rgba(34,197,94,.12)', fg: '#15803d' };
  if (ratio >= 0.4) return { bg: 'rgba(245,158,11,.14)', fg: '#b45309' };
  return { bg: 'rgba(239,68,68,.10)', fg: '#b91c1c' };
}

export default function NutrientPanel({ log }) {
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState('');

  useEffect(() => {
    let alive = true;
    loadCatalog()
      .then((d) => alive && setCatalog(d))
      // A failed catalog fetch must say so. Falling back to raw keys would
      // present "fa_20_5_epa_g" to a patient as though that were the name.
      .catch(() => alive && setError('Could not load the nutrient reference.'));
    return () => { alive = false; };
  }, []);

  // Only nutrients this meal actually has a value for. An absent nutrient is
  // not zero — it was never measured for this food.
  const present = useMemo(() => {
    if (!catalog) return [];
    const extended = log.extended_nutrients || {};
    return catalog.items
      .map((item) => ({
        item,
        value: log[item.key] != null ? log[item.key] : extended[item.key],
      }))
      .filter((row) => row.value != null);
  }, [catalog, log]);

  const filtered = useMemo(
    () => (category ? present.filter((r) => r.item.category === category) : present),
    [present, category],
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const window_ = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const categoriesPresent = useMemo(
    () => [...new Set(present.map((r) => r.item.category))].sort(),
    [present],
  );

  if (error) {
    return <div style={{ fontSize: '.75rem', color: '#b45309', padding: '.5rem 0' }}>{error}</div>;
  }
  if (!catalog) {
    return <div style={{ fontSize: '.75rem', color: 'var(--color-text-tertiary)', padding: '.5rem 0' }}>Loading nutrients…</div>;
  }
  if (!present.length) {
    return (
      <div style={{ fontSize: '.75rem', color: 'var(--color-text-tertiary)', padding: '.5rem 0' }}>
        No nutrient values recorded for this meal yet.
      </div>
    );
  }

  return (
    <div style={{ marginTop: '.5rem' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.3rem', marginBottom: '.5rem', alignItems: 'center' }}>
        <button
          onClick={() => { setCategory(''); setPage(1); }}
          style={chipStyle(category === '')}>
          All ({present.length})
        </button>
        {categoriesPresent.map((c) => (
          <button key={c} onClick={() => { setCategory(c); setPage(1); }} style={chipStyle(category === c)}>
            {c}
          </button>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '.35rem' }}>
        {window_.map(({ item, value }) => {
          const tone = toneFor(item, value);
          return (
            <div key={item.key}
              title={item.usda_id ? `USDA FoodData Central nutrient ${item.usda_id}` : item.key}
              style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                gap: '.4rem', padding: '.3rem .45rem', borderRadius: 4, fontSize: '.72rem',
                background: tone ? tone.bg : 'var(--color-surface-alt, rgba(127,127,127,.08))',
              }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>{item.name}</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 600, color: tone ? tone.fg : 'var(--color-text-primary)' }}>
                {fmt(value, item.unit)}
                {item.goal != null && (
                  <span style={{ fontWeight: 400, opacity: .65 }}>
                    {' / '}{fmt(item.goal, '')}
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>

      {totalPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginTop: '.5rem', fontSize: '.72rem' }}>
          <button disabled={safePage <= 1} onClick={() => setPage(safePage - 1)} style={pagerStyle(safePage <= 1)}>
            ‹ Prev
          </button>
          <span style={{ color: 'var(--color-text-tertiary)' }}>
            Page {safePage} of {totalPages} · {filtered.length} nutrients
          </span>
          <button disabled={safePage >= totalPages} onClick={() => setPage(safePage + 1)} style={pagerStyle(safePage >= totalPages)}>
            Next ›
          </button>
        </div>
      )}
    </div>
  );
}

const chipStyle = (active) => ({
  fontSize: '.68rem', padding: '.15rem .45rem', borderRadius: 999, cursor: 'pointer',
  border: '1px solid var(--color-border)',
  background: active ? 'var(--color-primary)' : 'transparent',
  color: active ? '#fff' : 'var(--color-text-secondary)',
});

const pagerStyle = (disabled) => ({
  fontSize: '.7rem', padding: '.15rem .5rem', borderRadius: 4, cursor: disabled ? 'default' : 'pointer',
  border: '1px solid var(--color-border)', background: 'transparent',
  color: disabled ? 'var(--color-text-tertiary)' : 'var(--color-text-secondary)',
  opacity: disabled ? .5 : 1,
});
