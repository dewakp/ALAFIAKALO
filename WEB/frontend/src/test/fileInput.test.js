import { describe, it, expect } from 'vitest';
import { detachFile, detachFiles } from '../utils/fileInput';

/**
 * The bug this guards against is invisible in every way that normally matters.
 *
 * A file input must be reset (`e.target.value = ''`) or re-picking the same file
 * never fires `change` again. In WebKit that reset strips the data off the File
 * objects the input produced, while LEAVING their metadata intact — so `name`,
 * `size` and `type` all still read correctly and any chip showing a filename
 * looks perfect. Only the bytes are gone.
 *
 * Production logged two `/ai/vision` uploads from Safari at 6360 bytes each — of
 * which 5329 was the auth token — from a form visibly holding two JPEGs. Both
 * requests were byte-identical in size despite different photos. The backend
 * answered "No image file provided", which was correct and looked absurd.
 */

/** Read a Blob's bytes. jsdom has no Blob.arrayBuffer(), same as Safari < 14. */
function bytesOf(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(Array.from(new Uint8Array(r.result)));
    r.onerror = () => reject(r.error);
    r.readAsArrayBuffer(blob);
  });
}

/** A File whose data is readable, standing in for a live input selection. */
function liveFile(name, bytes) {
  return new File([new Uint8Array(bytes)], name, { type: 'image/jpeg' });
}

describe('detachFiles', () => {
  it('copies the bytes, so the result survives the input being cleared', async () => {
    const [copy] = await detachFiles([liveFile('IMG_0667.jpeg', [1, 2, 3, 4])]);
    expect(await bytesOf(copy)).toEqual([1, 2, 3, 4]);
  });

  it('preserves the metadata the UI renders', async () => {
    const [copy] = await detachFiles([liveFile('IMG_0665.jpeg', [9])]);
    expect(copy.name).toBe('IMG_0665.jpeg');
    expect(copy.type).toBe('image/jpeg');
    expect(copy.size).toBe(1);
  });

  it('produces a File independent of the original', async () => {
    const original = liveFile('a.jpeg', [7, 7]);
    const [copy] = await detachFiles([original]);
    // Not the same object — that identity is the whole point, because the
    // original is the one the input can invalidate.
    expect(copy).not.toBe(original);
    expect(copy).toBeInstanceOf(File);
  });

  it('honours the limit (the picker allows at most 3 images)', async () => {
    const many = [1, 2, 3, 4, 5].map((n) => liveFile(`${n}.jpeg`, [n]));
    expect(await detachFiles(many, 3)).toHaveLength(3);
  });

  it('handles an empty or absent selection', async () => {
    expect(await detachFiles(null)).toEqual([]);
    expect(await detachFiles([])).toEqual([]);
    expect(await detachFile(null)).toBeNull();
  });

  it('defaults a missing MIME type rather than sending an empty one', async () => {
    const typeless = new File([new Uint8Array([1])], 'scan', { type: '' });
    const [copy] = await detachFiles([typeless]);
    expect(copy.type).toBe('application/octet-stream');
  });
});

describe('detachFile', () => {
  it('returns a single usable copy', async () => {
    const copy = await detachFile([liveFile('label.jpeg', [5, 6])]);
    expect(copy.name).toBe('label.jpeg');
    expect(await bytesOf(copy)).toEqual([5, 6]);
  });
});
