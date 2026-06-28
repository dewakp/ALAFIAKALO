/**
 * US coverage tile-grid map (statebins style). Dependency-free + offline — each
 * state is a labelled square in an approximate geographic layout; covered states
 * are highlighted. Used to overlay the regions a recall reaches.
 */

// [col, row] for each state — a verified, overlap-free US tile grid (11×8).
const GRID = {
  AK: [0, 0], ME: [10, 0],
  VT: [9, 1], NH: [10, 1],
  WA: [0, 2], ID: [1, 2], MT: [2, 2], ND: [3, 2], MN: [4, 2], IL: [5, 2], WI: [6, 2], MI: [7, 2], NY: [8, 2], RI: [9, 2], MA: [10, 2],
  OR: [0, 3], NV: [1, 3], WY: [2, 3], SD: [3, 3], IA: [4, 3], IN: [5, 3], OH: [6, 3], PA: [7, 3], NJ: [8, 3], CT: [9, 3],
  CA: [0, 4], UT: [1, 4], CO: [2, 4], NE: [3, 4], MO: [4, 4], KY: [5, 4], WV: [6, 4], VA: [7, 4], MD: [8, 4], DE: [9, 4],
  AZ: [1, 5], NM: [2, 5], KS: [3, 5], AR: [4, 5], TN: [5, 5], NC: [6, 5], SC: [7, 5], DC: [8, 5],
  OK: [3, 6], LA: [4, 6], MS: [5, 6], AL: [6, 6], GA: [7, 6],
  HI: [0, 7], TX: [3, 7], FL: [8, 7],
};

const CELL = 34;
const GAP = 3;
const COLS = 11;
const ROWS = 8;

export default function USCoverageMap({ covered = [], nationwide = false }) {
  const coveredSet = new Set((covered || []).map((s) => s.toUpperCase()));
  const width = COLS * (CELL + GAP);
  const height = ROWS * (CELL + GAP);

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', maxWidth: 460 }}
           role="img" aria-label="US states covered by recall">
        {Object.entries(GRID).map(([code, [col, row]]) => {
          const on = nationwide || coveredSet.has(code);
          return (
            <g key={code} transform={`translate(${col * (CELL + GAP)}, ${row * (CELL + GAP)})`}>
              <rect width={CELL} height={CELL} rx={5}
                fill={on ? '#f97316' : '#eef0f2'}
                stroke={on ? '#ea580c' : '#e2e5e9'} strokeWidth={1}>
                <title>{code}{on ? ' — covered' : ''}</title>
              </rect>
              <text x={CELL / 2} y={CELL / 2 + 4} textAnchor="middle"
                fontSize={11} fontWeight={600}
                fill={on ? '#fff' : '#9aa1a9'}>{code}</text>
            </g>
          );
        })}
      </svg>
      <div style={{ display: 'flex', gap: '1rem', marginTop: '.5rem', fontSize: '.78rem', color: 'var(--color-text-secondary)' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '.35rem' }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: '#f97316', display: 'inline-block' }} /> Covered
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '.35rem' }}>
          <span style={{ width: 12, height: 12, borderRadius: 3, background: '#eef0f2', display: 'inline-block' }} /> Not covered
        </span>
        {nationwide && <span style={{ color: '#ea580c', fontWeight: 600 }}>Nationwide distribution</span>}
      </div>
    </div>
  );
}
