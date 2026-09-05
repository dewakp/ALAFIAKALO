"""
Internationalization (i18n) Service
Multi-language support for global audience
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import Optional, Dict, List

from app.models.privacy import Translation


class I18nService:
    """Service for managing translations and multi-language content"""
    
    # Supported languages (ISO 639-1 codes)
    SUPPORTED_LANGUAGES = [
        "en",  # English
        "es",  # Spanish
        "fr",  # French
        "de",  # German
        "pt",  # Portuguese
        "ar",  # Arabic
        "zh",  # Chinese (Simplified)
        "hi",  # Hindi
        "ru",  # Russian
        "ja",  # Japanese
        "ko",  # Korean
        "it",  # Italian
        "nl",  # Dutch
        "pl",  # Polish
        "tr",  # Turkish
        "vi",  # Vietnamese
        "sw",  # Swahili
        "yo",  # Yoruba
        "ig",  # Igbo
        "ha",  # Hausa
    ]
    
    # Right-to-left languages
    RTL_LANGUAGES = ["ar", "he", "fa", "ur"]
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_translation(
        self,
        key: str,
        language_code: str = "en",
        fallback_to_english: bool = True,
        platform: Optional[str] = None,
    ) -> str:
        """
        Get translation for a key
        
        Args:
            key: Translation key (e.g., "dashboard.welcome")
            language_code: Language code (ISO 639-1)
            fallback_to_english: If True, return English if translation not found
            platform: Optional platform filter (web, ios, android)
            
        Returns:
            Translated string
        """
        # Validate language
        if language_code not in self.SUPPORTED_LANGUAGES:
            language_code = "en"
        
        # Try to get translation for requested language
        query = self.db.query(Translation).filter(
            and_(
                Translation.key == key,
                Translation.language_code == language_code,
                Translation.is_active == True
            )
        )
        
        if platform:
            query = query.filter(
                or_(Translation.platform == platform, Translation.platform == "all")
            )
        
        translation = query.first()
        
        if translation:
            return translation.value
        
        # Fallback to English
        if fallback_to_english and language_code != "en":
            english_query = self.db.query(Translation).filter(
                and_(
                    Translation.key == key,
                    Translation.language_code == "en",
                    Translation.is_active == True
                )
            )
            
            if platform:
                english_query = english_query.filter(
                    or_(Translation.platform == platform, Translation.platform == "all")
                )
            
            english_translation = english_query.first()
            
            if english_translation:
                return english_translation.value
        
        # Return key if no translation found
        return key
    
    def get_translations_bulk(
        self,
        keys: List[str],
        language_code: str = "en",
        platform: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Get multiple translations at once (more efficient)
        
        Returns:
            Dictionary mapping keys to translated values
        """
        if language_code not in self.SUPPORTED_LANGUAGES:
            language_code = "en"
        
        query = self.db.query(Translation).filter(
            and_(
                Translation.key.in_(keys),
                Translation.language_code == language_code,
                Translation.is_active == True
            )
        )
        
        if platform:
            query = query.filter(
                or_(Translation.platform == platform, Translation.platform == "all")
            )
        
        translations = query.all()
        
        result = {t.key: t.value for t in translations}
        
        # Fill in missing keys with key itself
        for key in keys:
            if key not in result:
                result[key] = key
        
        return result
    
    def get_all_translations_for_language(
        self,
        language_code: str = "en",
        category: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Get all translations for a language
        Useful for loading entire language pack for mobile apps
        
        Returns:
            Dictionary of all translations for the language
        """
        if language_code not in self.SUPPORTED_LANGUAGES:
            language_code = "en"
        
        query = self.db.query(Translation).filter(
            and_(
                Translation.language_code == language_code,
                Translation.is_active == True
            )
        )
        
        if category:
            query = query.filter(Translation.category == category)
        
        if platform:
            query = query.filter(
                or_(Translation.platform == platform, Translation.platform == "all")
            )
        
        translations = query.all()
        
        return {t.key: t.value for t in translations}
    
    def add_translation(
        self,
        key: str,
        language_code: str,
        value: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        platform: str = "all",
        is_machine_translated: bool = False,
    ) -> Translation:
        """
        Add or update a translation
        
        Args:
            key: Translation key
            language_code: Language code
            value: Translated text
            description: Context for translators
            category: Category (ui, email, notification, etc.)
            platform: Target platform (web, ios, android, all)
            is_machine_translated: Whether this was auto-translated
            
        Returns:
            Translation object
        """
        # Check if translation already exists
        existing = self.db.query(Translation).filter(
            and_(
                Translation.key == key,
                Translation.language_code == language_code,
                Translation.platform == platform
            )
        ).first()
        
        if existing:
            # Update existing
            existing.value = value
            existing.description = description
            existing.category = category
            existing.is_machine_translated = is_machine_translated
            existing.is_active = True
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            # Create new
            translation = Translation(
                key=key,
                language_code=language_code,
                value=value,
                description=description,
                category=category,
                platform=platform,
                is_machine_translated=is_machine_translated,
                is_active=True,
            )
            self.db.add(translation)
            self.db.commit()
            self.db.refresh(translation)
            return translation
    
    def add_translations_bulk(
        self,
        translations: List[Dict[str, str]],
    ) -> int:
        """
        Add multiple translations at once
        
        Args:
            translations: List of translation dicts with keys:
                - key: Translation key
                - language_code: Language
                - value: Translated text
                - (optional) description, category, platform
        
        Returns:
            Number of translations added/updated
        """
        count = 0
        for trans_data in translations:
            self.add_translation(**trans_data)
            count += 1
        
        return count
    
    def is_rtl_language(self, language_code: str) -> bool:
        """Check if language is right-to-left"""
        return language_code in self.RTL_LANGUAGES
    
    def get_language_name(self, language_code: str, in_language: str = "en") -> str:
        """
        Get language name in specified language
        
        Args:
            language_code: Language to get name for
            in_language: Language to return name in
            
        Returns:
            Language name (e.g., "Spanish", "Español")
        """
        # This would typically come from database, but using dict for simplicity
        language_names = {
            "en": {"en": "English", "es": "Inglés", "fr": "Anglais", "de": "Englisch"},
            "es": {"en": "Spanish", "es": "Español", "fr": "Espagnol", "de": "Spanisch"},
            "fr": {"en": "French", "es": "Francés", "fr": "Français", "de": "Französisch"},
            "de": {"en": "German", "es": "Alemán", "fr": "Allemand", "de": "Deutsch"},
            "pt": {"en": "Portuguese", "es": "Portugués", "fr": "Portugais", "de": "Portugiesisch"},
            "ar": {"en": "Arabic", "es": "Árabe", "fr": "Arabe", "de": "Arabisch"},
            "zh": {"en": "Chinese", "es": "Chino", "fr": "Chinois", "de": "Chinesisch"},
            "hi": {"en": "Hindi", "es": "Hindi", "fr": "Hindi", "de": "Hindi"},
            "ru": {"en": "Russian", "es": "Ruso", "fr": "Russe", "de": "Russisch"},
            "ja": {"en": "Japanese", "es": "Japonés", "fr": "Japonais", "de": "Japanisch"},
            "ko": {"en": "Korean", "es": "Coreano", "fr": "Coréen", "de": "Koreanisch"},
            "it": {"en": "Italian", "es": "Italiano", "fr": "Italien", "de": "Italienisch"},
            "yo": {"en": "Yoruba", "es": "Yoruba", "fr": "Yoruba", "de": "Yoruba"},
            "ig": {"en": "Igbo", "es": "Igbo", "fr": "Igbo", "de": "Igbo"},
            "ha": {"en": "Hausa", "es": "Hausa", "fr": "Hausa", "de": "Hausa"},
            "sw": {"en": "Swahili", "es": "Swahili", "fr": "Swahili", "de": "Swahili"},
        }
        
        if language_code in language_names and in_language in language_names[language_code]:
            return language_names[language_code][in_language]
        
        return language_code
    
    def detect_language_from_accept_header(self, accept_language: Optional[str]) -> str:
        """
        Parse Accept-Language header to determine preferred language
        
        Args:
            accept_language: Accept-Language header value
            
        Returns:
            Best matching supported language code
        """
        if not accept_language:
            return "en"
        
        # Parse Accept-Language header (e.g., "en-US,en;q=0.9,es;q=0.8")
        languages = []
        for lang_range in accept_language.split(","):
            parts = lang_range.strip().split(";")
            lang = parts[0].split("-")[0].lower()  # Get just language code
            
            # Parse quality value
            quality = 1.0
            if len(parts) > 1 and parts[1].startswith("q="):
                try:
                    quality = float(parts[1][2:])
                except ValueError:
                    quality = 1.0
            
            languages.append((lang, quality))
        
        # Sort by quality (highest first)
        languages.sort(key=lambda x: x[1], reverse=True)
        
        # Find first supported language
        for lang, _ in languages:
            if lang in self.SUPPORTED_LANGUAGES:
                return lang
        
        # Default to English
        return "en"
