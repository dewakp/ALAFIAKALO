import { useState, useCallback } from 'react';
import { fahrenheitToCelsius, celsiusToFahrenheit } from '../utils/units';

// App-wide temperature unit preference. US default is °F; storage is always
// Celsius (canonical). The chosen unit drives BOTH input and display, and is
// remembered across entries/sessions via localStorage.
const KEY = 'alafia_temp_unit';

export function useTempUnit() {
  const [unit, setUnit] = useState(() => localStorage.getItem(KEY) || 'F');

  const toggle = useCallback(() => {
    setUnit((u) => {
      const next = u === 'F' ? 'C' : 'F';
      localStorage.setItem(KEY, next);
      return next;
    });
  }, []);

  // Entered value (in the chosen unit) → Celsius for storage.
  const toCelsius = useCallback((v) => {
    if (v === '' || v == null) return null;
    const n = Number(v);
    if (Number.isNaN(n)) return null;
    return unit === 'F' ? fahrenheitToCelsius(n) : n;
  }, [unit]);

  // Stored Celsius → number in the chosen display unit.
  const fromCelsius = useCallback((c) => {
    if (c === '' || c == null) return null;
    const n = Number(c);
    if (Number.isNaN(n)) return null;
    return unit === 'F' ? celsiusToFahrenheit(n) : n;
  }, [unit]);

  // Format stored Celsius for display, e.g. "98.6 °F".
  const fmt = useCallback((c, dp = 1) => {
    const v = fromCelsius(c);
    return v == null ? '—' : `${v.toFixed(dp)} °${unit}`;
  }, [fromCelsius, unit]);

  // Convert an in-progress value from the current unit to the other unit
  // (used right before toggling so the displayed number stays the same temp).
  const convertInPlace = useCallback((v) => {
    if (v === '' || v == null) return v;
    const n = Number(v);
    if (Number.isNaN(n)) return v;
    return unit === 'F' ? fahrenheitToCelsius(n) : celsiusToFahrenheit(n);
  }, [unit]);

  return { unit, label: `°${unit}`, toggle, toCelsius, fromCelsius, fmt, convertInPlace };
}
