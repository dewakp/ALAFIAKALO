/**
 * FDA recall descriptions are a product name followed by every package
 * configuration it shipped in — brand, net weight, UPC, distributor address,
 * repeated fifteen or twenty times in one field. The page rendered that whole
 * string as an <h4>, so a single recall filled the screen in bold.
 *
 * The enumeration is real information — a patient checking their carton needs
 * the UPC — but it is DETAIL, not the headline. So it is split out rather than
 * discarded, and shown on request.
 *
 * The split is on the SHAPE of the text (a numbered list appearing mid-string),
 * not on FDA's particular wording, so a differently-phrased description still
 * separates correctly instead of being special-cased.
 */

/** Where a " 1. " style enumeration begins, or -1. */
function enumerationStart(text) {
  // Require the list to start at 1 and to sit after some prose, so a
  // description that merely contains a decimal ("Net Wt 1.5 oz") is not split.
  const m = /(?:^|[\s:;.])1\.\s+\S/.exec(text);
  if (!m) return -1;
  const at = m.index === 0 ? 0 : m.index + 1;
  return at > 24 ? at : -1;
}

/** Split a numbered run into its items. */
function splitItems(text) {
  const parts = text.split(/(?=(?:^|\s)\d{1,2}\.\s+\S)/).map((s) => s.trim());
  return parts.filter(Boolean);
}

/**
 * → { title, items, trailing }
 *
 * `title` is always safe to render as a heading; `items` may be empty.
 */
export function summariseRecall(description) {
  const text = String(description || '').replace(/\s+/g, ' ').trim();
  if (!text) return { title: 'Unnamed product', items: [] };

  const at = enumerationStart(text);
  if (at === -1) {
    // No enumeration. Long single-sentence descriptions still need a ceiling.
    if (text.length <= 180) return { title: text, items: [] };
    const cut = text.lastIndexOf(' ', 180);
    return { title: text.slice(0, cut > 80 ? cut : 180) + '…', items: [text] };
  }

  let title = text.slice(0, at).trim().replace(/[,:;]\s*$/, '');
  // "…packaged in the following configurations" adds nothing once the
  // configurations are a list of their own.
  title = title.replace(/\s+(packaged|available|sold)\s+in\s+the\s+following.*$/i, '');
  return {
    title: title || text.slice(0, 120),
    items: splitItems(text.slice(at)),
  };
}
