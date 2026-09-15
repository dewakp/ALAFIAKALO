import { afterEach, describe, expect, it } from 'vitest';
import i18n, { normaliseLanguage, SUPPORTED_LANGUAGES } from '../i18n';
import api from '../services/api';

// The assistant answers in the patient's language and falls back to the one the
// app is set to, which every request carries as X-Client-Language. Profiles
// store both "en" (web) and "English" (iOS), so both must resolve.
describe('patient language', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it.each([
    ['en', 'en'],
    ['English', 'en'],
    ['fr-FR', 'fr'],
    ['pt_BR', 'pt'],
    ['Français', 'fr'],
    ['Yorùbá', 'yo'],
    ['Engish', null], // a typo is refused, not guessed at
    ['', null],
    [null, null],
  ])('resolves a stored %j to %j', (stored, expected) => {
    expect(normaliseLanguage(stored)).toBe(expected);
  });

  it('offers the eleven product languages', () => {
    expect(SUPPORTED_LANGUAGES.map((lang) => lang.code)).toEqual(
      ['en', 'es', 'fr', 'de', 'pt', 'ar', 'zh', 'yo', 'ig', 'ha', 'sw'],
    );
  });

  it('sends the app language on every request', async () => {
    await i18n.changeLanguage('ha');
    const handler = api.interceptors.request.handlers.find(Boolean);
    const config = await handler.fulfilled({ headers: {}, method: 'get' });
    expect(config.headers['X-Client-Language']).toBe('ha');
  });
});
