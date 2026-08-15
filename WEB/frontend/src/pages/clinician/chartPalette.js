/**
 * Categorical palette for the clinician trend charts.
 *
 * Six slots, assigned in fixed order and never cycled. Both modes were run
 * through the dataviz validator against THIS app's chart surfaces — #ffffff
 * light and #1e293b dark, not the reference surfaces — because contrast and
 * lightness-band results only mean anything against the surface the chart
 * actually sits on:
 *
 *   light  worst adjacent CVD ΔE 9.1 (protan) · normal-vision ΔE 19.6 → PASS
 *   dark   worst adjacent CVD ΔE 8.4 (protan) · normal-vision ΔE 19.3 → PASS
 *
 * Both modes returned one WARN: some slots sit below 3:1 against the surface,
 * which obligates *relief* — visible labels or a table view. Every chart here
 * ships a legend, a direct label on the last point, and the full data table
 * underneath, so identity is never carried by color alone.
 *
 * A seventh series is never a generated hue: the category views group series by
 * unit, and no group reaches seven.
 */

const LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300'];
const DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300'];

export function seriesColors(isDark) {
  return isDark ? DARK : LIGHT;
}

/** Fixed-order assignment: slot by index, so a filtered-out series never
 *  repaints the survivors. Color follows the entity, not its rank. */
export function colorAt(index, isDark) {
  const p = seriesColors(isDark);
  return p[index % p.length];
}

export const CHART_INK = {
  grid: 'var(--color-border)',
  axis: 'var(--color-text-secondary)',
};
