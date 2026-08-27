package com.alafia.android.util

import com.alafia.android.schemas.DoseGuardErrorBody
import com.alafia.android.schemas.DoseGuardRefusal
import com.google.gson.Gson
import retrofit2.HttpException

/**
 * Reads the dose guard's refusal out of a 422.
 *
 * `POST /medications/dose-logs` answers a flagged dose with `detail` as an
 * OBJECT — the findings that name what is wrong and the field that overrides it:
 *
 *     {"detail": {"message": "...", "findings": [...], "override_with": "acknowledge_unusual"}}
 *
 * Android threw all of it away. A 422 fell through [ErrorUtil.userMessage] to
 * "Something went wrong. Please try again." — which does not even say the dose
 * was questioned, on a guard that had already worked out that "Calcium
 * Carbonated" should be "Calcium Carbonate" and offered a way through. A guard
 * that cannot explain itself gets blamed for the thing it did not do, and one
 * with no route forward blocks a true clinical record.
 *
 * Returns null for anything that is not a refusal, so an ordinary failure still
 * takes the ordinary path — an error is not the same event as a refusal.
 */
object DoseGuard {
    private val gson = Gson()

    fun refusalFrom(e: Exception): DoseGuardRefusal? {
        if (e !is HttpException || e.code() != 422) return null
        val body = try {
            e.response()?.errorBody()?.string()
        } catch (_: Exception) {
            null
        } ?: return null
        val parsed = try {
            gson.fromJson(body, DoseGuardErrorBody::class.java)
        } catch (_: Exception) {
            null
        }
        val refusal = parsed?.detail ?: return null
        // A refusal with nothing to say is no better than the generic message.
        return if (refusal.findings.isEmpty()) null else refusal
    }
}
