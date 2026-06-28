import { useUnits } from '../context/UnitsContext';
import { METRIC, IMPERIAL } from '../utils/units';

/**
 * Segmented Metric / Imperial control. Reads and writes the shared UnitsContext,
 * which persists the choice to the backend. Drop it anywhere a units switch is
 * useful (Profile preferences, settings, page headers).
 */
export default function UnitToggle({ size = 'md' }) {
  const { system, setSystem } = useUnits();
  const pad = size === 'sm' ? '0.25rem 0.6rem' : '0.4rem 0.9rem';

  const optionStyle = (active) => ({
    padding: pad,
    border: 'none',
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: size === 'sm' ? '0.8rem' : '0.9rem',
    background: active ? 'var(--color-primary, #2563eb)' : 'transparent',
    color: active ? '#fff' : 'var(--color-text-secondary, #555)',
    transition: 'background 0.15s ease',
  });

  return (
    <div
      role="group"
      aria-label="Measurement system"
      style={{
        display: 'inline-flex',
        border: '1px solid var(--color-border, #d1d5db)',
        borderRadius: '999px',
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        aria-pressed={system === METRIC}
        style={optionStyle(system === METRIC)}
        onClick={() => setSystem(METRIC)}
      >
        Metric
      </button>
      <button
        type="button"
        aria-pressed={system === IMPERIAL}
        style={optionStyle(system === IMPERIAL)}
        onClick={() => setSystem(IMPERIAL)}
      >
        Imperial
      </button>
    </div>
  );
}
