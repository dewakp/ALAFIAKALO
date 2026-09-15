package com.alafia.android

import android.content.Context
import java.util.Locale

/**
 * The languages ALAFIA offers — the same eleven codes on web, iOS, Android and
 * the backend (`WEB/backend/app/services/prompt_language.py`).
 */
object AppLanguage {
    val CODES = listOf("en", "es", "fr", "de", "pt", "ar", "zh", "yo", "ig", "ha", "sw")

    val NATIVE_NAMES = mapOf(
        "en" to "English", "es" to "Español", "fr" to "Français", "de" to "Deutsch",
        "pt" to "Português", "ar" to "العربية", "zh" to "中文", "yo" to "Yorùbá",
        "ig" to "Igbo", "ha" to "Hausa", "sw" to "Kiswahili",
    )

    private const val PREFS = "alafia_prefs"
    private const val KEY = "app_language"

    /**
     * The language this app is in: the patient's choice, else the device's
     * language when ALAFIA offers it, else English.
     *
     * Sent on every request as `X-Client-Language`, and the backend puts it
     * FIRST. So the saved profile preference must become the choice here when
     * the profile loads — sending the device language instead would answer a
     * patient who chose Yoruba in English on an English-language phone.
     */
    fun current(context: Context): String {
        val chosen = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, null)
        if (chosen != null && chosen in CODES) return chosen
        val device = normalise(Locale.getDefault().toLanguageTag())
        return device.ifEmpty { "en" }
    }

    /**
     * Remember the patient's choice. An empty or unknown value is ignored, never
     * guessed at: a blank profile field does not erase a choice.
     */
    fun choose(context: Context, value: String?): Boolean {
        val code = normalise(value)
        if (code.isEmpty()) return false
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (prefs.getString(KEY, null) == code) return false
        prefs.edit().putString(KEY, code).apply()
        return true
    }

    /**
     * A context whose resources — strings, and layout direction for Arabic —
     * follow the patient's language.
     *
     * Deliberately NOT `Locale.setDefault`: that changes number formatting for
     * the whole process, and a French patient's `String.format("%.1f", 1.5)`
     * would reach the backend as "1,5". Only resources follow the choice.
     */
    fun wrap(base: Context): Context {
        val locale = Locale.forLanguageTag(current(base))
        val config = android.content.res.Configuration(base.resources.configuration)
        config.setLocale(locale)
        config.setLayoutDirection(locale)
        return base.createConfigurationContext(config)
    }

    /**
     * A product code for any stored form — "fr", "fr-FR", "French", "Français" —
     * or "" when it is none of them. Profiles hold both codes and names.
     */
    fun normalise(value: String?): String {
        val raw = value?.trim().orEmpty()
        if (raw.isEmpty()) return ""
        val prefix = raw.substringBefore('-').substringBefore('_').lowercase()
        if (prefix in CODES) return prefix
        return CODES.firstOrNull { code ->
            raw.equals(Locale.forLanguageTag(code).getDisplayLanguage(Locale.ENGLISH), ignoreCase = true) ||
                raw.equals(NATIVE_NAMES[code], ignoreCase = true)
        }.orEmpty()
    }

    fun displayName(code: String): String =
        if (code.isEmpty()) "—" else NATIVE_NAMES[code] ?: code.uppercase()
}
