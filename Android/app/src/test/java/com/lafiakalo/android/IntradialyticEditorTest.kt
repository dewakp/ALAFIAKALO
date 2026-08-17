package com.alafia.android

import com.alafia.android.models.IntradialyticReading
import com.alafia.android.views.hd.EditableReading
import com.google.gson.Gson
import org.junit.Assert.*
import org.junit.Test

/**
 * The intradialytic grid's save semantics, which is where this feature has gone
 * wrong before on other clients. Each test below pins a specific past failure.
 */
class IntradialyticEditorTest {

    private val gson = Gson()

    // ── reading_time is normalised, not merely validated ──────────────────

    @Test
    fun `a trailing space does not survive into the payload`() {
        // Web tested `regex.test(t.trim())` and then posted the UNTRIMMED value,
        // so "14:30 " passed the guard and the API rejected the save with
        // "invalid time format, invalid timezone sign" on a completed flowsheet.
        val row = EditableReading(readingTime = "14:30 ")
        assertEquals("14:30", row.normalisedTime)
        assertEquals("14:30", row.payload(1)["reading_time"])
    }

    @Test
    fun `single digit hours are zero padded`() {
        assertEquals("09:05", EditableReading(readingTime = "9:5").normalisedTime)
    }

    @Test
    fun `an unparseable time is rejected rather than guessed at`() {
        listOf("25:00", "12:75", "abc", "12", ":", "").forEach {
            assertNull("expected null for '$it'", EditableReading(readingTime = it).normalisedTime)
        }
    }

    // ── a blank time stays blank ──────────────────────────────────────────

    @Test
    fun `a blank time is omitted, never sent as midnight`() {
        // Defaulting this to 00:00 is how 3664 rows (22.6% of the table) came to
        // look like measured midnight readings. Absent means the column keeps its
        // NULL default; it must not appear in the body at all.
        val row = EditableReading(readingTime = "", systolicBp = "140")
        val body = row.payload(7)
        assertFalse("reading_time must be absent", body.containsKey("reading_time"))
        assertEquals(140, body["systolic_bp"])
        // And Gson must not resurrect it as an explicit null.
        assertFalse(gson.toJson(body).contains("reading_time"))
    }

    // ── blank rows are not readings ───────────────────────────────────────

    @Test
    fun `an added but abandoned row is blank`() {
        assertTrue(EditableReading().isBlank)
        assertFalse(EditableReading(pulse = "72").isBlank)
        assertFalse(EditableReading(readingTime = "10:00").isBlank)
    }

    @Test
    fun `a row carrying only whitespace is still blank`() {
        assertTrue(EditableReading(systolicBp = "  ", remarks = " ").isBlank)
    }

    // ── PUT vs POST is decided by serverId ────────────────────────────────

    @Test
    fun `a server row keeps its id so it is updated rather than duplicated`() {
        // Re-POSTing an edited row is how a corrected flowsheet GREW: the amended
        // values differ from the stored ones, so nothing could match them up.
        val loaded = EditableReading.from(reading(id = 91, time = "14:30:00"))
        assertEquals(91, loaded.serverId)
        assertEquals("14:30", loaded.readingTime)
        assertNull("update body must not carry session_id",
                   loaded.payload(null)["session_id"])
        assertEquals(3, loaded.payload(3)["session_id"])
    }

    @Test
    fun `a reading with no stored time loads as an empty field, not midnight`() {
        assertEquals("", EditableReading.from(reading(id = 1, time = null)).readingTime)
    }

    // ── numbers survive the round trip ────────────────────────────────────

    @Test
    fun `whole numbers lose their decimal point in the field`() {
        val loaded = EditableReading.from(reading(id = 2, bfr = 250.0f, ufRate = 812.5f))
        assertEquals("250", loaded.bloodFlowRate)
        assertEquals("812.5", loaded.ufRate)
    }

    @Test
    fun `only fields the user filled in are sent`() {
        val body = EditableReading(readingTime = "08:00", pulse = "68").payload(4)
        assertEquals(setOf("session_id", "reading_time", "pulse"), body.keys)
    }

    private fun reading(
        id: Int,
        time: String? = null,
        bfr: Float? = null,
        ufRate: Float? = null,
    ) = IntradialyticReading(
        id = id, sessionId = 1, readingTime = time, readingNumber = null,
        systolicBp = null, diastolicBp = null, pulse = null,
        meanArterialPressure = null, dialysateRate = null,
        dialysateVolumeRemaining = null, ufRate = ufRate, ufVolumeRemoved = null,
        bloodFlowRate = bfr, arterialPressure = null, venousPressure = null,
        effluentPressure = null, accessState = null, salineAmount = null,
        remarks = null, createdAt = null,
    )
}
