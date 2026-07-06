/* Firebase Auth client — powers phone (OTP) and social (Google / Apple) sign-in.
 *
 * The provider flow completes client-side with the Firebase JS SDK; the minted
 * ID token is then exchanged at POST /auth/firebase for ALAFIA's own JWTs.
 * The apiKey is Firebase's public web client key (not a secret); override via
 * VITE_FIREBASE_* env vars if the project ever changes.
 */
import { initializeApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  OAuthProvider,
  RecaptchaVerifier,
  signInWithPopup,
  signInWithPhoneNumber,
} from 'firebase/auth';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || 'AIzaSyCVG5VUkGUfsbU8mNyFXcnLGKyARPiCw50',
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || 'alafia-9i0hh.firebaseapp.com',
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || 'alafia-9i0hh',
};

let _auth = null;
function auth() {
  if (!_auth) _auth = getAuth(initializeApp(firebaseConfig));
  return _auth;
}

/** Google sign-in popup → Firebase ID token. */
export async function signInWithGoogle() {
  const cred = await signInWithPopup(auth(), new GoogleAuthProvider());
  return cred.user.getIdToken();
}

/** Apple sign-in popup → Firebase ID token. */
export async function signInWithApple() {
  const provider = new OAuthProvider('apple.com');
  provider.addScope('email');
  provider.addScope('name');
  const cred = await signInWithPopup(auth(), provider);
  return cred.user.getIdToken();
}

/** Start phone sign-in: sends an SMS code. `containerId` hosts the invisible
 *  reCAPTCHA. Returns a confirmation to pass to confirmPhoneCode. */
export async function startPhoneSignIn(phoneNumber, containerId) {
  const a = auth();
  // Recreate the verifier each attempt — a consumed reCAPTCHA can't be reused.
  if (window._alafiaRecaptcha) {
    try { window._alafiaRecaptcha.clear(); } catch { /* already gone */ }
  }
  window._alafiaRecaptcha = new RecaptchaVerifier(a, containerId, { size: 'invisible' });
  return signInWithPhoneNumber(a, phoneNumber, window._alafiaRecaptcha);
}

/** Complete phone sign-in with the received SMS code → Firebase ID token. */
export async function confirmPhoneCode(confirmation, code) {
  const cred = await confirmation.confirm(code);
  return cred.user.getIdToken();
}

/** Human-readable message for Firebase Auth error codes. */
export function firebaseErrorMessage(err, fallback) {
  const code = err?.code || '';
  const map = {
    'auth/popup-closed-by-user': 'Sign-in window was closed before completing.',
    'auth/cancelled-popup-request': 'Sign-in was cancelled.',
    'auth/popup-blocked': 'The browser blocked the sign-in popup — please allow popups and retry.',
    'auth/account-exists-with-different-credential':
      'An account already exists with this email via a different sign-in method.',
    'auth/invalid-phone-number': 'That phone number is invalid — use international format, e.g. +15551234567.',
    'auth/invalid-verification-code': 'That code is incorrect. Please check and try again.',
    'auth/code-expired': 'That code has expired — request a new one.',
    'auth/too-many-requests': 'Too many attempts — please wait a moment and try again.',
    'auth/operation-not-allowed': 'This sign-in method is not enabled for this project.',
    'auth/unauthorized-domain': 'This domain is not authorized for sign-in (Firebase console → Auth → Settings).',
  };
  return map[code] || err?.message || fallback;
}
