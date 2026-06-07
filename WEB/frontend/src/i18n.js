/**
 * i18n Configuration for ALAFIA
 * 
 * Multi-language support using i18next
 * 
 * Installation required:
 * npm install i18next react-i18next i18next-browser-languagedetector
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// Import translations
import enTranslations from './locales/en.json';
import esTranslations from './locales/es.json';
import frTranslations from './locales/fr.json';
import deTranslations from './locales/de.json';
import ptTranslations from './locales/pt.json';
import arTranslations from './locales/ar.json';
import zhTranslations from './locales/zh.json';
import yoTranslations from './locales/yo.json';
import igTranslations from './locales/ig.json';
import haTranslations from './locales/ha.json';
import swTranslations from './locales/sw.json';

// Supported languages
export const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'es', name: 'Spanish', nativeName: 'Español' },
  { code: 'fr', name: 'French', nativeName: 'Français' },
  { code: 'de', name: 'German', nativeName: 'Deutsch' },
  { code: 'pt', name: 'Portuguese', nativeName: 'Português' },
  { code: 'ar', name: 'Arabic', nativeName: 'العربية', dir: 'rtl' },
  { code: 'zh', name: 'Chinese', nativeName: '中文' },
  { code: 'yo', name: 'Yoruba', nativeName: 'Yorùbá' },
  { code: 'ig', name: 'Igbo', nativeName: 'Igbo' },
  { code: 'ha', name: 'Hausa', nativeName: 'Hausa' },
  { code: 'sw', name: 'Swahili', nativeName: 'Kiswahili' },
];

// RTL languages
export const RTL_LANGUAGES = ['ar', 'he', 'fa', 'ur'];

// Initialize i18next
i18n
  .use(LanguageDetector) // Auto-detect user language
  .use(initReactI18next) // Bind to React
  .init({
    resources: {
      en: { translation: enTranslations },
      es: { translation: esTranslations },
      fr: { translation: frTranslations },
      de: { translation: deTranslations },
      pt: { translation: ptTranslations },
      ar: { translation: arTranslations },
      zh: { translation: zhTranslations },
      yo: { translation: yoTranslations },
      ig: { translation: igTranslations },
      ha: { translation: haTranslations },
      sw: { translation: swTranslations },
    },
    
    fallbackLng: 'en', // Fallback to English if translation not found
    
    // Language detection options
    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      caches: ['localStorage'], // Cache user's language preference
      lookupLocalStorage: 'language',
    },
    
    interpolation: {
      escapeValue: false, // React already escapes values
    },
    
    // Namespacing (optional, for organizing translations)
    defaultNS: 'translation',
    
    // Performance
    load: 'languageOnly', // Load only 'en' not 'en-US'
    
    // Backend integration (optional - load translations from API)
    backend: {
      loadPath: '/api/v1/privacy/translations/{{lng}}',
      allowMultiLoading: false,
      crossDomain: true,
    },
  });

// Helper function to check if language is RTL
export const isRTL = (languageCode) => {
  return RTL_LANGUAGES.includes(languageCode);
};

// Helper function to set document direction based on language
export const setDocumentDirection = (languageCode) => {
  document.documentElement.dir = isRTL(languageCode) ? 'rtl' : 'ltr';
  document.documentElement.lang = languageCode;
};

// Watch for language changes and update document direction
i18n.on('languageChanged', (lng) => {
  setDocumentDirection(lng);
});

// Set initial direction
setDocumentDirection(i18n.language);

export default i18n;
