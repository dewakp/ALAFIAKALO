import React from 'react';
import { useTranslation } from 'react-i18next';
import { SUPPORTED_LANGUAGES } from '../i18n';
import api from '../services/api';

/**
 * Language Switcher Component
 * 
 * Allows users to change the application language
 * Supports 20+ languages including African languages
 */
const LanguageSwitcher = ({ variant = 'dropdown' }) => {
  const { i18n } = useTranslation();
  const currentLanguage = i18n.language;

  const handleLanguageChange = (languageCode) => {
    i18n.changeLanguage(languageCode);
    // Save preference to localStorage (automatic with i18next config)
    // Update user profile on backend (optional)
    updateUserLanguagePreference(languageCode);
  };

  const updateUserLanguagePreference = async (languageCode) => {
    try {
      // The same PATCH the Profile screen saves with, through the shared client
      // so auth, CSRF and the base URL are handled once. This used to PUT to
      // `${VITE_API_URL}/api/v1/users/me` by hand, bypassing all three.
      await api.patch('/users/me', { preferred_language: languageCode });
    } catch (error) {
      console.error('Failed to update language preference:', error);
    }
  };

  if (variant === 'dropdown') {
    return (
      <div className="language-switcher">
        <select
          value={currentLanguage}
          onChange={(e) => handleLanguageChange(e.target.value)}
          className="language-select"
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
