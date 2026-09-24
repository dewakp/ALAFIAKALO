/* Social sign-in against the providers directly — no Firebase broker.
 *
 * The browser completes the flow with Google or Apple and gets THEIR ID token;
 * the backend verifies it against the provider's published JWKS at
 * POST /auth/oidc. That removes the Firebase JS SDK, a second identity store,
 * and the failure surface that produced `auth/internal-error` in production —
 * where, separately, Apple had never been configured as a provider at all and
 * the server-side exchange answered 503 because no Admin credential was ever
 * mounted.
 *
 * The two providers are NOT symmetrical, and pretending otherwise is how this
 * gets broken:
 *
 *   Google — does not hand an ID token to an arbitrary click. It renders its
 *            own button (which its branding rules require in any case) and
 *            calls back with a credential.
 *   Apple  — signs in from any control: AppleID.auth.signIn() resolves with
 *            authorization.id_token.
 */

/* Public by design — an OAuth client id travels in every authorization request,
 * exactly like Firebase's web apiKey did. Overridable per environment. */
export const GOOGLE_CLIENT_ID =
  import.meta.env.VITE_GOOGLE_CLIENT_ID ||
  '214891981468-8k22g0heta01kcflao4vfupm8uqgit6r.apps.googleusercontent.com';

/* Apple's Services ID. Deliberately NO fallback: a wrong value produces an
 * opaque Apple error, and a button that cannot work is worse than no button
 * (§3ar). `isAppleConfigured()` gates whether it is offered at all. */
export const APPLE_SERVICES_ID = import.meta.env.VITE_APPLE_SERVICES_ID || '';

export const isAppleConfigured = () => Boolean(APPLE_SERVICES_ID);

const GOOGLE_SRC = 'https://accounts.google.com/gsi/client';
const APPLE_SRC =
  'https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js';

/** Load a provider script once. Rejects rather than hanging if it is blocked —
 *  an ad blocker or a CSP will stop these, and a silent hang looks like a dead
 *  button. */
function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === 'true') { resolve(); return; }
      existing.addEventListener('load', () => resolve());
      existing.addEventListener('error', () => reject(new Error('blocked')));
      return;
    }
    const el = document.createElement('script');
    el.src = src;
    el.async = true;
    el.onload = () => { el.dataset.loaded = 'true'; resolve(); };
    el.onerror = () => reject(new Error('blocked'));
    document.head.appendChild(el);
  });
}

/**
 * Render Google's own sign-in button into `container`.
 *
 * `onToken(idToken)` receives the credential. Returns a cleanup function.
 * Rendering rather than calling: GIS only issues an ID token through its own
 * button or One Tap, and One Tap can be suppressed silently by the browser —
 * which would read as a button that does nothing.
 */
export async function renderGoogleButton(container, onToken, onError) {
  try {
    await loadScript(GOOGLE_SRC);
  } catch {
    onError?.(new Error('script-blocked'));
    return () => {};
  }
  const google = window.google;
  if (!google?.accounts?.id) {
    onError?.(new Error('script-blocked'));
    return () => {};
  }

  google.accounts.id.initialize({
    client_id: GOOGLE_CLIENT_ID,
    callback: (response) => {
      if (response?.credential) onToken(response.credential);
      else onError?.(new Error('no-credential'));
    },
    ux_mode: 'popup',
role: undefined,
  });
  google.accounts.id.renderButton(container, {
    theme: 'outline', size: 'large', width: container.offsetWidth || 320,
    text: 'signin_with', shape: 'rectangular',
  });

  return () => { try { google.accounts.id.cancel(); } catch { /* already gone */ } };
}

/** Apple sign-in from our own button → Apple's ID token. */
export async function signInWithApple() {
  if (!isAppleConfigured()) {
    throw new Error('apple-not-configured');
  }
  await loadScript(APPLE_SRC);
  const AppleID = window.AppleID;
  if (!AppleID?.auth) throw new Error('script-blocked');

  AppleID.auth.init({
    clientId: APPLE_SERVICES_ID,
    scope: 'name email',
    redirectURI: `${window.location.origin}/login`,
    usePopup: true,
  });

  const result = await AppleID.auth.signIn();
  const idToken = result?.authorization?.id_token;
  if (!idToken) throw new Error('no-credential');
  return idToken;
}

/** A sentence for the failures these flows actually produce. */
export function oidcErrorMessage(err, fallback) {
  const raw = err?.error || err?.message || '';
  const map = {
    // Apple reports a closed popup this way; Google's cancel is silent.
    popup_closed_by_user: 'Sign-in was closed before it finished.',
    user_cancelled_authorize: 'Sign-in was cancelled.',
    'script-blocked':
      'The sign-in provider could not be loaded — an extension or network policy may be blocking it.',
    'no-credential': 'The provider did not return a sign-in token. Please try again.',
    'apple-not-configured': 'Apple sign-in is not available yet.',
  };
  return map[raw] || fallback;
}
