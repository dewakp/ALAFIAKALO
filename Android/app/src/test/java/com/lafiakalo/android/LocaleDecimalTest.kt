// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.lafiakalo.android

import com.alafia.android.LocaleDecimal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * A dose typed as `0,5` must not be recorded as `0.0`.
 *
 * `"0,5".toDoubleOrNull()` is null — measured, not assumed — and the
 * medication screen read it as `amount.toDoubleOrNull() ?: 0.0`. So a patient
 * in France, Germany, Spain, Portugal or Egypt typing a half-tablet dose
 * recorded **zero milligrams**, silently, on the field §3aj calls the most
 * dangerous in the product. Weights, temperatures and sleep hours went to null
 * and were dropped with no message at all.
 *
 * Five of ALAFIA's eleven languages use a non-dot decimal separator
 * (fr, de, es, pt use `,`; ar uses `٫` U+066B), and the keyboard follows the
 * DEVICE locale regardless of the in-app language choice.
 */
class LocaleDecimalTest {

    // ── The bug itself ────────────────────────────────────────────────

    @Test
    fun `a comma decimal is the number the patient meant`() {
        assertEquals(0.5, LocaleDecimal.parse("0,5")!!, 1e-9)
        assertEquals(72.5, LocaleDecimal.parse("72,5")!!, 1e-9)
        assertEquals(37.2, LocaleDecimal.parse("37,2")!!, 1e-9)
    }

    @Test
    fun `the dose that used to become zero`() {
        // The exact production expression, before and after.
        assertEquals(0.0, "0,5".toDoubleOrNull() ?: 0.0, 1e-9)          // what it did
        assertEquals(0.5, LocaleDecimal.parse("0,5") ?: 0.0, 1e-9)      // what it does
    }

    @Test
    fun `an Arabic keyboard's separator and digits both parse`() {
        // U+066B is the Arabic decimal separator; ٠-٩ are Arabic-Indic digits.
        assertEquals(0.5, LocaleDecimal.parse("0٫5")!!, 1e-9)
        assertEquals(123.5, LocaleDecimal.parse("١٢٣٫٥")!!, 1e-9)
    }

    // ── Still correct for everyone it already worked for ──────────────

    @Test
    fun `a dot decimal is unchanged`() {
        assertEquals(0.5, LocaleDecimal.parse("0.5")!!, 1e-9)
        assertEquals(1000.0, LocaleDecimal.parse("1000")!!, 1e-9)
        assertEquals(0.5, LocaleDecimal.parse("  0.5  ")!!, 1e-9)
        assertEquals(-1.5, LocaleDecimal.parse("-1.5")!!, 1e-9)
    }

    // ── Grouping, which is a different thing from a decimal point ─────

    @Test
    fun `a lone comma is a DECIMAL separator, because the keyboard has no grouping key`() {
        // KeyboardType.Decimal offers digits and the locale separator only —
        // the patient cannot type a thousands separator, so 1,234 is 1.234.
        assertEquals(1.234, LocaleDecimal.parse("1,234")!!, 1e-9)
    }

    @Test
    fun `repeated separators are grouping`() {
        assertEquals(1234567.0, LocaleDecimal.parse("1.234.567")!!, 1e-9)
        assertEquals(1234567.0, LocaleDecimal.parse("1,234,567")!!, 1e-9)
    }

    @Test
    fun `both separators present means the last one is the decimal point`() {
        assertEquals(1234.56, LocaleDecimal.parse("1.234,56")!!, 1e-9)   // de
        assertEquals(1234.56, LocaleDecimal.parse("1,234.56")!!, 1e-9)   // en
    }

    @Test
    fun `a French grouping space is not part of the number`() {
        assertEquals(1234.5, LocaleDecimal.parse("1 234,5")!!, 1e-9)
        assertEquals(1234.5, LocaleDecimal.parse("1 234,5")!!, 1e-9)
    }

    // ── Refusals: a wrong number is worse than no number (§3aj) ───────

    @Test
    fun `nonsense is refused rather than half-parsed`() {
        assertNull(LocaleDecimal.parse("1.2.3"))   // not groups of three
        assertNull(LocaleDecimal.parse("abc"))
        assertNull(LocaleDecimal.parse("12kg"))    // parseFloat-style truncation refused
        assertNull(LocaleDecimal.parse(""))
        assertNull(LocaleDecimal.parse("   "))
        assertNull(LocaleDecimal.parse(null))
        assertNull(LocaleDecimal.parse("."))
        assertNull(LocaleDecimal.parse(","))
    }

    @Test
    fun `the float flavour agrees with the double one`() {
        assertEquals(0.5f, LocaleDecimal.parseFloat("0,5")!!, 1e-6f)
        assertNull(LocaleDecimal.parseFloat("abc"))
    }

    // ── The normalisation itself, so a separator bug and a parse ──────
    // ── failure cannot be mistaken for one another ────────────────────

    @Test
    fun `normalisation is pinned separately from parsing`() {
        assertEquals("0.5", LocaleDecimal.normalise("0,5"))
        assertEquals("1234.56", LocaleDecimal.normalise("1.234,56"))
        assertEquals("1234567", LocaleDecimal.normalise("1,234,567"))
        assertNull(LocaleDecimal.normalise("1.2.3"))
    }
}
