/**
 * Unit conversions + display helpers — the frontend mirror of the backend
 * `app/core/units.py`.
 *
 * Policy: the API/DB stores **metric** as canonical (kg, cm, °C, mg/dL, mL).
 * These helpers convert canonical metric values to the user's chosen display
 * system at the edge, and convert user-entered imperial values back to metric
 * before they are persisted.
 */

export const METRIC = 'metric';
export const IMPERIAL = 'imperial';

// ── Temperature ────────────────────────────────────────────────────────────
export const celsiusToFahrenheit = (v) => round(v * 9 / 5 + 32, 1);
export const fahrenheitToCelsius = (v) => round((v - 32) * 5 / 9, 2);

// ── Mass ───────────────────────────────────────────────────────────────────
export const kgToLb = (v) => round(v / 0.45359237, 1);
export const lbToKg = (v) => round(v * 0.45359237, 3);

// ── Length ─────────────────────────────────────────────────────────────────
export const cmToIn = (v) => round(v / 2.54, 1);
export const inToCm = (v) => round(v * 2.54, 2);

// ── Volume ─────────────────────────────────────────────────────────────────
export const mlToFlOz = (v) => round(v / 29.5735295625, 1);
export const flOzToMl = (v) => round(v * 29.5735295625, 2);

// ── Glucose ────────────────────────────────────────────────────────────────
const GLUCOSE_MGDL_PER_MMOL = 18.0182;
export const mgdlToMmol = (v) => round(v / GLUCOSE_MGDL_PER_MMOL, 2);
export const mmolToMgdl = (v) => round(v * GLUCOSE_MGDL_PER_MMOL, 1);

// ── Measurement registry ────────────────────────────────────────────────────
// measurement → { metric: label, imperial: label, toImperial, toMetric }
const MEASUREMENTS = {
  temperature: { metric: '°C', imperial: '°F', toImperial: celsiusToFahrenheit, toMetric: fahrenheitToCelsius },
  mass:        { metric: 'kg', imperial: 'lb', toImperial: kgToLb,             toMetric: lbToKg },
  length:      { metric: 'cm', imperial: 'in', toImperial: cmToIn,            toMetric: inToCm },
  volume:      { metric: 'mL', imperial: 'fl oz', toImperial: mlToFlOz,       toMetric: flOzToMl },
  glucose:     { metric: 'mg/dL', imperial: 'mmol/L', toImperial: mgdlToMmol, toMetric: mmolToMgdl },
};

/** Unit label for a measurement in the given system, e.g. unitLabel('mass','imperial') → 'lb'. */
export function unitLabel(measurement, system = METRIC) {
  const m = MEASUREMENTS[measurement];
  if (!m) return '';
  return system === IMPERIAL ? m.imperial : m.metric;
}

/** Convert a canonical (metric) value into the requested display system. */
export function convertForDisplay(value, measurement, system = METRIC) {
  if (value === null || value === undefined || value === '') return value;
  const m = MEASUREMENTS[measurement];
  if (!m || system !== IMPERIAL) return Number(value);
  return m.toImperial(Number(value));
}

/** Convert a user-entered display-system value back to canonical metric for storage. */
export function convertToMetric(value, measurement, system = METRIC) {
  if (value === null || value === undefined || value === '') return value;
  const m = MEASUREMENTS[measurement];
  if (!m || system !== IMPERIAL) return Number(value);
  return m.toMetric(Number(value));
}

/** Render a canonical value with its unit attached, e.g. '37.0 °C' / '98.6 °F'. */
export function formatQuantity(value, measurement, system = METRIC, precision = 1) {
  if (value === null || value === undefined || value === '') return '—';
  const converted = convertForDisplay(value, measurement, system);
  const unit = unitLabel(measurement, system);
  return `${Number(converted).toFixed(precision)} ${unit}`.trim();
}

function round(n, dp) {
  const f = 10 ** dp;
  return Math.round(Number(n) * f) / f;
}
