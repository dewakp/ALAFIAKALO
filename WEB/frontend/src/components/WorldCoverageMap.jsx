/**
 * Country helpers for coverage lists.
 *
 * This file used to render a world map: four highlighted countries across the
 * full width of the page, saying what the line above it already said in words —
 * "Mexico · United States · Canada · United Kingdom". A picture of a sentence is
 * not a visualisation, and it pushed the actual recall content below the fold.
 * FDA coverage is a short list of countries, so it is drawn as a list of chips.
 *
 * The name is kept so the import sites don't churn; only the helpers remain.
 */

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
