package com.alafia.android

import com.alafia.android.models.NutritionLog
import com.alafia.android.models.LabResult
import com.alafia.android.models.Medication
import com.alafia.android.util.ErrorUtil
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import org.junit.Assert.*
import org.junit.Test
import retrofit2.HttpException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import java.net.SocketTimeoutException
import java.net.UnknownHostException

// ══════════════════════════════════════════════════════════════════════════════
// NutritionLog model tests
// ══════════════════════════════════════════════════════════════════════════════

class NutritionLogModelTest {

    private val gson: Gson = GsonBuilder().serializeNulls().create()

    @Test
    fun `NutritionLog parses full JSON correctly`() {
        val json = """
        {
            "id": 1,
            "user_id": 42,
            "log_date": "2026-04-28",
            "meal_type": "breakfast",
            "food_name": "Oatmeal",
            "serving_size": "1 cup",
            "fdc_id": null,
            "calories": 150.0,
            "protein_g": 5.0,
            "carbs_g": 27.0,
            "fat_g": 2.5,
            "fiber_g": 4.0,
            "sugar_g": 1.0,
            "sodium_mg": 60.0,
            "potassium_mg": 140.0,
            "notes": "with berries",
            "created_at": "2026-04-28T08:00:00Z"
        }
        """.trimIndent()

        val log = gson.fromJson(json, NutritionLog::class.java)

        assertEquals(1, log.id)
        assertEquals(42, log.userId)
        assertEquals("2026-04-28", log.logDate)
        assertEquals("breakfast", log.mealType)
        assertEquals("Oatmeal", log.foodName)
        assertEquals(150.0f, log.calories)
        assertEquals(5.0f, log.proteinG)
        assertEquals(27.0f, log.carbsG)
        assertEquals(4.0f, log.fiberG)
        assertEquals(60.0f, log.sodiumMg)
        assertEquals("with berries", log.notes)
    }

    @Test
    fun `NutritionLog handles null optional fields`() {
        val json = """
        {
            "id": 2,
            "user_id": 1,
            "log_date": "2026-04-28",
            "meal_type": "lunch",
            "food_name": "Brown rice",
            "created_at": "2026-04-28T12:00:00Z"
        }
        """.trimIndent()

        val log = gson.fromJson(json, NutritionLog::class.java)

        assertNull(log.calories)
        assertNull(log.proteinG)
        assertNull(log.fiberG)
        assertNull(log.notes)
        assertNull(log.fdcId)
    }

    @Test
    fun `NutritionLog parses extended_nutrients map`() {
        val json = """
        {
            "id": 3,
            "user_id": 1,
            "log_date": "2026-04-28",
            "meal_type": "dinner",
            "food_name": "Salmon",
            "extended_nutrients": {"omega3_g": 2.5, "selenium_mcg": 36.0},
            "created_at": "2026-04-28T19:00:00Z"
        }
        """.trimIndent()

        val log = gson.fromJson(json, NutritionLog::class.java)

        assertNotNull(log.extendedNutrients)
        assertEquals(2.5f, log.extendedNutrients!!["omega3_g"])
        assertEquals(36.0f, log.extendedNutrients!!["selenium_mcg"])
    }

    @Test
    fun `NutritionLog meal types are preserved`() {
        for (mealType in listOf("breakfast", "lunch", "dinner", "snack")) {
            val json = """{"id":1,"user_id":1,"log_date":"2026-04-28","meal_type":"$mealType","food_name":"Food","created_at":"2026-04-28T00:00:00Z"}"""
            val log = gson.fromJson(json, NutritionLog::class.java)
            assertEquals(mealType, log.mealType)
        }
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// LabResult model tests
// ══════════════════════════════════════════════════════════════════════════════

class LabResultModelTest {

    private val gson = Gson()

    private fun makeLabJson(extras: String = ""): String = """
        {
            "id": 10,
            "user_id": 42,
            "test_date": "2026-04-28",
            "test_name": "Albumin",
            "value": 4.2,
            "unit": "g/dL",
            "status": "final",
            "created_at": "2026-04-28T10:00:00Z"
            ${ if (extras.isNotEmpty()) ",$extras" else "" }
        }
    """.trimIndent()

    @Test
    fun `LabResult parses basic fields`() {
        val r = gson.fromJson(makeLabJson(), LabResult::class.java)
        assertEquals(10, r.id)
        assertEquals("Albumin", r.test_name)
        assertEquals(4.2f, r.value)
        assertEquals("g/dL", r.unit)
        assertEquals("final", r.status)
    }

    @Test
    fun `LabResult parses reference range`() {
        val r = gson.fromJson(
            makeLabJson(""""reference_range_low": 3.4, "reference_range_high": 4.8"""),
            LabResult::class.java
        )
        assertEquals(3.4f, r.reference_range_low)
        assertEquals(4.8f, r.reference_range_high)
    }

    @Test
    fun `LabResult handles null optional fields`() {
        val r = gson.fromJson(makeLabJson(), LabResult::class.java)
        assertNull(r.loinc_code)
        assertNull(r.category)
        assertNull(r.ordering_provider)
        assertNull(r.performing_lab)
        assertNull(r.reference_range_low)
    }

    @Test
    fun `LabResult parses is_abnormal flag`() {
        val r = gson.fromJson(makeLabJson(""""is_abnormal": true"""), LabResult::class.java)
        assertEquals(true, r.is_abnormal)
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// Medication model tests
// ══════════════════════════════════════════════════════════════════════════════

class MedicationModelTest {

    private val gson = Gson()

    @Test
    fun `Medication parses all fields correctly`() {
        val json = """
        {
            "id": 5,
            "user_id": 42,
            "name": "Lisinopril",
            "dosage": "10 mg",
            "frequency": "once daily",
            "reason": "Hypertension",
            "start_date": "2026-01-01",
            "end_date": null,
            "notes": "Take with food",
            "created_at": "2026-01-01T00:00:00Z"
        }
        """.trimIndent()

        val med = gson.fromJson(json, Medication::class.java)

        assertEquals(5, med.id)
        assertEquals("Lisinopril", med.name)
        assertEquals("10 mg", med.dosage)
        assertEquals("once daily", med.frequency)
        assertEquals("Hypertension", med.reason)
        assertEquals("Take with food", med.notes)
    }

    @Test
    fun `Medication optional fields null when absent`() {
        val json = """
        {
            "id": 6,
            "user_id": 1,
            "name": "Aspirin",
            "dosage": "81 mg",
            "frequency": "daily",
            "reason": "Cardiac",
            "start_date": "2026-01-01",
            "end_date": null,
            "notes": null,
            "created_at": "2026-01-01T00:00:00Z"
        }
        """.trimIndent()

        val med = gson.fromJson(json, Medication::class.java)

        assertNull(med.end_date)
        assertNull(med.notes)
    }
}

// ══════════════════════════════════════════════════════════════════════════════
// ErrorUtil tests (extended)
// ══════════════════════════════════════════════════════════════════════════════

class ErrorUtilExtendedTest {

    private fun makeHttpException(code: Int): HttpException {
        val body = "error".toResponseBody("application/json".toMediaType())
        val response = Response.Builder()
            .code(code)
            .message("Error")
            .protocol(Protocol.HTTP_1_1)
            .request(Request.Builder().url("http://test.example.com/").build())
            .body(body)
            .build()
        return HttpException(retrofit2.Response.error<Any>(code, body))
    }

    @Test
    fun `401 returns session expired message`() {
        val msg = ErrorUtil.userMessage(makeHttpException(401))
        assertTrue(msg.contains("log in", ignoreCase = true))
    }

    @Test
    fun `403 returns permission denied message`() {
        val msg = ErrorUtil.userMessage(makeHttpException(403))
        assertTrue(msg.contains("permission", ignoreCase = true))
    }

    @Test
    fun `404 returns not found message`() {
        val msg = ErrorUtil.userMessage(makeHttpException(404))
        assertTrue(msg.contains("not found", ignoreCase = true))
    }

    @Test
    fun `429 returns rate limit message`() {
        val msg = ErrorUtil.userMessage(makeHttpException(429))
        assertTrue(msg.contains("Too many", ignoreCase = true))
    }

    @Test
    fun `500 returns server error message`() {
        val msg = ErrorUtil.userMessage(makeHttpException(500))
        assertTrue(msg.contains("Server error", ignoreCase = true))
    }

    @Test
    fun `UnknownHostException returns no internet message`() {
        val msg = ErrorUtil.userMessage(UnknownHostException("host"))
        assertTrue(msg.contains("internet", ignoreCase = true))
    }

    @Test
    fun `SocketTimeoutException returns timeout message`() {
        val msg = ErrorUtil.userMessage(SocketTimeoutException())
        assertTrue(msg.contains("timed out", ignoreCase = true))
    }

    @Test
    fun `Unknown exception returns generic message`() {
        val msg = ErrorUtil.userMessage(Exception("unexpected"))
        assertTrue(msg.contains("Something went wrong", ignoreCase = true))
    }
}
