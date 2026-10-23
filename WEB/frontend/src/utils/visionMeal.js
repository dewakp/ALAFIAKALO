// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

/* The meal a photo's correction rows describe, in the shape Save sends.

   The rows carry grams the patient checked or corrected; the saved meal is
   re-estimated server-side by parsing `food_name` (nutrient_enrichment →
   estimate_meal_nutrients). Names alone threw the grams away: "3 Pieces of
   Sardines" parses as 300 g, so a patient who corrected it to 100 g logged
   three times the fish. The parser reads a LEADING gram figure ("100 g …");
   one in parentheses after the name is ignored when the name carries a count
   — measured, not assumed.

   Serving size is the meal's TOTAL. It used to be the first item's portion,
   which then stood for the whole plate.

   iOS (FoodVisionEdit.mealDescription) and Android (visionMeal) mirror this. */

function parseGrams(raw) {
  if (raw === '' || raw == null) return null;
  const g = Number(raw);
  return Number.isFinite(g) && g > 0 ? g : null;
}

function formatGrams(g) {
  return Number.isInteger(g) ? String(g) : String(Math.round(g * 10) / 10);
}

export function mealFromVisionRows(rows) {
  const items = (rows || [])
    .map((r) => ({ name: (r.name || '').trim(), grams: parseGrams(r.estimated_grams) }))
    .filter((r) => r.name);

  const food_name = items
    .map((r) => (r.grams != null ? `${formatGrams(r.grams)} g ${r.name}` : r.name))
    .join(', ');

  let serving_size = '';
  if (items.length && items.every((r) => r.grams != null)) {
    const total = items.reduce((s, r) => s + r.grams, 0);
    serving_size = items.length === 1
      ? `${formatGrams(total)} g`
      : `composite meal (${formatGrams(total)} g total)`;
  }
  return { food_name, serving_size };
}
