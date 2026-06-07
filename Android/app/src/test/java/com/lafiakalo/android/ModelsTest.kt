package com.alafia.android

import com.alafia.android.models.User
import com.alafia.android.models.FitnessLog
import com.alafia.android.models.MoodEntry
import com.google.gson.Gson
import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for data model JSON parsing.
 * Verifies that Gson can correctly deserialize API responses.
 */
class ModelsTest {

    private val gson = Gson()

    @Test
    fun `User model parses from JSON correctly`() {
        val json = """
        {
            "id": 1,
            "email": "test@example.com",
            "full_name": "Test User",
            "date_of_birth": "1990-01-15",
            "gender": "male",
            "profile_picture_url": null,
            "is_active": true,
            "is_superuser": false,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "system_id": "SID-ABC123"
        }
        """.trimIndent()

        val user = gson.fromJson(json, User::class.java)

        assertEquals(1, user.id)
        assertEquals("test@example.com", user.email)
        assertEquals("Test User", user.full_name)
        assertEquals("1990-01-15", user.date_of_birth)
        assertTrue(user.is_active)
        assertFalse(user.is_superuser)
        assertEquals("SID-ABC123", user.system_id)
    }

    @Test
    fun `User model handles null optional fields`() {
        val json = """
        {
            "id": 2,
            "email": "minimal@example.com",
            "full_name": "Minimal User",
            "date_of_birth": null,
            "gender": null,
            "profile_picture_url": null,
            "is_active": true,
            "is_superuser": false,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z"
        }
        """.trimIndent()

        val user = gson.fromJson(json, User::class.java)

        assertNull(user.date_of_birth)
        assertNull(user.gender)
        assertNull(user.system_id)
    }

    @Test
    fun `FitnessLog model parses correctly`() {
        val json = """
        {
            "id": 10,
            "user_id": 1,
            "log_date": "2026-04-14",
            "activity_type": "running",
            "duration_minutes": 30,
            "distance_km": 5.0,
            "calories_burned": 350.0,
            "heart_rate_avg": 145,
            "heart_rate_max": 170,
            "steps": 6000,
            "sets": null,
            "reps": null,
            "weight_kg": null,
            "intensity": "moderate",
            "notes": "Morning run",
            "created_at": "2026-04-14T06:30:00Z"
        }
        """.trimIndent()

        val log = gson.fromJson(json, FitnessLog::class.java)

        assertEquals(10, log.id)
        assertEquals("running", log.activity_type)
        assertEquals(30, log.duration_minutes)
        assertEquals(5.0f, log.distance_km)
        assertEquals(350.0f, log.calories_burned)
    }

    @Test
    fun `MoodEntry model uses SerializedName mapping`() {
        val json = """
        {
            "id": 5,
            "user_id": 1,
            "entry_date": "2026-04-14",
            "mood_score": 7,
            "energy_level": 6,
            "stress_level": 4,
            "anxiety_level": 3,
            "sleep_quality": 8,
            "sleep_hours": 7.5,
            "emotions": "happy,calm",
            "triggers": null,
            "coping_strategies": "meditation",
            "gratitude": "Family time",
            "journal_entry": "Good day",
            "notes": null
        }
        """.trimIndent()

        val mood = gson.fromJson(json, MoodEntry::class.java)

        assertEquals(5, mood.id)
        assertEquals(1, mood.userId)
        assertEquals("2026-04-14", mood.entryDate)
        assertEquals(7, mood.moodScore)
        assertEquals(6, mood.energyLevel)
        assertEquals(7.5, mood.sleepHours)
    }
}
