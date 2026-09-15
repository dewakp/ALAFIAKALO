import React from 'react';
import { useTranslation } from 'react-i18next';
import { SUPPORTED_LANGUAGES, normaliseLanguage, t } from '../i18n';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

/**
 * The language the app is drawn in and, for someone signed in, the saved
 * preference the backend answers them in.
 *
 * Offered on the sign-in page too, where there is no profile: a PATCH there
 * answers 401, which the API client reads as a dead session.
 */
const LanguageSwitcher = ({ variant = 'dropdown' }) => {
  const { i18n } = useTranslation();
  const { user } = useAuth();
  // i18n.language can be a browser tag ("en-US"); the options are product codes.
  const currentLanguage = normaliseLanguage(i18n.language) || 'en';

  const handleLanguageChange = async (languageCode) => {
    if (user) {
      try {
        // Saved BEFORE switching. Switching remounts the app, which reloads the
        // profile — and a profile read before this save lands still holds the
        // old language, which AuthContext would adopt and switch straight back.
        // The same PATCH the Profile screen saves with, through the shared client.
        await api.patch('/users/me', { preferred_language: languageCode });
      } catch (error) {
        console.error('Failed to update language preference:', error);
      }
    }
    i18n.changeLanguage(languageCode);
  };

  if (variant === 'dropdown') {
    return (
      <div className="language-switcher">
        <select
          value={currentLanguage}
          onChange={(e) => handleLanguageChange(e.target.value)}
          className="language-select"
          aria-label={t('LanguageSwitcher.language')}
        >
          {SUPPORTED_LANGUAGES.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.nativeName}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (variant === 'grid') {
    return (
      <div className="language-grid">
        {SUPPORTED_LANGUAGES.map((lang) => (
          <button
            key={lang.code}
            onClick={() => handleLanguageChange(lang.code)}
            className={`language-button ${currentLanguage === lang.code ? 'active' : ''}`}
          >
            <span className="native-name">{lang.nativeName}</span>
            <span className="english-name">{lang.name}</span>
          </button>
        ))}
      </div>
    );
  }

  return null;
};

export default LanguageSwitcher;
