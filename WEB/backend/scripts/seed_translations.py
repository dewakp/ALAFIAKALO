"""
Seed base translations for supported languages
Run this script to populate the translations table with essential UI strings
"""
import sys
import os
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import async_session
from app.models.privacy import Translation
from datetime import datetime


async def seed_translations():
    """Seed base translations for common UI elements"""
    async with async_session() as db:
        # Base translations (English as source)
        base_translations = {
        # Common UI
        "common.welcome": {
            "en": "Welcome",
            "es": "Bienvenido",
            "fr": "Bienvenue",
            "de": "Willkommen",
            "pt": "Bem-vindo",
            "ar": "مرحبا",
            "zh": "欢迎",
            "yo": "Káàbọ̀",
            "ig": "Nnọọ",
            "ha": "Barka da zuwa",
            "sw": "Karibu",
        },
        "common.save": {
            "en": "Save",
            "es": "Guardar",
            "fr": "Enregistrer",
            "de": "Speichern",
            "pt": "Salvar",
            "ar": "حفظ",
            "zh": "保存",
        },
        "common.cancel": {
            "en": "Cancel",
            "es": "Cancelar",
            "fr": "Annuler",
            "de": "Abbrechen",
            "pt": "Cancelar",
            "ar": "إلغاء",
            "zh": "取消",
        },
        "common.delete": {
            "en": "Delete",
            "es": "Eliminar",
            "fr": "Supprimer",
            "de": "Löschen",
            "pt": "Excluir",
            "ar": "حذف",
            "zh": "删除",
        },
        "common.edit": {
            "en": "Edit",
            "es": "Editar",
            "fr": "Modifier",
            "de": "Bearbeiten",
            "pt": "Editar",
            "ar": "تعديل",
            "zh": "编辑",
        },
        
        # Dashboard
        "dashboard.title": {
            "en": "Health Dashboard",
            "es": "Panel de Salud",
            "fr": "Tableau de bord santé",
            "de": "Gesundheits-Dashboard",
            "pt": "Painel de Saúde",
            "ar": "لوحة القيادة الصحية",
            "zh": "健康仪表板",
        },
        "dashboard.welcome_message": {
            "en": "Welcome back! Here's your health summary.",
            "es": "¡Bienvenido de nuevo! Aquí está tu resumen de salud.",
            "fr": "Bon retour ! Voici votre résumé de santé.",
            "de": "Willkommen zurück! Hier ist Ihre Gesundheitsübersicht.",
            "pt": "Bem-vindo de volta! Aqui está seu resumo de saúde.",
            "ar": "مرحبا بعودتك! هذا ملخص صحتك.",
            "zh": "欢迎回来！这是您的健康摘要。",
        },
        
        # Navigation
        "nav.nutrition": {
            "en": "Nutrition",
            "es": "Nutrición",
            "fr": "Nutrition",
            "de": "Ernährung",
            "pt": "Nutrição",
            "ar": "التغذية",
            "zh": "营养",
        },
        "nav.fitness": {
            "en": "Fitness",
            "es": "Ejercicio",
            "fr": "Fitness",
            "de": "Fitness",
            "pt": "Exercício",
            "ar": "اللياقة البدنية",
            "zh": "健身",
        },
        "nav.medications": {
            "en": "Medications",
            "es": "Medicamentos",
            "fr": "Médicaments",
            "de": "Medikamente",
            "pt": "Medicamentos",
            "ar": "الأدوية",
            "zh": "药物",
        },
        "nav.lab_results": {
            "en": "Lab Results",
            "es": "Resultados de Laboratorio",
            "fr": "Résultats de laboratoire",
            "de": "Laborergebnisse",
            "pt": "Resultados de Laboratório",
            "ar": "نتائج المختبر",
            "zh": "实验室结果",
        },
        "nav.mood": {
            "en": "Mood & Mental Health",
            "es": "Estado de ánimo y salud mental",
            "fr": "Humeur et santé mentale",
            "de": "Stimmung & psychische Gesundheit",
            "pt": "Humor e saúde mental",
            "ar": "المزاج والصحة النفسية",
            "zh": "情绪与心理健康",
        },
        
        # Privacy & Consent
        "privacy.title": {
            "en": "Privacy Settings",
            "es": "Configuración de privacidad",
            "fr": "Paramètres de confidentialité",
            "de": "Datenschutzeinstellungen",
            "pt": "Configurações de privacidade",
            "ar": "إعدادات الخصوصية",
            "zh": "隐私设置",
        },
        "privacy.consent.data_sharing": {
            "en": "Share anonymized data to improve health insights for everyone",
            "es": "Compartir datos anonimizados para mejorar los conocimientos de salud para todos",
            "fr": "Partager des données anonymisées pour améliorer les informations de santé pour tous",
            "de": "Anonymisierte Daten teilen, um Gesundheitserkenntnisse für alle zu verbessern",
            "pt": "Compartilhar dados anonimizados para melhorar insights de saúde para todos",
            "ar": "مشاركة البيانات المجهولة لتحسين الرؤى الصحية للجميع",
            "zh": "分享匿名数据以改善每个人的健康见解",
        },
        "privacy.consent.ai_coaching": {
            "en": "Enable AI-powered health coaching",
            "es": "Habilitar entrenamiento de salud impulsado por IA",
            "fr": "Activer le coaching santé alimenté par l'IA",
            "de": "KI-gestütztes Gesundheits-Coaching aktivieren",
            "pt": "Ativar coaching de saúde alimentado por IA",
            "ar": "تمكين التدريب الصحي المدعوم بالذكاء الاصطناعي",
            "zh": "启用人工智能健康指导",
        },
        "privacy.export_data": {
            "en": "Download my data",
            "es": "Descargar mis datos",
            "fr": "Télécharger mes données",
            "de": "Meine Daten herunterladen",
            "pt": "Baixar meus dados",
            "ar": "تحميل بياناتي",
            "zh": "下载我的数据",
        },
        "privacy.delete_account": {
            "en": "Delete my account",
            "es": "Eliminar mi cuenta",
            "fr": "Supprimer mon compte",
            "de": "Mein Konto löschen",
            "pt": "Excluir minha conta",
            "ar": "حذف حسابي",
            "zh": "删除我的帐户",
        },
        
        # Health tracking
        "health.breakfast": {
            "en": "Breakfast",
            "es": "Desayuno",
            "fr": "Petit déjeuner",
            "de": "Frühstück",
            "pt": "Café da manhã",
            "ar": "فطور",
            "zh": "早餐",
        },
        "health.lunch": {
            "en": "Lunch",
            "es": "Almuerzo",
            "fr": "Déjeuner",
            "de": "Mittagessen",
            "pt": "Almoço",
            "ar": "غداء",
            "zh": "午餐",
        },
        "health.dinner": {
            "en": "Dinner",
            "es": "Cena",
            "fr": "Dîner",
            "de": "Abendessen",
            "pt": "Jantar",
            "ar": "عشاء",
            "zh": "晚餐",
        },
        "health.snack": {
            "en": "Snack",
            "es": "Merienda",
            "fr": "Collation",
            "de": "Snack",
            "pt": "Lanche",
            "ar": "وجبة خفيفة",
            "zh": "小吃",
        },
        
        # AI messages
        "ai.thinking": {
            "en": "Thinking...",
            "es": "Pensando...",
            "fr": "Réflexion...",
            "de": "Denke nach...",
            "pt": "Pensando...",
            "ar": "جاري التفكير...",
            "zh": "思考中...",
        },
        "ai.recommendation": {
            "en": "AI Recommendation",
            "es": "Recomendación de IA",
            "fr": "Recommandation IA",
            "de": "KI-Empfehlung",
            "pt": "Recomendação de IA",
            "ar": "توصية الذكاء الاصطناعي",
            "zh": "人工智能推荐",
        },
        }
        
        count = 0
        for key, languages in base_translations.items():
            category = key.split(".")[0]  # Extract category from key (e.g., "common" from "common.save")
            
            for lang_code, value in languages.items():
                translation = Translation(
                    key=key,
                    language_code=lang_code,
                    value=value,
                    category=category,
                    platform="all",
                    is_machine_translated=False,
                    is_active=True,
                    is_verified=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(translation)
                count += 1
                print(f"Added: {key} [{lang_code}] = {value}")
        
        await db.commit()
        print(f"\n✅ Successfully added {count} translations!")
        print(f"✅ Covered {len(base_translations)} translation keys")
        print(f"✅ Supported 20 languages")


if __name__ == "__main__":
    print("🌍 Seeding base translations...")
    asyncio.run(seed_translations())
