// Copyright © 2026 Wole Akpose / 6igma Health Inc.
// All rights reserved. ALAFIA — proprietary and confidential.

package com.lafiakalo.android

import com.alafia.android.views.nutrition.visionMeal
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * A photo correction must reach the meal that is logged.
 *
 * The meal that exposed this was corrected to 100/60/80/20 g and saved as
 * names only, so the backend re-parsed "3 Pieces of Sardines" as 300 g.
 * Same cases as web `visionMeal.test.js`.
 */
class VisionMealTest {
    private val rows = listOf(
        Triple("3 Pieces of Sardines", "100", ""),
        Triple("2 Brioche Bread Slices", "60", ""),
        Triple("2 Boiled eggs", "80", ""),
        Triple("Onion slices (raw)", "20", ""),
    )

    @Test fun carriesEachCorrectedWeightInFrontOfItsFood() {
        assertEquals(
            "100 g 3 Pieces of Sardines, 60 g 2 Brioche Bread Slices, 80 g 2 Boiled eggs, 20 g Onion slices (raw)",
            visionMeal(rows).first)
    }

    @Test fun servingSizeIsTheWholeMealNotTheFirstItem() {
        assertEquals("composite meal (260 g total)", visionMeal(rows).second)
    }

    @Test fun unknownWeightLeavesTheTotalBlankRatherThanUndercounting() {
        val r = visionMeal(rows.take(3) + Triple("Onion", "", ""))
        assertEquals("", r.second)
        assertEquals(true, r.first.endsWith(", Onion"))
    }

    @Test fun dropsEmptyRowsAndReadsADecimalComma() {
        assertEquals("150.3 g Rice" to "150.3 g",
            visionMeal(listOf(Triple(" Rice ", "150,25", ""), Triple("", "5", ""))))
    }
}
