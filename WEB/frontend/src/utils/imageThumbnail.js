/**
 * A small thumbnail of a chosen meal photo, made in the browser.
 *
 * Two jobs, and they are the same picture: the chip beside "Choose Files"
 * shows it immediately, and it is saved with the meal so the food log can show
 * which photo each entry came from.
 *
 * Done client-side deliberately. The alternative is uploading the original to
 * get a thumbnail back, which means a patient who picks a photo and never runs
 * the analysis uploads a multi-megabyte file for a 48 px image — and gets
 * nothing if they then cancel.
 */

/** Longest edge of the stored thumbnail, in pixels. */
const MAX_EDGE = 96;

/** JPEG quality. 0.7 is indistinguishable at this size and roughly halves it. */
const QUALITY = 0.7;

/**
 * Read a File into a `data:` URI thumbnail.
 *
 * Resolves to null rather than throwing when the file cannot be decoded — a
 * meal must still be savable when its picture is unreadable. The photo itself
 * is never altered; this is an extra, not a replacement.
 */
export function thumbnailFromFile(file) {
  return new Promise((resolve) => {
    if (!file || !file.type?.startsWith('image/')) { resolve(null); return; }

    // Guarded: if object URLs are unavailable the whole function must still
    // RESOLVE null, never reject. A rejected promise here propagates into the
    // save handler and loses the meal the patient just typed — the thumbnail
    // is a nicety, the meal is the record.
    let url;
    try {
      url = URL.createObjectURL(file);
    } catch {
      resolve(null);
      return;
    }

    const img = new Image();

    img.onload = () => {
      try {
        const scale = Math.min(1, MAX_EDGE / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));

        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        // A transparent PNG would otherwise composite onto black; meals
        // photographed against a light table then render as a dark square.
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, w, h);
        ctx.drawImage(img, 0, 0, w, h);

        resolve(canvas.toDataURL('image/jpeg', QUALITY));
      } catch {
        resolve(null);
      } finally {
        URL.revokeObjectURL(url);
      }
    };

    img.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
    img.src = url;
  });
}
