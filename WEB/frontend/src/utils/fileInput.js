/**
 * Take files off an <input type="file"> in a form that survives clearing it.
 *
 * A file input has to be reset (`e.target.value = ''`) or picking the SAME file
 * twice never fires `change` again. But clearing it detaches the File objects
 * it produced in WebKit: they keep their metadata — `name`, `size`, `type` — so
 * anything showing a filename still looks correct, while the underlying data is
 * gone. FormData then serialises them as empty parts, and FileReader reads
 * nothing.
 *
 * That is not hypothetical. Production logged two `/ai/vision` uploads from
 * Safari at **6360 bytes each** — of which 5329 was the auth token — from a form
 * that visibly had two JPEGs attached. Both request sizes were identical
 * despite different photos, because neither carried any image data. The backend
 * answered "No image file provided", which was accurate and looked absurd.
 *
 * Re-wrapping each File around its own ArrayBuffer makes it independent of the
 * input element, so the reset cannot reach it. Read the bytes BEFORE clearing.
 *
 * @param {FileList|File[]|null} fileList  files from the input event
 * @param {number} [limit]                 max files to take
 * @returns {Promise<File[]>}              standalone copies, safe to keep
 */
export async function detachFiles(fileList, limit = Infinity) {
  const picked = Array.from(fileList || []).slice(0, Math.max(0, limit));
  return Promise.all(
    picked.map(async (f) =>
      new File([await readBytes(f)], f.name, {
        type: f.type || 'application/octet-stream',
        lastModified: f.lastModified,
      })
    )
  );
}

/**
 * Blob bytes, via `arrayBuffer()` where it exists and FileReader where it does
 * not. `Blob.arrayBuffer()` only arrived in Safari 14 — and Safari is exactly
 * the engine whose input-reset behaviour makes this module necessary, so the
 * fallback is not academic. jsdom lacks it too, which is how this surfaced.
 */
function readBytes(file) {
  if (typeof file.arrayBuffer === 'function') return file.arrayBuffer();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(file);
  });
}

/** Single-file convenience wrapper. Returns null when nothing was picked. */
export async function detachFile(fileList) {
  const [only] = await detachFiles(fileList, 1);
  return only || null;
}
