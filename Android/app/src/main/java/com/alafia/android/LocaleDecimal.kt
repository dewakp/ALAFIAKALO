// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.alafia.android

/**
 * A number the patient TYPED, in whatever decimal separator their keyboard gave
 * them.
 *
 * `"0,5".toDoubleOrNull()` is **null** — Kotlin delegates to
 * `Double.parseDouble`, which is locale-independent and accepts only a dot.
 * Measured, not assumed, along with the separator each of our languages uses:
 *
 *     "0.5"  -> 0.5          fr [,]   de [,]   es [,]
 *     "0,5"  -> null         pt [,]   ar [٫]
 *     "72,5" -> null         sw [.]   en [.]
 *
 * Five of ALAFIA's eleven languages use a non-dot separator, and the keyboard
 * follows the DEVICE locale — so it applies however the patient set the in-app
 * language. The damage was silent and worst on the most dangerous field in the
 * product:
 *
 *     dose_amount = amount.toDoubleOrNull() ?: 0.0
 *
 * A patient in France, Germany, Spain, Portugal or Egypt typing a half-tablet
 * dose as `0,5` recorded **0.0 mg**. Weights, temperatures and sleep hours
 * went to null and were dropped without a word. §3aj exists because a wrong
 * dose in a clinical record is the error that replays.
 *
 * **A lone comma is a decimal separator, not grouping.** These fields are
 * `KeyboardType.Decimal`, which offers no grouping key at all — the patient
 * *cannot* type a thousands separator — so `1,234` is 1.234. Refusing it as
 * "ambiguous" would reject the only thing that keyboard can produce. Repeated
 * separators (`1.234.567`) ARE grouping and are read that way, but only when
 * every group after the first is exactly three digits; `1.2.3` is nonsense and
 * is refused rather than quietly becoming 123.
 *
 * Deliberately NOT `NumberFormat.getInstance()`: that parses against the
 * process locale, and §3aw records that ALAFIA sets its language through
 * `attachBaseContext` rather than `Locale.setDefault` precisely so the process
 * locale is NOT the app's. A patient with an English phone who chose French
 * would then get a parser disagreeing with their keyboard. This reads what was
 * typed instead of guessing where they are.
 */
object LocaleDecimal {

    /** The typed text as a number, or null when it is not one. */
    fun parse(raw: String?): Double? = normalise(raw)?.toDoubleOrNull()

    /** Float flavour, for the call sites whose model field is a Float. */
    fun parseFloat(raw: String?): Float? = parse(raw)?.toFloat()

    /**
     * Typed text -> a string `Double.parseDouble` accepts, or null.
     *
     * Internal so the tests can pin the normalisation itself rather than only
     * the parsed result — a wrong separator decision and a parse failure are
     * different bugs and should not be indistinguishable.
     */
    internal fun normalise(raw: String?): String? {
        val trimmed = raw?.trim().orEmpty()
        if (trimmed.isEmpty()) return null

        // Arabic-Indic digits and the Arabic separators come from an Arabic
        // keyboard; the spaces are French grouping (U+00A0 / U+202F / U+2009).
        val sb = StringBuilder(trimmed.length)
        for (ch in trimmed) {
            when (ch) {
                in '٠'..'٩' -> sb.append('0' + (ch - '٠'))
                in '۰'..'۹' -> sb.append('0' + (ch - '۰'))
                '٫' -> sb.append('.')            // Arabic decimal separator
                '٬' -> sb.append(',')            // Arabic thousands separator
                ' ', ' ', ' ', ' ' -> Unit
                else -> sb.append(ch)
            }
        }

        var s = sb.toString()
        var sign = ""
        if (s.startsWith("-") || s.startsWith("+")) {
            if (s[0] == '-') sign = "-"
            s = s.substring(1)
        }
        if (s.isEmpty()) return null
        // Anything that is not a digit or a separator is not a number. This is
        // what keeps "12kg" and "abc" out rather than letting them half-parse.
        if (s.any { !it.isDigit() && it != '.' && it != ',' }) return null

        val dots = s.count { it == '.' }
        val commas = s.count { it == ',' }

        val body: String = when {
            dots == 0 && commas == 0 -> s

            // Both kinds present: the LAST one is the decimal separator and
            // everything before it is grouping — true of "1.234,56" (de) and
            // "1,234.56" (en) alike.
            dots > 0 && commas > 0 -> {
                val decimalAt = maxOf(s.lastIndexOf('.'), s.lastIndexOf(','))
                val whole = s.substring(0, decimalAt).replace(".", "").replace(",", "")
                val fraction = s.substring(decimalAt + 1)
                if (whole.isEmpty() || fraction.isEmpty()) return null
                "$whole.$fraction"
            }

            // Exactly one separator: the decimal point, whichever glyph it is.
            dots == 1 || commas == 1 -> s.replace(',', '.')

            // Repeated separators of one kind are grouping, and only if every
            // group after the first is three digits. "1.2.3" is not a number.
            else -> {
                val separator = if (dots > 1) '.' else ','
                val parts = s.split(separator)
                if (parts[0].isEmpty() || parts.drop(1).any { it.length != 3 }) return null
                if (parts.any { part -> part.any { !it.isDigit() } }) return null
                parts.joinToString("")
            }
        }

        if (body.isEmpty() || body == ".") return null
        return sign + body
    }
}
