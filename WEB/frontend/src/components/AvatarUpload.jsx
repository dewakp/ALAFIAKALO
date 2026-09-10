import { useRef, useState } from 'react';
import api from '../services/api';
import Avatar from './Avatar';
import { apiErrorMessage } from '../utils/apiError';

/**
 * Choose a photo, or take one.
 *
 * Two inputs, not one. `capture="user"` opens the front camera directly on a
 * phone — but on a desktop browser it is ignored and the control degrades to
 * an ordinary file picker, so a single button labelled "Take Photo" would lie
 * on the platform most likely to be used for a long profile edit. The camera
 * button is therefore hidden where there is no camera to open.
 */
const HAS_CAMERA = typeof navigator !== 'undefined'
  && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '');

export default function AvatarUpload({ user, onChange }) {
  const fileRef = useRef(null);
  const cameraRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function send(file) {
    if (!file) return;
    setError('');
    setBusy(true);
    try {
      const body = new FormData();
      body.append('file', file);
      // Let the browser set the multipart boundary; naming Content-Type here
      // omits it and the server cannot parse the body.
      const { data } = await api.post('/users/me/avatar', body);
      onChange?.(data);
    } catch (err) {
      setError(apiErrorMessage(err, 'That photo could not be uploaded.'));
    } finally {
      setBusy(false);
      // Clear the input, or choosing the SAME file again fires no change event.
      if (fileRef.current) fileRef.current.value = '';
      if (cameraRef.current) cameraRef.current.value = '';
    }
  }

  async function remove() {
    setError('');
    setBusy(true);
    try {
      const { data } = await api.delete('/users/me/avatar');
      onChange?.(data);
    } catch (err) {
      setError(apiErrorMessage(err, 'That photo could not be removed.'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
      <Avatar src={user?.profile_picture_url} name={user?.full_name} id={user?.id} size={88} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button type="button" className="btn btn-secondary" disabled={busy}
                  onClick={() => fileRef.current?.click()}>
            {user?.profile_picture_url ? 'Change Photo' : 'Upload Photo'}
          </button>
          {HAS_CAMERA && (
            <button type="button" className="btn btn-secondary" disabled={busy}
                    onClick={() => cameraRef.current?.click()}>
              Take Photo
            </button>
          )}
          {user?.profile_picture_url && (
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={remove}>
              Remove
            </button>
          )}
        </div>
        <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
          {busy ? 'Uploading…' : 'JPEG, PNG, HEIC or WebP — up to 15 MB.'}
        </div>
        {error && <div style={{ fontSize: '0.85rem', color: 'var(--color-danger)' }}>{error}</div>}
      </div>
      <input ref={fileRef} type="file" accept="image/*" hidden
             onChange={(e) => send(e.target.files?.[0])} />
      <input ref={cameraRef} type="file" accept="image/*" capture="user" hidden
             onChange={(e) => send(e.target.files?.[0])} />
    </div>
  );
}
