import { describe, it, expect, vi } from 'vitest';
import { thumbnailFromFile } from '../utils/imageThumbnail';

/**
 * The meal photo thumbnail.
 *
 * Two jobs, one picture: it shows in the chip the moment a photo is chosen —
 * "IMG_0675.jpeg" tells nobody which photo they attached, and on a phone every
 * shot taken in the same minute has near enough the same name — and it is
 * saved with the meal so the food log can show what each entry was.
 */

describe('thumbnailFromFile', () => {
  it('refuses a non-image without throwing', async () => {
    // A meal must stay savable when its attachment is not a picture.
    const f = new File(['not an image'], 'notes.txt', { type: 'text/plain' });
    expect(await thumbnailFromFile(f)).toBeNull();
  });

  it('returns null for nothing at all rather than blowing up', async () => {
    expect(await thumbnailFromFile(null)).toBeNull();
    expect(await thumbnailFromFile(undefined)).toBeNull();
  });

  it('resolves null when the bytes cannot be decoded', async () => {
    // jsdom cannot decode images, so Image.onerror fires — which is exactly
    // the corrupt-file path, and it must not reject.
    const f = new File([new Uint8Array([1, 2, 3])], 'broken.jpg', { type: 'image/jpeg' });
    await expect(thumbnailFromFile(f)).resolves.toBeNull();
  });

  it('never rejects — a failed thumbnail must not block saving the meal', async () => {
    const f = new File([new Uint8Array([0])], 'x.png', { type: 'image/png' });
    let threw = false;
    try { await thumbnailFromFile(f); } catch { threw = true; }
    expect(threw).toBe(false);
  });
});

describe('the log row', () => {
  it('keeps the camera icon for meals that predate thumbnails', () => {
    // Entries logged before this existed have `food_image_uris` and no
    // thumbnail. Rendering only thumbnails would hide their photos entirely.
    const legacy = { food_image_uris: '/media/12', food_thumbnail: null };
    const modern = { food_image_uris: '/media/13', food_thumbnail: 'data:image/jpeg;base64,AA' };
    const showsIcon = (l) => Boolean(l.food_image_uris && !l.food_thumbnail);
    expect(showsIcon(legacy)).toBe(true);
    expect(showsIcon(modern)).toBe(false);
  });
});
